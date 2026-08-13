from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

GOLD_SCHEMA_VERSION = "1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return digest[:16]


def source_hashes(
    *,
    tool_schemas: Any = None,
    policy: Any = None,
    sop: Any = None,
) -> dict[str, str]:
    return {
        "tools": content_hash(tool_schemas or {}),
        "policy": content_hash(policy or {}),
        "sop": content_hash(sop if sop is not None else ""),
    }


def pack_version(hashes: dict[str, str], *, n_cases: int = 0) -> str:
    joined = f"{hashes['tools']}:{hashes['policy']}:{hashes['sop']}"
    base = "g_" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
    if n_cases:
        return f"{base}.c{n_cases}"
    return base


def is_gold_pack(doc: dict[str, Any]) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("schema_version") == GOLD_SCHEMA_VERSION
        and isinstance(doc.get("agent_id"), str)
        and isinstance(doc.get("source_hashes"), dict)
        and isinstance(doc.get("cases"), list)
    )


def validate_gold_pack(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["gold pack must be an object"]
    for key in (
        "schema_version",
        "agent_id",
        "version",
        "created_at",
        "tool_schemas",
        "policy",
        "budget",
        "sop_hash",
        "source_hashes",
        "cases",
    ):
        if key not in doc:
            errors.append(f"missing {key}")
    if doc.get("schema_version") != GOLD_SCHEMA_VERSION:
        errors.append(f"schema_version must be {GOLD_SCHEMA_VERSION}")
    hashes = doc.get("source_hashes")
    if not isinstance(hashes, dict):
        errors.append("source_hashes must be an object")
    else:
        for key in ("tools", "policy", "sop"):
            if not hashes.get(key):
                errors.append(f"missing source_hashes.{key}")
    if not isinstance(doc.get("cases"), list):
        errors.append("cases must be an array")
    if not str(doc.get("agent_id") or "").strip():
        errors.append("agent_id required")
    return errors


def build_pack(
    *,
    agent_id: str,
    tool_schemas: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    sop: Any = None,
    sop_clauses: Any = None,
    cases: list[dict[str, Any]] | None = None,
    default_expected_tools: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    schemas = tool_schemas if isinstance(tool_schemas, dict) else {}
    pol = policy if isinstance(policy, dict) else {}
    bud = budget if isinstance(budget, dict) else {}
    sop_body = sop_clauses if sop_clauses is not None else sop
    hashes = source_hashes(tool_schemas=schemas, policy=pol, sop=sop_body)
    case_list = list(cases or [])
    pack: dict[str, Any] = {
        "schema_version": GOLD_SCHEMA_VERSION,
        "agent_id": agent_id.strip(),
        "version": pack_version(hashes, n_cases=len(case_list)),
        "created_at": created_at or _now(),
        "tool_schemas": schemas,
        "policy": pol,
        "budget": bud,
        "sop_hash": hashes["sop"],
        "sop_clauses": sop_body,
        "source_hashes": hashes,
        "cases": case_list,
    }
    if default_expected_tools is not None:
        pack["default_expected_tools"] = list(default_expected_tools)
    errors = validate_gold_pack(pack)
    if errors:
        raise ValueError("invalid gold pack: " + "; ".join(errors))
    return pack


def pack_from_body(agent_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return build_pack(
        agent_id=str(body.get("agent_id") or agent_id),
        tool_schemas=body.get("tool_schemas") if isinstance(body.get("tool_schemas"), dict) else {},
        policy=body.get("policy") if isinstance(body.get("policy"), dict) else {},
        budget=body.get("budget") if isinstance(body.get("budget"), dict) else {},
        sop=body.get("sop"),
        sop_clauses=body.get("sop_clauses"),
        cases=list(body["cases"]) if isinstance(body.get("cases"), list) else [],
        default_expected_tools=(
            list(body["default_expected_tools"])
            if isinstance(body.get("default_expected_tools"), list)
            else None
        ),
    )


def pack_to_dataset(pack: dict[str, Any]) -> dict[str, Any]:
    counts = [
        len(case.get("traces") or [])
        for case in pack.get("cases") or []
        if case.get("traces")
    ]
    n_runs = min(counts) if counts else 1
    dataset: dict[str, Any] = {
        "id": str(pack.get("agent_id") or "gold"),
        "n_runs": n_runs,
        "budget": pack.get("budget") or {},
        "policy": pack.get("policy") or {},
        "tool_schemas": pack.get("tool_schemas") or {},
        "gold_version": pack.get("version"),
        "gold_stale": False,
        "cases": list(pack.get("cases") or []),
    }
    if pack.get("default_expected_tools"):
        dataset["default_expected_tools"] = list(pack["default_expected_tools"])
    return dataset


def as_dataset(doc: dict[str, Any]) -> dict[str, Any]:
    if is_gold_pack(doc):
        return pack_to_dataset(doc)
    return doc


def config_from_pack(pack: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(fallback)
    cfg["id"] = str(pack.get("agent_id") or cfg.get("id") or "live")
    cfg["tool_schemas"] = pack.get("tool_schemas") or cfg.get("tool_schemas") or {}
    cfg["policy"] = pack.get("policy") or cfg.get("policy") or {}
    cfg["budget"] = pack.get("budget") or cfg.get("budget") or {}
    if pack.get("default_expected_tools"):
        cfg["default_expected_tools"] = list(pack["default_expected_tools"])
    cfg["gold_version"] = pack.get("version")
    return cfg
