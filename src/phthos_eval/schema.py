from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phthos_eval.constants import CHANGE_CLASSES, FAILURE_TYPES, SCHEMA_VERSION

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
    "gold_version",
    "gold_stale",
)
REQUIRED_SCORES = (
    "task_success",
    "n_run_reliability",
    "pass_at_n",
    "cost",
    "cost_mean",
    "latency_ms",
    "latency_mean_ms",
    "latency_p50_ms",
    "latency_p95_ms",
    "steps",
    "steps_mean",
    "tokens",
    "policy_hits",
    "wrong_tool_hits",
    "budget_hits",
    "loop_hits",
)


def schema_file() -> Path:
    pkg = Path(__file__).resolve().parent / "data" / SCHEMA_FILENAME
    candidates = [
        pkg,
        Path.cwd() / "schema" / SCHEMA_FILENAME,
        Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Diagnosis schema {SCHEMA_FILENAME} not found. Reinstall phthos-eval."
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
    if "gold_version" in doc and doc.get("gold_version") is not None and not isinstance(doc.get("gold_version"), str):
        errors.append("gold_version must be string or null")
    if not isinstance(doc.get("gold_stale"), bool):
        errors.append("gold_stale must be a boolean")
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
