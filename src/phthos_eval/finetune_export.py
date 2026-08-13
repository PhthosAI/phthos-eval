from __future__ import annotations

from typing import Any

from phthos_eval.constants import SCHEMA_VERSION

FINETUNE_FORMAT = "phthos-eval-finetune.v1"


def labeled_trajectories(
    dataset: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    """Pass/fail traces + evidence for *their* fine-tune stack. This product does not train."""
    by_case = {str(c["id"]): c for c in dataset.get("cases") or []}
    rows: list[dict[str, Any]] = []
    for case in diagnosis.get("cases") or []:
        src = by_case.get(str(case["case_id"])) or {}
        passed = bool(case.get("passed"))
        rows.append(
            {
                "case_id": case["case_id"],
                "passed": passed,
                "failures": case.get("failures") or [],
                "evidence": [f.get("evidence") for f in (case.get("failures") or [])],
                "traces": list(src.get("traces") or []),
                "change_class": "none" if passed else diagnosis.get("change_class"),
            }
        )
    return {
        "format": FINETUNE_FORMAT,
        "schema_version": diagnosis.get("schema_version") or SCHEMA_VERSION,
        "dataset_id": diagnosis.get("dataset_id") or dataset.get("id"),
        "run_id": diagnosis.get("run_id"),
        "note": (
            "Labeled trajectories for an external fine-tune / RL stack. "
            "phthos-eval does not train, update weights, or apply the agent fix."
        ),
        "rows": rows,
    }
