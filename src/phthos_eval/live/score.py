from __future__ import annotations

from typing import Any

from phthos_eval.runner import run_dataset


def score_one_trace(
    trace: dict[str, Any],
    *,
    config: dict[str, Any],
    case_id: str,
    expected_tools: list[str] | None = None,
    run_id: str | None = None,
    judge: bool = False,
) -> dict[str, Any]:
    """Score one live trace with the same runner and scorers as offline."""
    tools = expected_tools
    if tools is None:
        tools = list(config.get("default_expected_tools") or [])
    dataset = {
        "id": str(config.get("id") or "live"),
        "n_runs": 1,
        "budget": config.get("budget") or {},
        "policy": config.get("policy") or {},
        "tool_schemas": config.get("tool_schemas") or {},
        "cases": [
            {
                "id": case_id,
                "expected_tools": tools,
                "traces": [trace],
            }
        ],
    }
    return run_dataset(dataset, run_id=run_id, judge=judge)
