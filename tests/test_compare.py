from __future__ import annotations

import json
from pathlib import Path

from phthos_eval.compare import compare_diagnoses


def test_compare_same_cases_delta() -> None:
    before = {
        "schema_version": "0.2.0",
        "run_id": "a",
        "change_class": "tool",
        "scores": {"task_success": 0.5, "n_run_reliability": 0.5},
        "cases": [
            {"case_id": "ok", "passed": True},
            {"case_id": "bad", "passed": False},
        ],
    }
    after = {
        "schema_version": "0.2.0",
        "run_id": "b",
        "change_class": "none",
        "scores": {"task_success": 1.0, "n_run_reliability": 1.0},
        "cases": [
            {"case_id": "ok", "passed": True},
            {"case_id": "bad", "passed": True},
        ],
    }
    doc = compare_diagnoses(before, after)
    assert doc["before_run_id"] == "a"
    assert doc["after_run_id"] == "b"
    assert doc["task_success_delta"] == 0.5
    assert doc["n_run_reliability_delta"] == 0.5
    by_id = {r["case_id"]: r for r in doc["cases"]}
    assert by_id["bad"]["before_passed"] is False
    assert by_id["bad"]["after_passed"] is True


def test_cli_compare(tmp_path: Path) -> None:
    from phthos_eval.cli import main

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    out = tmp_path / "cmp.json"
    before.write_text(
        json.dumps(
            {
                "run_id": "a",
                "scores": {"task_success": 0.0},
                "cases": [{"case_id": "c", "passed": False}],
            }
        ),
        encoding="utf-8",
    )
    after.write_text(
        json.dumps(
            {
                "run_id": "b",
                "scores": {"task_success": 1.0},
                "cases": [{"case_id": "c", "passed": True}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["compare", "--before", str(before), "--after", str(after), "-o", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["task_success_delta"] == 1.0
