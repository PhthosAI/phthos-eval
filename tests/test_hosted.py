from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from phthos_eval.constants import SCHEMA_VERSION
from phthos_eval.live.client import LiveClient, LiveError
from phthos_eval.live.config import LiveSettings
from phthos_eval.live.server import serve_in_thread
from phthos_eval.schema import validate_diagnosis

ROOT = Path(__file__).resolve().parents[1]
DATASET = json.loads((ROOT / "fixtures" / "dataset.json").read_text(encoding="utf-8"))
LIVE_CONFIG = {
    "id": DATASET["id"],
    "budget": DATASET["budget"],
    "policy": DATASET["policy"],
    "tool_schemas": DATASET["tool_schemas"],
    "default_expected_tools": ["search"],
}


def _spans(case_id: str) -> list:
    case = next(c for c in DATASET["cases"] if c["id"] == case_id)
    return case["traces"][0]["spans"]


@pytest.fixture
def hosted(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(LIVE_CONFIG), encoding="utf-8")
    settings = LiveSettings(
        host="127.0.0.1",
        port=0,
        sample_rate=1.0,
        data_dir=tmp_path / "data",
        config_path=cfg,
        live_judge=False,
        hosted=True,
        alert_min_pass_rate=0.8,
    )
    app, httpd, url = serve_in_thread(settings)
    try:
        yield url, app
    finally:
        httpd.shutdown()
        app.stop()


def test_hosted_health_and_status_need_no_key(hosted) -> None:
    url, _app = hosted
    client = LiveClient(url)
    health = client.health()
    assert health["ok"] is True
    assert health["hosted"] is True
    assert health["mode"] == "hosted"
    assert health["schema_version"] == SCHEMA_VERSION
    assert health["judge"] == "off"
    status = client.status()
    assert status["product"] == "phthos-eval"
    with pytest.raises(LiveError) as exc:
        client.scores()
    assert exc.value.status == 401


def test_hosted_signup_login_and_tenant_isolation(hosted) -> None:
    url, app = hosted
    alpha = LiveClient(url)
    a = alpha.signup("a@example.com", "password1", "alpha")
    alpha.api_key = a["api_key"]
    beta = LiveClient(url)
    b = beta.signup("b@example.com", "password1", "beta")
    beta.api_key = b["api_key"]
    assert a["workspace_id"] != b["workspace_id"]
    assert a["api_key"].startswith("pk_")

    resp = alpha.ingest(_spans("fail-policy"), case_id="fail-policy", expected_tools=["search"])
    app.wait_idle(timeout=5)
    doc = alpha.diagnosis(resp["id"])
    assert validate_diagnosis(doc) == []
    assert doc["schema_version"] == SCHEMA_VERSION
    assert alpha.scores()["scored"] == 1
    assert beta.scores()["scored"] == 0
    with pytest.raises(LiveError) as exc:
        beta.diagnosis(resp["id"])
    assert exc.value.status == 404

    session = LiveClient(url)
    session.login("a@example.com", "password1")
    me = session.me()
    assert me["email"] == "a@example.com"
    assert me["workspace_id"] == a["workspace_id"]
    assert session.scores()["scored"] == 1


def test_hosted_dataset_run_and_export_bundle(hosted) -> None:
    url, _app = hosted
    client = LiveClient(url)
    client.api_key = client.signup("ds@example.com", "password1", "ds")["api_key"]
    created = client.put_dataset("spike", DATASET)
    listed = client.datasets()
    assert listed["datasets"][0]["id"] == created["id"]
    doc = client.run_dataset(created["id"])
    assert validate_diagnosis(doc) == []
    assert doc["schema_version"] == SCHEMA_VERSION
    pulled = client.dataset(created["id"])
    assert pulled["body"]["id"] == DATASET["id"]
    bundle = client.export_bundle()
    assert bundle["schema_version"] == SCHEMA_VERSION
    assert len(bundle["diagnoses"]) == 1
    assert len(bundle["datasets"]) == 1
    assert bundle["datasets"][0]["body"]["id"] == DATASET["id"]


def test_hosted_score_drop_webhook(hosted) -> None:
    url, app = hosted
    received: list[dict] = []

    class Hook(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_POST(self) -> None:
            n = int(self.headers.get("Content-Length") or 0)
            received.append(json.loads(self.rfile.read(n)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

    hook = ThreadingHTTPServer(("127.0.0.1", 0), Hook)
    Thread(target=hook.serve_forever, daemon=True).start()
    try:
        hook_url = f"http://127.0.0.1:{hook.server_address[1]}/hook"
        client = LiveClient(url)
        client.api_key = client.signup("al@example.com", "password1", "al")["api_key"]
        client.set_alerts(webhook_url=hook_url, min_pass_rate=0.8)
        client.ingest(_spans("pass-search"), case_id="pass-search", expected_tools=["search"])
        app.wait_idle(timeout=5)
        client.ingest(_spans("fail-policy"), case_id="fail-policy", expected_tools=["search"])
        app.wait_idle(timeout=5)
        assert received, "webhook should fire when pass rate drops"
        assert received[0]["event"] == "score_drop"
        assert received[0]["pass_rate"] < 0.8
        alerts = client.alerts()
        assert alerts["recent"][0]["kind"] == "score_drop"
    finally:
        hook.shutdown()


def test_oss_self_host_still_open(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(LIVE_CONFIG), encoding="utf-8")
    settings = LiveSettings(
        host="127.0.0.1",
        port=0,
        sample_rate=1.0,
        data_dir=tmp_path / "data",
        config_path=cfg,
        hosted=False,
    )
    app, httpd, url = serve_in_thread(settings)
    try:
        client = LiveClient(url)
        assert client.health()["hosted"] is False
        assert client.health()["mode"] == "self-host"
        resp = client.ingest(_spans("pass-search"), expected_tools=["search"])
        app.wait_idle(timeout=5)
        doc = client.diagnosis(resp["id"])
        assert validate_diagnosis(doc) == []
        with pytest.raises(LiveError) as exc:
            client.signup("x@example.com", "password1")
        assert exc.value.status == 404
    finally:
        httpd.shutdown()
        app.stop()
