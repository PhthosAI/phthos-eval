from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phthos_eval.live.auth import sign_sso
from phthos_eval.live.client import LiveClient, LiveError
from phthos_eval.live.config import LiveSettings
from phthos_eval.live.server import serve_in_thread
from phthos_eval.plans import PLANS
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
OPS = "ops-secret-test"
SSO = "sso-secret-test"


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
        hosted=True,
        ops_secret=OPS,
        sso_secret=SSO,
        hosted_judge_api_key="sk-hosted-judge",
    )
    app, httpd, url = serve_in_thread(settings)
    try:
        yield url, app
    finally:
        httpd.shutdown()
        app.stop()


def test_plan_catalog_is_public(hosted) -> None:
    url, _app = hosted
    catalog = LiveClient(url).plans()
    ids = {p["id"] for p in catalog["plans"]}
    assert ids == {"self-host", "free", "pro"}
    pro = next(p for p in catalog["plans"] if p["id"] == "pro")
    assert pro["hosted_judge"] is True
    assert pro["retention_days"] == 365
    assert pro["saml"] is True


def test_signup_defaults_to_free_and_ops_can_upgrade(hosted) -> None:
    url, _app = hosted
    client = LiveClient(url)
    created = client.signup("owner@example.com", "password1", "acme")
    client.api_key = created["api_key"]
    assert client.plan()["plan"]["id"] == "free"
    assert client.usage()["retention_days"] == 30
    client.set_plan_ops(created["workspace_id"], "pro", OPS)
    assert client.plan()["plan"]["id"] == "pro"
    assert client.usage()["retention_days"] == 365
    assert client.usage()["hosted_judge_allowed"] is True


def test_viewer_cannot_ingest(hosted) -> None:
    url, app = hosted
    owner = LiveClient(url)
    created = owner.signup("lead@example.com", "password1", "t")
    owner.api_key = created["api_key"]
    invited = owner.invite("view@example.com", "password1", "viewer")
    assert invited["role"] == "viewer"
    viewer = LiveClient(url)
    viewer.login("view@example.com", "password1")
    assert viewer.me()["role"] == "viewer"
    with pytest.raises(LiveError) as exc:
        viewer.ingest(_spans("pass-search"), expected_tools=["search"])
    assert exc.value.status == 403
    resp = owner.ingest(_spans("pass-search"), expected_tools=["search"])
    app.wait_idle(timeout=5)
    assert resp["accepted"] is True


def test_ingest_rate_limit_on_free(hosted, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PLANS["free"], "ingest_per_day", 1)
    url, app = hosted
    client = LiveClient(url)
    client.api_key = client.signup("lim@example.com", "password1")["api_key"]
    client.ingest(_spans("pass-search"), expected_tools=["search"])
    app.wait_idle(timeout=5)
    with pytest.raises(LiveError) as exc:
        client.ingest(_spans("pass-search"), expected_tools=["search"])
    assert exc.value.status == 429


def test_free_cannot_enable_hosted_judge_pro_can_and_meters(
    hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "phthos_eval.runner.maybe_judge",
        lambda _d, **_k: {"skipped": False, "reason": None, "score": 1.0, "error": None},
    )
    url, _app = hosted
    client = LiveClient(url)
    created = client.signup("j@example.com", "password1")
    client.api_key = created["api_key"]
    with pytest.raises(LiveError) as exc:
        client.set_judge("hosted")
    assert exc.value.status == 403
    client.set_plan_ops(created["workspace_id"], "pro", OPS)
    client.set_judge("hosted")
    ds = client.put_dataset("spike", DATASET)
    doc = client.run_dataset(ds["id"])
    assert validate_diagnosis(doc) == []
    assert doc["judge"]["skipped"] is False
    assert client.usage()["hosted_judge_this_month"] >= 1
    client.set_judge("byok", api_key="sk-customer")
    assert client.judge_settings()["mode"] == "byok"
    assert client.judge_settings()["byok_configured"] is True


def test_sso_consume_creates_session(hosted) -> None:
    url, _app = hosted
    owner = LiveClient(url)
    created = owner.signup("sso-owner@example.com", "password1")
    exp = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    sig = sign_sso(SSO, "sso-user@example.com", created["workspace_id"], exp)
    guest = LiveClient(url)
    body = guest.sso_consume(
        "sso-user@example.com",
        workspace_id=created["workspace_id"],
        exp=exp,
        sig=sig,
    )
    assert body["ok"] is True
    assert guest.me()["email"] == "sso-user@example.com"


def test_pro_retention_keeps_rows_free_prunes(hosted) -> None:
    url, app = hosted
    client = LiveClient(url)
    created = client.signup("ret@example.com", "password1")
    client.api_key = created["api_key"]
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    app.store._conn.execute(
        """
        INSERT INTO diagnoses (
          id, ingest_id, created_at, passed, change_class, cost, policy_hits,
          diagnosis_json, workspace_id
        ) VALUES (?, ?, ?, 1, 'none', 0, 0, '{}', ?)
        """,
        ("old-run", "old-run", old, created["workspace_id"]),
    )
    app.store._conn.commit()
    assert app.store.prune(30, created["workspace_id"]) >= 1
    client.set_plan_ops(created["workspace_id"], "pro", OPS)
    app.store._conn.execute(
        """
        INSERT INTO diagnoses (
          id, ingest_id, created_at, passed, change_class, cost, policy_hits,
          diagnosis_json, workspace_id
        ) VALUES (?, ?, ?, 1, 'none', 0, 0, '{}', ?)
        """,
        ("kept-run", "kept-run", old, created["workspace_id"]),
    )
    app.store._conn.commit()
    assert app.store.prune(365, created["workspace_id"]) == 0


def test_self_host_ignores_plans_and_still_scores(tmp_path: Path) -> None:
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
        assert client.health()["hosted_judge"] is False
        resp = client.ingest(_spans("pass-search"), expected_tools=["search"])
        app.wait_idle(timeout=5)
        doc = client.diagnosis(resp["id"])
        assert validate_diagnosis(doc) == []
        with pytest.raises(LiveError) as exc:
            client.set_plan_ops("x", "pro", OPS)
        assert exc.value.status in {401, 404}
    finally:
        httpd.shutdown()
        app.stop()
