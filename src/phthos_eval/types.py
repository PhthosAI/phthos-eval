from __future__ import annotations

from typing import Any


def pointer(
    span_id: str,
    *,
    step_id: str | None = None,
    case_id: str | None = None,
    trace_index: int | None = None,
) -> dict[str, Any]:
    return {
        "span_id": span_id,
        "step_id": step_id,
        "case_id": case_id,
        "trace_index": trace_index,
    }


def failure(
    type_: str,
    span_id: str,
    *,
    step_id: str | None = None,
    case_id: str | None = None,
    trace_index: int | None = None,
) -> dict[str, Any]:
    return {
        "type": type_,
        "span_id": span_id,
        "evidence": pointer(
            span_id,
            step_id=step_id,
            case_id=case_id,
            trace_index=trace_index,
        ),
    }
