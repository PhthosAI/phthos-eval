from __future__ import annotations

from pathlib import Path

from phthos_eval import SCHEMA_VERSION, validate_diagnosis
from phthos_eval.schema import load_schema, schema_file

ROOT = Path(__file__).resolve().parents[1]


def test_package_schema_loads() -> None:
    schema = load_schema()
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert schema_file().is_file()


def test_root_schema_matches_package() -> None:
    root = (ROOT / "schema" / f"diagnosis.v{SCHEMA_VERSION}.json").read_text(encoding="utf-8")
    pkg = schema_file().read_text(encoding="utf-8")
    assert root == pkg


def test_gold_schema_matches_package() -> None:
    root = (ROOT / "schema" / "gold.v1.json").read_text(encoding="utf-8")
    pkg = (ROOT / "src" / "phthos_eval" / "data" / "gold.v1.json").read_text(encoding="utf-8")
    assert root == pkg


def test_validate_rejects_bad_change_class() -> None:
    errors = validate_diagnosis(
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": "x",
            "dataset_id": "x",
            "n_runs": 1,
            "scores": {
                "task_success": 1,
                "n_run_reliability": 1,
                "pass_at_n": 1,
                "cost": 0,
                "cost_mean": 0,
                "latency_ms": 0,
                "latency_mean_ms": 0,
                "latency_p50_ms": 0,
                "latency_p95_ms": 0,
                "steps": 0,
                "steps_mean": 0,
                "tokens": None,
                "policy_hits": 0,
                "wrong_tool_hits": 0,
                "budget_hits": 0,
                "loop_hits": 0,
            },
            "failures": [],
            "change_class": "not-a-class",
            "evidence": [],
            "judge": {"skipped": True},
            "gold_version": None,
            "gold_stale": False,
        }
    )
    assert any("change_class" in e for e in errors)


def test_validate_rejects_missing_span() -> None:
    errors = validate_diagnosis({"schema_version": SCHEMA_VERSION})
    assert any("missing" in e for e in errors)
