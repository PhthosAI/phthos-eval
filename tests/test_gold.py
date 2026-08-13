from __future__ import annotations

import json
from pathlib import Path

import pytest

from phthos_eval.cli import main
from phthos_eval.gold import build_pack, pack_to_dataset, source_hashes, validate_gold_pack
from phthos_eval.live.client import LiveClient, LiveError
from phthos_eval.live.config import LiveSettings
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


def _spans(case_id: str) -> list:
    case = next(c for c in DATASET["cases"] if c["id"] == case_id)
    return case["traces"][0]["spans"]


def test_source_hash_changes_with_schema() -> None:
    a = source_hashes(tool_schemas={"search": {"type": "object"}}, policy={}, sop="")
    b = source_hashes(tool_schemas={"search": {"type": "object", "required": ["q"]}}, policy={}, sop="")
    assert a["tools"] != b["tools"]
    assert a["policy"] == b["policy"]


def test_offline_run_accepts_gold_pack() -> None:
    pack = build_pack(
        agent_id="support",
        tool_schemas=DATASET["tool_schemas"],
        policy=DATASET["policy"],
        budget=DATASET["budget"],
        cases=[
            {
                "id": "pass-search",
                "expected_tools": ["search"],
                "traces": [DATASET["cases"][0]["traces"][0]],
            }
        ],
        default_expected_tools=["search"],
    )
    assert validate_gold_pack(pack) == []
    doc = run_dataset(pack_to_dataset(pack), judge=False)
    assert validate_diagnosis(doc) == []
    assert doc["gold_version"] == pack["version"]
    assert doc["gold_stale"] is False


def test_cli_gold_export(tmp_path: Path) -> None:
    pack = build_pack(
        agent_id="a",
        tool_schemas={"search": {"type": "object"}},
        policy={"deny_tools": []},
        cases=[],
    )
    src = tmp_path / "gold.json"
    out = tmp_path / "ds.json"
    src.write_text(json.dumps(pack), encoding="utf-8")
    assert main(["gold", "-f", str(src), "--dataset-out", str(out)]) == 0
    dataset = json.loads(out.read_text(encoding="utf-8"))
    assert dataset["gold_version"] == pack["version"]


def test_cli_gold_check_stale(tmp_path: Path) -> None:
    pack = build_pack(agent_id="a", tool_schemas={"search": {}}, policy={})
    src = tmp_path / "get.json"
    src.write_text(
        json.dumps({"pack": pack, "stale": True, "version": pack["version"]}),
        encoding="utf-8",
    )
    assert main(["gold", "-f", str(src), "--check-stale"]) == 2


def test_live_gold_stale_candidate_confirm_reject(tmp_path: Path) -> None:
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
        client = LiveClient(url)
        put = client.put_gold(
            "support",
            {
                "tool_schemas": DATASET["tool_schemas"],
                "policy": DATASET["policy"],
                "budget": DATASET["budget"],
                "sop": "refunds require lookup_order first",
                "default_expected_tools": ["search"],
                "cases": [],
            },
        )
        pack = put["pack"]
        assert put["stale"] is False
        got = client.gold("support")
        assert got["stale"] is False
        assert got["pack"]["version"] == pack["version"]

        sync = client.sync_gold(
            "support",
            {
                "tool_schemas": {"search": {"type": "object", "required": ["q"]}},
                "policy": DATASET["policy"],
                "sop": "refunds require lookup_order first",
            },
        )
        assert sync["stale"] is True
        assert client.gold("support")["stale"] is True
        scores = client.scores()
        assert scores["gold_stale"] is True

        client.put_gold(
            "support",
            {
                "tool_schemas": {"search": {"type": "object", "required": ["q"]}},
                "policy": DATASET["policy"],
                "budget": DATASET["budget"],
                "sop": "refunds require lookup_order first",
                "default_expected_tools": ["search"],
                "cases": [],
            },
        )
        assert client.gold("support")["stale"] is False

        resp = client.ingest(
            _spans("fail-policy"),
            agent_id="support",
            case_id="fail-policy",
            expected_tools=["search"],
        )
        app.wait_idle(timeout=5)
        doc = client.diagnosis(resp["id"])
        assert validate_diagnosis(doc) == []
        assert doc["gold_version"]
        pending = client.gold_candidates("support")["candidates"]
        assert pending, "failing live run should enqueue a candidate"
        cid = pending[0]["id"]

        with pytest.raises(LiveError) as exc:
            client.confirm_candidate(cid, source="judge")
        assert exc.value.status == 400
        assert "judge_cannot_confirm" in exc.value.body

        still = client.gold_candidates("support")["candidates"]
        assert any(c["id"] == cid for c in still)

        confirmed = client.confirm_candidate(cid)
        assert confirmed["ok"] is True
        cases = confirmed["pack"]["cases"]
        assert any(c.get("id") == "fail-policy" for c in cases)
        assert client.gold_candidates("support")["candidates"] == []

        exported = client.export_gold("support")
        assert exported["gold_version"] == confirmed["pack"]["version"]
        rerun = run_dataset(exported, judge=False)
        assert validate_diagnosis(rerun) == []
        assert any(c["case_id"] == "fail-policy" for c in rerun["cases"])

        resp2 = client.ingest(
            _spans("fail-wrong-tool"),
            agent_id="support",
            case_id="fail-wrong-tool",
            expected_tools=["search"],
        )
        app.wait_idle(timeout=5)
        cid2 = client.gold_candidates("support")["candidates"][0]["id"]
        client.reject_candidate(cid2)
        gold = client.gold("support")["pack"]
        assert not any(c.get("id") == "fail-wrong-tool" for c in gold["cases"])
        assert client.gold_candidates("support")["candidates"] == []
        _ = resp2
    finally:
        httpd.shutdown()
        app.stop()


def test_passing_none_does_not_enqueue(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(LIVE_CONFIG), encoding="utf-8")
    settings = LiveSettings(
        host="127.0.0.1",
        port=0,
        sample_rate=1.0,
        data_dir=tmp_path / "data",
        config_path=cfg,
    )
    app, httpd, url = serve_in_thread(settings)
    try:
        client = LiveClient(url)
        client.put_gold(
            "search-bot",
            {
                "tool_schemas": DATASET["tool_schemas"],
                "policy": DATASET["policy"],
                "budget": DATASET["budget"],
                "default_expected_tools": ["search"],
            },
        )
        client.ingest(
            _spans("pass-search"),
            agent_id="search-bot",
            case_id="pass-search",
            expected_tools=["search"],
        )
        app.wait_idle(timeout=5)
        assert client.gold_candidates("search-bot")["candidates"] == []
    finally:
        httpd.shutdown()
        app.stop()
