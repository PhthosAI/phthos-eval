from __future__ import annotations

from phthos_eval import BudgetScorer, LoopScorer, PolicyScorer, WrongToolScorer, failure
from phthos_eval.runner import run_dataset
from phthos_eval.scorers import score_trace


def _trace(*tools: str, cost: float = 0.0, args: dict | None = None) -> dict:
    spans = [
        {
            "id": f"s{i}",
            "type": "tool",
            "name": name,
            "args": args or {"query": "q"},
            "cost_usd": cost,
            "latency_ms": 1,
        }
        for i, name in enumerate(tools)
    ]
    return {"spans": spans}


def test_wrong_tool() -> None:
    fails = WrongToolScorer().score(
        _trace("lookup"),
        case={"expected_tools": ["search"]},
        dataset={},
        case_id="c",
        trace_index=0,
    )
    assert len(fails) == 1
    assert fails[0]["type"] == "wrong_tool"
    assert fails[0]["span_id"] == "s0"


def test_policy() -> None:
    fails = PolicyScorer().score(
        _trace("send_money"),
        case={},
        dataset={"policy": {"deny_tools": ["send_money"]}},
        case_id="c",
        trace_index=0,
    )
    assert fails[0]["type"] == "policy"


def test_budget() -> None:
    fails = BudgetScorer().score(
        _trace("search", cost=1.0),
        case={},
        dataset={"budget": {"max_cost_usd": 0.05}},
        case_id="c",
        trace_index=0,
    )
    assert fails[0]["type"] == "budget"


def test_loop() -> None:
    fails = LoopScorer().score(
        _trace("search", "search", "search"),
        case={},
        dataset={},
        case_id="c",
        trace_index=0,
    )
    assert fails[0]["type"] == "loop"


def test_custom_scorer_is_used() -> None:
    class AlwaysFail:
        def score(self, trace, *, case, dataset, case_id, trace_index):
            return [failure("policy", "custom", case_id=case_id, trace_index=trace_index)]

    dataset = {
        "id": "custom",
        "n_runs": 2,
        "cases": [
            {
                "id": "a",
                "expected_tools": ["search"],
                "traces": [_trace("search"), _trace("search")],
            }
        ],
    }
    doc = run_dataset(dataset, scorers=[AlwaysFail()])
    assert doc["failures"][0]["span_id"] == "custom"
    assert doc["change_class"] == "policy"


def test_score_trace_default_empty_pass() -> None:
    fails = score_trace(
        _trace("search"),
        case={"expected_tools": ["search"]},
        dataset={"tool_schemas": {"search": {"required": ["query"]}}},
        case_id="c",
        trace_index=0,
    )
    assert fails == []
