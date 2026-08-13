from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from phthos_eval.constants import FAILURE_TO_CHANGE_CLASS, SCHEMA_VERSION
from phthos_eval.judge import maybe_judge
from phthos_eval.metrics import (
    mean,
    percentile,
    round_opt,
    trace_cost,
    trace_latency_ms,
    trace_steps,
    trace_tokens,
)
from phthos_eval.schema import validate_diagnosis
from phthos_eval.scorers import score_trace
from phthos_eval.types import Scorer


def run_dataset(
    dataset: dict[str, Any],
    *,
    scorers: Sequence[Scorer] | None = None,
    run_id: str | None = None,
    judge: bool | dict[str, Any] = True,
) -> dict[str, Any]:
    n_runs = int(dataset.get("n_runs") or 2)
    if n_runs < 1:
        raise ValueError("n_runs must be >= 1")

    case_rows: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []
    costs: list[float] = []
    latencies: list[float] = []
    steps_list: list[int] = []
    token_parts: list[float] = []
    pass_flags: list[bool] = []
    case_pass_rates: list[float] = []
    case_any_pass: list[bool] = []

    for case in dataset.get("cases") or []:
        case_id = str(case["id"])
        traces = case.get("traces") or []
        if len(traces) < n_runs:
            raise ValueError(f"case {case_id} needs at least {n_runs} traces")
        case_failures: list[dict[str, Any]] = []
        trace_passes = 0
        case_cost = 0.0
        case_latency = 0.0
        case_steps = 0
        for idx in range(n_runs):
            trace = traces[idx]
            cost = trace_cost(trace)
            latency = trace_latency_ms(trace)
            steps = trace_steps(trace)
            costs.append(cost)
            latencies.append(latency)
            steps_list.append(steps)
            case_cost += cost
            case_latency += latency
            case_steps += steps
            tok = trace_tokens(trace)
            if tok is not None:
                token_parts.append(tok)
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
        pass_rate = trace_passes / n_runs
        pass_flags.append(passed)
        case_pass_rates.append(pass_rate)
        case_any_pass.append(trace_passes >= 1)
        all_failures.extend(case_failures)
        case_rows.append(
            {
                "case_id": case_id,
                "passed": passed,
                "pass_rate": pass_rate,
                "cost": round(case_cost, 6),
                "latency_ms": round(case_latency, 3),
                "steps": case_steps,
                "failures": case_failures,
            }
        )

    n_cases = len(pass_flags)
    task_success = (sum(1 for p in pass_flags if p) / n_cases) if n_cases else None
    reliability = mean(case_pass_rates)
    pass_at_n = (sum(1 for p in case_any_pass if p) / n_cases) if n_cases else None
    hits = {
        name: sum(1 for f in all_failures if f["type"] == name)
        for name in ("policy", "wrong_tool", "budget", "loop")
    }

    diagnosis: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or str(uuid.uuid4()),
        "dataset_id": str(dataset.get("id") or "unnamed"),
        "n_runs": n_runs,
        "scores": {
            "task_success": round_opt(task_success, 6),
            "n_run_reliability": round_opt(reliability, 6),
            "pass_at_n": round_opt(pass_at_n, 6),
            "cost": round(sum(costs), 6) if costs else None,
            "cost_mean": round_opt(mean(costs), 6),
            "latency_ms": round(sum(latencies), 3) if latencies else None,
            "latency_mean_ms": round_opt(mean(latencies), 3),
            "latency_p50_ms": round_opt(percentile(latencies, 50), 3),
            "latency_p95_ms": round_opt(percentile(latencies, 95), 3),
            "steps": sum(steps_list) if steps_list else None,
            "steps_mean": round_opt(mean([float(s) for s in steps_list]), 3),
            "tokens": round(sum(token_parts), 3) if token_parts else None,
            "policy_hits": hits["policy"],
            "wrong_tool_hits": hits["wrong_tool"],
            "budget_hits": hits["budget"],
            "loop_hits": hits["loop"],
        },
        "failures": all_failures,
        "change_class": _change_class(all_failures),
        "evidence": [f["evidence"] for f in all_failures],
        "judge": {"skipped": True, "reason": "pending", "score": None, "error": None},
        "cases": case_rows,
    }
    if judge is False:
        diagnosis["judge"] = {
            "skipped": True,
            "reason": "disabled",
            "score": None,
            "error": None,
        }
    elif isinstance(judge, dict):
        diagnosis["judge"] = maybe_judge(
            diagnosis,
            api_key=judge.get("api_key"),
            base_url=judge.get("base_url"),
            model=judge.get("model"),
        )
    else:
        diagnosis["judge"] = maybe_judge(diagnosis)
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
