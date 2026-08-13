"""Phthos Eval — offline runner and live engine (self-host or hosted)."""

from phthos_eval.constants import (
    CHANGE_CLASSES,
    FAILURE_TO_CHANGE_CLASS,
    FAILURE_TYPES,
    SCHEMA_VERSION,
)
from phthos_eval.runner import run_dataset, write_diagnosis
from phthos_eval.schema import load_schema, schema_file, validate_diagnosis
from phthos_eval.scorers import (
    BudgetScorer,
    LoopScorer,
    PolicyScorer,
    ToolSchemaScorer,
    WrongToolScorer,
    default_scorers,
    score_trace,
)
from phthos_eval.types import (
    CaseResult,
    ChangeClass,
    Diagnosis,
    EvidencePointer,
    Failure,
    FailureType,
    JudgeResult,
    Scorer,
    Scores,
    failure,
    pointer,
)

__all__ = [
    "CHANGE_CLASSES",
    "FAILURE_TO_CHANGE_CLASS",
    "FAILURE_TYPES",
    "SCHEMA_VERSION",
    "BudgetScorer",
    "CaseResult",
    "ChangeClass",
    "Diagnosis",
    "EvidencePointer",
    "Failure",
    "FailureType",
    "JudgeResult",
    "LoopScorer",
    "PolicyScorer",
    "Scorer",
    "Scores",
    "ToolSchemaScorer",
    "WrongToolScorer",
    "default_scorers",
    "failure",
    "load_schema",
    "pointer",
    "run_dataset",
    "schema_file",
    "score_trace",
    "validate_diagnosis",
    "write_diagnosis",
]
