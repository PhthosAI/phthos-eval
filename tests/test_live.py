from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from phthos_eval.live.client import LiveClient, LiveError
from phthos_eval.live.config import LiveSettings, should_sample
from phthos_eval.live.otel import otlp_to_traces
from phthos_eval.live.score import score_one_trace
from phthos_eval.live.server import serve_in_thread
from phthos_eval.runner import run_dataset
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


def _first_trace(case_id: str) -> dict:
    case = next(c for c in DATASET["cases"] if c["id"] == case_id)
    return case["traces"][0]


def test_sample_rate_bounds() -> None:
    assert should_sample("any", 0) is False
    assert should_sample("any", 1) is True
    a = should_sample("stable-key", 0.5)
    b = should_sample("stable-key", 0.5)
    assert a is b


def test_live_score_matches_offline_schema_and_failures() -> None:
    trace = _first_trace("fail-policy")
    live = score_one_trace(
        trace,
        config=LIVE_CONFIG,
        case_id="fail-policy",
        expected_tools=["search"],
        run_id="live-1",
        judge=False,
    )
    offline = run_dataset(
        {
            "id": DATASET["id"],
            "n_runs": 1,
            "budget": DATASET["budget"],
            "policy": DATASET["policy"],
            "tool_schemas": DATASET["tool_schemas"],
            "cases": [
                {
                    "id": "fail-policy",
                    "expected_tools": ["search"],
                    "traces": [trace],
                }
            ],
        },
        run_id="off-1",
        judge=False,
    )
    assert validate_diagnosis(live) == []
    assert validate_diagnosis(offline) == []
    assert live["schema_version"] == offline["schema_version"]
    assert live["n_runs"] == offline["n_runs"] == 1
    assert {f["type"] for f in live["failures"]} == {f["type"] for f in offline["failures"]}
    assert live["change_class"] == offline["change_class"]
    assert live["judge"]["reason"] == "disabled"


def test_live_does_not_call_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(*_a, **_k):
        raise AssertionError("judge must not run on the live path")

    monkeypatch.setattr("phthos_eval.runner.maybe_judge", boom)
    score_one_trace(
        _first_trace("pass-search"),
        config=LIVE_CONFIG,
        case_id="pass-search",
        expected_tools=["search"],
        judge=False,
    )


def test_otlp_maps_tool_and_llm() -> None:
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "aaa",
                                "spanId": "s1",
                                "name": "chat",
                                "startTimeUnixNano": "0",
                                "endTimeUnixNano": "120000000",
                                "attributes": [
                                    {
                                        "key": "openinference.span.kind",
                                        "value": {"stringValue": "LLM"},
                                    }
                                ],
                            },
                            {
                                "traceId": "aaa",
                                "spanId": "s2",
                                "name": "search",
                                "startTimeUnixNano": "120000000",
                                "endTimeUnixNano": "160000000",
                                "attributes": [
                                    {
                                        "key": "gen_ai.tool.name",
                                        "value": {"stringValue": "search"},
                                    },
                                    {
                                        "key": "tool.parameters",
                                        "value": {"stringValue": '{"query":"hours"}'},
                                    },
                                ],
                            },
                        ]
                    }
                ]
            }
        ]
    }
    traces = otlp_to_traces(payload)
    assert len(traces) == 1
    types = [s["type"] for s in traces[0]["spans"]]
    assert types == ["llm", "tool"]
    tool = traces[0]["spans"][1]
    assert tool["name"] == "search"
    assert tool["args"]["query"] == "hours"
    assert tool["latency_ms"] == 40.0


@pytest.fixture
def live_url(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(LIVE_CONFIG), encoding="utf-8")
    settings = LiveSettings(
        host="127.0.0.1",
        port=0,
        sample_rate=1.0,
        data_dir=tmp_path / "data",
        config_path=cfg,
        live_judge=False,
    )
    app, httpd, url = serve_in_thread(settings)
    try:
        yield url, app, tmp_path
    finally:
        httpd.shutdown()
        app.stop()


def test_http_ingest_async_then_diagnosis(live_url) -> None:
    url, app, _tmp = live_url
    client = LiveClient(url)
    health = client.health()
    assert health["ok"] is True
    assert health["judge"] == "off"
    assert health["sample_rate"] == 1.0
    trace = _first_trace("fail-wrong-tool")
    resp = client.ingest(
        trace["spans"],
        agent_id="t",
        case_id="fail-wrong-tool",
        expected_tools=["search"],
    )
    assert resp["accepted"] is True
    assert resp["sampled"] is True
    app.wait_idle(timeout=5)
    doc = None
    for _ in range(50):
        try:
            doc = client.diagnosis(resp["id"])
            break
        except LiveError:
            time.sleep(0.05)
    assert doc is not None
    assert validate_diagnosis(doc) == []
    assert any(f["type"] == "wrong_tool" for f in doc["failures"])
    scores = client.scores()
    assert scores["scored"] >= 1
    assert scores["received"] >= 1
    assert scores["judge"] == "off"


def test_sample_rate_zero_skips_diagnosis(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(LIVE_CONFIG), encoding="utf-8")
    settings = LiveSettings(
        host="127.0.0.1",
        port=0,
        sample_rate=0.0,
        data_dir=tmp_path / "data",
        config_path=cfg,
    )
    app, httpd, url = serve_in_thread(settings)
    try:
        client = LiveClient(url)
        resp = client.ingest(_first_trace("pass-search")["spans"], case_id="x")
        assert resp["sampled"] is False
        app.wait_idle(timeout=2)
        with pytest.raises(LiveError) as exc:
            client.diagnosis(resp["id"])
        assert exc.value.status == 404
        scores = client.scores()
        assert scores["received"] == 1
        assert scores["sampled"] == 0
        assert scores["scored"] == 0
    finally:
        httpd.shutdown()
        app.stop()


def test_export_reruns_offline(live_url) -> None:
    url, app, tmp_path = live_url
    client = LiveClient(url)
    trace = _first_trace("fail-policy")
    resp = client.ingest(
        trace["spans"],
        case_id="fail-policy",
        expected_tools=["search"],
    )
    app.wait_idle(timeout=5)
    out = tmp_path / "from-live.json"
    exported = client.export(resp["id"], path=str(out))
    assert Path(exported["path"]).is_file()
    dataset = json.loads(out.read_text(encoding="utf-8"))
    doc = run_dataset(dataset, judge=False)
    assert validate_diagnosis(doc) == []
    assert any(f["type"] == "policy" for f in doc["failures"])


def test_otel_http_ingest(live_url) -> None:
    url, app, _tmp = live_url
    client = LiveClient(url)
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "abc",
                                "spanId": "t1",
                                "name": "search",
                                "attributes": [
                                    {
                                        "key": "gen_ai.tool.name",
                                        "value": {"stringValue": "lookup"},
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    resp = client.ingest_otlp(payload)
    assert resp["accepted"] is True
    assert resp["traces"] == 1
    app.wait_idle(timeout=5)
    doc = client.diagnosis(resp["ids"][0])
    assert any(f["type"] == "wrong_tool" for f in doc["failures"])
