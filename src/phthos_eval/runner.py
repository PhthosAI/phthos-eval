from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from phthos_eval.constants import FAILURE_TO_CHANGE_CLASS, SCHEMA_VERSION
from phthos_eval.judge import maybe_judge
from phthos_eval.schema import validate_diagnosis
from phthos_eval.scorers import score_trace
from phthos_eval.types import Scorer


def run_dataset(
    dataset: dict[str, Any],
    *,
    scorers: Sequence[Scorer] | None = None,
    run_id: str | None = None,
    judge: bool = True,
) -> dict[str, Any]:
    n_runs = int(dataset.get("n_runs") or 2)
    if n_runs < 1:
        raise ValueError("n_runs must be >= 1")

    case_rows: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []
    costs: list[float] = []
    latencies: list[float] = []
    pass_flags: list[bool] = []

    for case in dataset.get("cases") or []:
        case_id = str(case["id"])
        traces = case.get("traces") or []
        if len(traces) < n_runs:
            raise ValueError(f"case {case_id} needs at least {n_runs} traces")
        case_failures: list[dict[str, Any]] = []
        trace_passes = 0
        for idx in range(n_runs):
            trace = traces[idx]
            spans = trace.get("spans") or []
            costs.append(sum(float(s.get("cost_usd") or 0) for s in spans))
            latencies.append(sum(float(s.get("latency_ms") or 0) for s in spans))
            fails = score_trace(
                trace,
                case=case,
                dataset=dataset,
                case_id=case_id,
                trace_index=idx,
                scorers=list(scorers) if scorers is not None else None,
            )
            if not fails:
                trace_passes += 1
            case_failures.extend(fails)
        passed = trace_passes == n_runs
        pass_flags.append(passed)
        all_failures.extend(case_failures)
        case_rows.append(
            {
                "case_id": case_id,
                "passed": passed,
                "failures": case_failures,
            }
        )

    reliability = (sum(1 for p in pass_flags if p) / len(pass_flags)) if pass_flags else None
    policy_hits = sum(1 for f in all_failures if f["type"] == "policy")
    change_class = _change_class(all_failures)
    evidence = [f["evidence"] for f in all_failures]

    diagnosis: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or str(uuid.uuid4()),
        "dataset_id": str(dataset.get("id") or "unnamed"),
        "n_runs": n_runs,
        "scores": {
            "task_success": reliability,
            "cost": round(sum(costs), 6) if costs else None,
            "latency_ms": round(sum(latencies), 3) if latencies else None,
            "policy_hits": policy_hits,
            "n_run_reliability": reliability,
        },
        "failures": all_failures,
        "change_class": change_class,
        "evidence": evidence,
        "judge": {"skipped": True, "reason": "pending", "score": None, "error": None},
        "cases": case_rows,
    }
    if judge:
        diagnosis["judge"] = maybe_judge(diagnosis)
    else:
        diagnosis["judge"] = {
            "skipped": True,
            "reason": "disabled",
            "score": None,
            "error": None,
        }
    errors = validate_diagnosis(diagnosis)
    if errors:
        raise ValueError("invalid diagnosis: " + "; ".join(errors))
    return diagnosis


def _change_class(failures: list[dict[str, Any]]) -> str:
    if not failures:
        return "none"
    order = ("policy", "wrong_tool", "budget", "loop")
    types = {f["type"] for f in failures}
    for t in order:
        if t in types:
            return FAILURE_TO_CHANGE_CLASS[t]
    return "none"


def write_diagnosis(diagnosis: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diagnosis, indent=2) + "\n", encoding="utf-8")
