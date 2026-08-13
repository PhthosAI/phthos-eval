from __future__ import annotations

from phthos_eval.metrics import percentile
from phthos_eval.runner import run_dataset
from phthos_eval.schema import validate_diagnosis


def _ok_trace() -> dict:
    return {
        "spans": [
            {
                "id": "s0",
                "type": "tool",
                "name": "search",
                "args": {"query": "q"},
                "cost_usd": 0.01,
                "latency_ms": 10,
                "tokens": 20,
            }
        ]
    }


def _bad_trace() -> dict:
    return {
        "spans": [
            {
                "id": "s0",
                "type": "tool",
                "name": "lookup",
                "args": {"q": "q"},
                "cost_usd": 0.02,
                "latency_ms": 100,
            }
        ]
    }


def test_percentile_nearest_rank() -> None:
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([1, 2, 3, 4, 5], 95) == 5
    assert percentile([], 95) is None


def test_pass_at_n_and_reliability_split() -> None:
    """Industry split: pass^N vs mean pass-rate vs pass@N (Chen et al. / codegen)."""
    dataset = {
        "id": "mix",
        "n_runs": 2,
        "cases": [
            {
                "id": "always",
                "expected_tools": ["search"],
                "traces": [_ok_trace(), _ok_trace()],
            },
            {
                "id": "flaky",
                "expected_tools": ["search"],
                "traces": [_ok_trace(), _bad_trace()],
            },
        ],
    }
    doc = run_dataset(dataset, judge=False)
    assert validate_diagnosis(doc) == []
    scores = doc["scores"]
    assert scores["task_success"] == 0.5
    assert scores["n_run_reliability"] == 0.75
    assert scores["pass_at_n"] == 1.0
    assert scores["wrong_tool_hits"] == 1
    assert scores["tokens"] == 60
    by_id = {c["case_id"]: c for c in doc["cases"]}
    assert by_id["always"]["pass_rate"] == 1.0
    assert by_id["flaky"]["pass_rate"] == 0.5
    assert by_id["flaky"]["passed"] is False
    assert scores["latency_p95_ms"] == 100
    assert scores["cost_mean"] == 0.0125
    assert scores["steps"] == 4
    assert scores["steps_mean"] == 1.0
