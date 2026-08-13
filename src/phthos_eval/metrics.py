from __future__ import annotations

import math
from typing import Any

from phthos_eval.scorers import tool_spans


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile. p=50 median, p=95 SLA tail. Empty → None."""
    if not values:
        return None
    xs = sorted(values)
    if p <= 0:
        return xs[0]
    if p >= 100:
        return xs[-1]
    rank = math.ceil(p / 100.0 * len(xs)) - 1
    return xs[max(0, min(rank, len(xs) - 1))]


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def trace_cost(trace: dict[str, Any]) -> float:
    return sum(float(s.get("cost_usd") or 0) for s in trace.get("spans") or [])


def trace_latency_ms(trace: dict[str, Any]) -> float:
    return sum(float(s.get("latency_ms") or 0) for s in trace.get("spans") or [])


def trace_steps(trace: dict[str, Any]) -> int:
    return len(tool_spans(trace.get("spans") or []))


def trace_tokens(trace: dict[str, Any]) -> float | None:
    total = 0.0
    seen = False
    for span in trace.get("spans") or []:
        raw = _span_tokens(span)
        if raw is None:
            continue
        seen = True
        total += raw
    return total if seen else None


def _span_tokens(span: dict[str, Any]) -> float | None:
    if span.get("tokens") is not None:
        return float(span["tokens"])
    inn = span.get("input_tokens")
    out = span.get("output_tokens")
    if inn is None and out is None:
        return None
    return float(inn or 0) + float(out or 0)


def round_opt(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(value, digits)
