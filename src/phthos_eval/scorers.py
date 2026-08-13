from __future__ import annotations

from collections import Counter
from typing import Any

from phthos_eval.types import Failure, Scorer, failure


def tool_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in spans if (s.get("type") or s.get("kind")) == "tool"]


class WrongToolScorer:
    def score(
        self,
        trace: dict[str, Any],
        *,
        case: dict[str, Any],
        dataset: dict[str, Any],
        case_id: str,
        trace_index: int,
    ) -> list[Failure]:
        expected = set(case.get("expected_tools") or [])
        if not expected:
            return []
        out: list[Failure] = []
        for i, span in enumerate(tool_spans(trace.get("spans") or [])):
            name = span.get("name") or span.get("tool")
            if name not in expected:
                out.append(
                    failure(
                        "wrong_tool",
                        str(span.get("id") or f"step-{i}"),
                        step_id=str(i),
                        case_id=case_id,
                        trace_index=trace_index,
                    )
                )
        return out


class ToolSchemaScorer:
    def score(
        self,
        trace: dict[str, Any],
        *,
        case: dict[str, Any],
        dataset: dict[str, Any],
        case_id: str,
        trace_index: int,
    ) -> list[Failure]:
        schemas: dict[str, Any] = dataset.get("tool_schemas") or {}
        out: list[Failure] = []
        for i, span in enumerate(tool_spans(trace.get("spans") or [])):
            name = span.get("name") or span.get("tool")
            spec = schemas.get(name)
            if not spec:
                continue
            args = span.get("args") or span.get("arguments") or {}
            required = spec.get("required") or []
            if not isinstance(args, dict) or any(key not in args for key in required):
                out.append(
                    failure(
                        "wrong_tool",
                        str(span.get("id") or f"step-{i}"),
                        step_id=str(i),
                        case_id=case_id,
                        trace_index=trace_index,
                    )
                )
        return out


class BudgetScorer:
    def score(
        self,
        trace: dict[str, Any],
        *,
        case: dict[str, Any],
        dataset: dict[str, Any],
        case_id: str,
        trace_index: int,
    ) -> list[Failure]:
        spans = trace.get("spans") or []
        budget = dataset.get("budget") or {}
        max_cost = budget.get("max_cost_usd")
        max_steps = budget.get("max_steps")
        cost = sum(float(s.get("cost_usd") or 0) for s in spans)
        steps = len(tool_spans(spans))
        out: list[Failure] = []
        if max_cost is not None and cost > float(max_cost):
            span = spans[-1] if spans else {}
            out.append(
                failure(
                    "budget",
                    str(span.get("id") or "trace"),
                    step_id=str(len(spans) - 1) if spans else "0",
                    case_id=case_id,
                    trace_index=trace_index,
                )
            )
        if max_steps is not None and steps > int(max_steps):
            tools = tool_spans(spans)
            span = tools[-1] if tools else (spans[-1] if spans else {})
            out.append(
                failure(
                    "budget",
                    str(span.get("id") or "trace"),
                    step_id=str(len(spans) - 1) if spans else "0",
                    case_id=case_id,
                    trace_index=trace_index,
                )
            )
        return out


class PolicyScorer:
    def score(
        self,
        trace: dict[str, Any],
        *,
        case: dict[str, Any],
        dataset: dict[str, Any],
        case_id: str,
        trace_index: int,
    ) -> list[Failure]:
        deny = set((dataset.get("policy") or {}).get("deny_tools") or [])
        if not deny:
            return []
        out: list[Failure] = []
        for i, span in enumerate(tool_spans(trace.get("spans") or [])):
            name = span.get("name") or span.get("tool")
            if name in deny:
                out.append(
                    failure(
                        "policy",
                        str(span.get("id") or f"step-{i}"),
                        step_id=str(i),
                        case_id=case_id,
                        trace_index=trace_index,
                    )
                )
        return out


class LoopScorer:
    def score(
        self,
        trace: dict[str, Any],
        *,
        case: dict[str, Any],
        dataset: dict[str, Any],
        case_id: str,
        trace_index: int,
    ) -> list[Failure]:
        tools = tool_spans(trace.get("spans") or [])
        keys = [
            (s.get("name") or s.get("tool"), _freeze(s.get("args") or s.get("arguments")))
            for s in tools
        ]
        counts = Counter(keys)
        out: list[Failure] = []
        seen: set[Any] = set()
        for i, (span, key) in enumerate(zip(tools, keys)):
            if counts[key] >= 3 and key not in seen:
                seen.add(key)
                out.append(
                    failure(
                        "loop",
                        str(span.get("id") or f"step-{i}"),
                        step_id=str(i),
                        case_id=case_id,
                        trace_index=trace_index,
                    )
                )
        return out


def default_scorers() -> list[Scorer]:
    return [
        WrongToolScorer(),
        ToolSchemaScorer(),
        BudgetScorer(),
        PolicyScorer(),
        LoopScorer(),
    ]


def score_trace(
    trace: dict[str, Any],
    *,
    case: dict[str, Any],
    dataset: dict[str, Any],
    case_id: str,
    trace_index: int,
    scorers: list[Scorer] | None = None,
) -> list[Failure]:
    found: list[Failure] = []
    for scorer in scorers or default_scorers():
        found.extend(
            scorer.score(
                trace,
                case=case,
                dataset=dataset,
                case_id=case_id,
                trace_index=trace_index,
            )
        )
    return found


def _freeze(args: Any) -> str:
    if isinstance(args, dict):
        return repr(sorted(args.items()))
    return repr(args)
