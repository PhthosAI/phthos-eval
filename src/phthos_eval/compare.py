from __future__ import annotations

from typing import Any


def compare_diagnoses(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Same-case before/after. Eval does not apply the change — the consumer does."""
    before_cases = {str(c["case_id"]): c for c in before.get("cases") or []}
    after_cases = {str(c["case_id"]): c for c in after.get("cases") or []}
    ids = sorted(set(before_cases) | set(after_cases))
    rows: list[dict[str, Any]] = []
    for case_id in ids:
        b = before_cases.get(case_id)
        a = after_cases.get(case_id)
        rows.append(
            {
                "case_id": case_id,
                "before_passed": None if b is None else bool(b.get("passed")),
                "after_passed": None if a is None else bool(a.get("passed")),
            }
        )
    b_scores = before.get("scores") or {}
    a_scores = after.get("scores") or {}

    def _delta(key: str) -> float | None:
        bv, av = b_scores.get(key), a_scores.get(key)
        if bv is None or av is None:
            return None
        return round(float(av) - float(bv), 6)

    return {
        "schema_version": after.get("schema_version") or before.get("schema_version"),
        "before_run_id": before.get("run_id"),
        "after_run_id": after.get("run_id"),
        "before_change_class": before.get("change_class"),
        "after_change_class": after.get("change_class"),
        "task_success_delta": _delta("task_success"),
        "n_run_reliability_delta": _delta("n_run_reliability"),
        "cases": rows,
    }
