"""Phthos Eval — offline runner and live engine (self-host or hosted)."""

from phthos_eval.compare import compare_diagnoses
from phthos_eval.constants import (
    CHANGE_CLASSES,
    FAILURE_TO_CHANGE_CLASS,
    FAILURE_TYPES,
    SCHEMA_VERSION,
)
from phthos_eval.finetune_export import labeled_trajectories
from phthos_eval.gold import as_dataset, build_pack, pack_to_dataset, validate_gold_pack
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
from phthos_eval.sink import TraceSink, instrument
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
    "TraceSink",
    "WrongToolScorer",
    "as_dataset",
    "build_pack",
    "compare_diagnoses",
    "default_scorers",
    "failure",
    "instrument",
    "labeled_trajectories",
    "load_schema",
    "pack_to_dataset",
    "pointer",
    "run_dataset",
    "schema_file",
    "score_trace",
    "validate_diagnosis",
    "validate_gold_pack",
    "write_diagnosis",
]

