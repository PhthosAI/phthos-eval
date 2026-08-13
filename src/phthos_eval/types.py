from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict

ChangeClass = Literal["prompt", "tool", "policy", "model", "finetune_data", "none"]
FailureType = Literal["wrong_tool", "loop", "budget", "policy"]


class EvidencePointer(TypedDict):
    span_id: str
    step_id: str | None
    case_id: str | None
    trace_index: int | None


class Failure(TypedDict):
    type: FailureType
    span_id: str
    evidence: EvidencePointer


class Scores(TypedDict):
    task_success: float | None
    cost: float | None
    latency_ms: float | None
    policy_hits: int | None
    n_run_reliability: float | None


class JudgeResult(TypedDict):
    skipped: bool
    reason: str | None
    score: float | None
    error: str | None


class CaseResult(TypedDict):
    case_id: str
    passed: bool
    failures: list[Failure]


class Diagnosis(TypedDict):
    schema_version: str
    run_id: str
    dataset_id: str
    n_runs: int
    scores: Scores
    failures: list[Failure]
    change_class: ChangeClass
    evidence: list[EvidencePointer]
    judge: JudgeResult
    cases: list[CaseResult]


class Scorer(Protocol):
    """Deterministic scorer. Return typed failures; never call an LLM here."""

    def score(
        self,
        trace: dict[str, Any],
        *,
        case: dict[str, Any],
        dataset: dict[str, Any],
        case_id: str,
        trace_index: int,
    ) -> list[Failure]: ...


def pointer(
    span_id: str,
    *,
    step_id: str | None = None,
    case_id: str | None = None,
    trace_index: int | None = None,
) -> EvidencePointer:
    return {
        "span_id": span_id,
        "step_id": step_id,
        "case_id": case_id,
        "trace_index": trace_index,
    }


def failure(
    type_: FailureType,
    span_id: str,
    *,
    step_id: str | None = None,
    case_id: str | None = None,
    trace_index: int | None = None,
) -> Failure:
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
