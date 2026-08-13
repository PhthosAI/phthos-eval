from __future__ import annotations

import json
from pathlib import Path

import pytest

from phthos_eval.cli import main
from phthos_eval.runner import run_dataset
from phthos_eval.schema import load_schema, validate_diagnosis

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "fixtures" / "dataset.json"


def test_schema_file_loads() -> None:
    schema = load_schema()
    assert schema["properties"]["schema_version"]["const"] == "0.1.0"


def test_fixture_run_emits_typed_failure_and_change_class() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    doc = run_dataset(dataset)
    assert validate_diagnosis(doc) == []
    types = {f["type"] for f in doc["failures"]}
    assert "wrong_tool" in types
    assert "budget" in types
    assert "policy" in types
    assert "loop" in types
    assert doc["change_class"] in {
        "prompt",
        "tool",
        "policy",
        "model",
        "finetune_data",
        "none",
    }
    assert doc["change_class"] != "none"
    assert doc["n_runs"] == 2
    assert doc["judge"]["skipped"] is True
    assert doc["judge"]["reason"] == "no_key"
    by_id = {c["case_id"]: c for c in doc["cases"]}
    assert by_id["pass-search"]["passed"] is True
    assert by_id["fail-wrong-tool"]["passed"] is False


def test_support_agent_dogfood() -> None:
    path = ROOT / "examples" / "support_agent" / "dataset.json"
    doc = run_dataset(json.loads(path.read_text(encoding="utf-8")))
    by_id = {c["case_id"]: c for c in doc["cases"]}
    assert by_id["status-ok"]["passed"] is True
    assert by_id["refund-denied"]["passed"] is False
    assert any(f["type"] == "policy" for f in doc["failures"])


def test_cli_writes_file_and_check_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PHTHOS_EVAL_API_KEY", raising=False)
    out = tmp_path / "diagnosis.json"
    assert main(["run", "-d", str(DATASET), "-o", str(out)]) == 0
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert validate_diagnosis(raw) == []
    assert raw["failures"]
    assert raw["change_class"] != "none"
    assert main(["check", str(out)]) == 0
    assert main(["run", "-d", str(DATASET), "-o", str(out), "--fail-on-findings"]) == 1
