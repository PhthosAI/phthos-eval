from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phthos_eval import SCHEMA_VERSION, CHANGE_CLASSES, FAILURE_TYPES

SCHEMA_FILENAME = f"diagnosis.v{SCHEMA_VERSION}.json"

REQUIRED_TOP = (
    "schema_version",
    "run_id",
    "dataset_id",
    "n_runs",
    "scores",
    "failures",
    "change_class",
    "evidence",
    "judge",
)
REQUIRED_SCORES = (
    "task_success",
    "cost",
    "latency_ms",
    "policy_hits",
    "n_run_reliability",
)


def schema_file() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "schema" / SCHEMA_FILENAME,
        here.parents[2] / "schema" / SCHEMA_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Diagnosis schema {SCHEMA_FILENAME} not found. Run from the repo root."
    )


def load_schema() -> dict[str, Any]:
    return json.loads(schema_file().read_text(encoding="utf-8"))


def validate_diagnosis(doc: dict[str, Any]) -> list[str]:
    """Return human-readable errors. Empty list means OK. No extra deps."""
    errors: list[str] = []
    for key in REQUIRED_TOP:
        if key not in doc:
            errors.append(f"missing {key}")
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION}, got {doc.get('schema_version')!r}"
        )
    if doc.get("change_class") not in CHANGE_CLASSES:
        errors.append(f"invalid change_class {doc.get('change_class')!r}")
    n_runs = doc.get("n_runs")
    if not isinstance(n_runs, int) or n_runs < 1:
        errors.append("n_runs must be int >= 1")
    scores = doc.get("scores")
    if not isinstance(scores, dict):
        errors.append("scores must be an object")
    else:
        for key in REQUIRED_SCORES:
            if key not in scores:
                errors.append(f"missing scores.{key}")
    failures = doc.get("failures")
    if not isinstance(failures, list):
        errors.append("failures must be an array")
    else:
        for i, fail in enumerate(failures):
            errors.extend(_failure_errors(f"failures[{i}]", fail))
    evidence = doc.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be an array")
    else:
        for i, ptr in enumerate(evidence):
            errors.extend(_pointer_errors(f"evidence[{i}]", ptr))
    judge = doc.get("judge")
    if not isinstance(judge, dict) or "skipped" not in judge:
        errors.append("judge.skipped is required")
    return errors


def _failure_errors(prefix: str, fail: Any) -> list[str]:
    if not isinstance(fail, dict):
        return [f"{prefix} must be an object"]
    errors: list[str] = []
    if fail.get("type") not in FAILURE_TYPES:
        errors.append(f"{prefix}.type invalid")
    if not fail.get("span_id"):
        errors.append(f"{prefix}.span_id required")
    errors.extend(_pointer_errors(f"{prefix}.evidence", fail.get("evidence")))
    return errors


def _pointer_errors(prefix: str, ptr: Any) -> list[str]:
    if not isinstance(ptr, dict):
        return [f"{prefix} must be an object"]
    if not ptr.get("span_id"):
        return [f"{prefix}.span_id required"]
    return []
