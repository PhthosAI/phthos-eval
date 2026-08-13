from __future__ import annotations

import json
from typing import Any


def otlp_to_traces(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map OTLP/HTTP JSON to [{trace_id, spans}] in the Phthos span shape.

    Understands OpenInference (`openinference.span.kind`) and GenAI
    (`gen_ai.tool.name`, `gen_ai.operation.name`) attributes. Protobuf is not
    accepted — send JSON.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource in payload.get("resourceSpans") or []:
        for scope in resource.get("scopeSpans") or []:
            for raw in scope.get("spans") or []:
                trace_id = _hex(raw.get("traceId") or "unknown")
                grouped.setdefault(trace_id, []).append(_span(raw))
    return [{"trace_id": tid, "spans": spans} for tid, spans in grouped.items()]


def is_otlp(payload: dict[str, Any]) -> bool:
    return isinstance(payload, dict) and "resourceSpans" in payload


def _span(raw: dict[str, Any]) -> dict[str, Any]:
    attrs = _attr_map(raw.get("attributes") or [])
    kind = _kind(raw, attrs)
    start = _nano(raw.get("startTimeUnixNano"))
    end = _nano(raw.get("endTimeUnixNano"))
    latency = round((end - start) / 1_000_000, 3) if start is not None and end is not None else 0.0
    span: dict[str, Any] = {
        "id": _hex(raw.get("spanId") or raw.get("name") or "span"),
        "type": kind,
        "name": _name(kind, raw, attrs),
        "latency_ms": latency,
        "cost_usd": _cost(attrs),
    }
    if kind == "tool":
        span["args"] = _args(attrs)
    return span


def _kind(raw: dict[str, Any], attrs: dict[str, Any]) -> str:
    oi = str(attrs.get("openinference.span.kind") or "").upper()
    if oi in {"TOOL", "RETRIEVER"}:
        return "tool"
    if oi in {"LLM", "CHAIN", "AGENT", "EMBEDDING"}:
        return "llm"
    if attrs.get("gen_ai.tool.name") or attrs.get("tool.name"):
        return "tool"
    op = str(attrs.get("gen_ai.operation.name") or "").lower()
    if op in {"chat", "completion", "generate_content", "embeddings"}:
        return "llm"
    name = str(raw.get("name") or "").lower()
    if "tool" in name:
        return "tool"
    return "llm"


def _name(kind: str, raw: dict[str, Any], attrs: dict[str, Any]) -> str:
    if kind == "tool":
        return str(
            attrs.get("gen_ai.tool.name")
            or attrs.get("tool.name")
            or attrs.get("tool_name")
            or raw.get("name")
            or "tool"
        )
    return str(
        attrs.get("gen_ai.request.model")
        or attrs.get("llm.model_name")
        or raw.get("name")
        or "llm"
    )


def _args(attrs: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "tool.parameters",
        "gen_ai.tool.call.arguments",
        "tool.args",
        "input.value",
    ):
        raw = attrs.get(key)
        if raw is None:
            continue
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"value": raw}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
    return {}


def _cost(attrs: dict[str, Any]) -> float:
    for key in ("gen_ai.usage.cost", "cost_usd", "llm.token_count.cost"):
        val = attrs.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return 0.0


def _attr_map(attrs: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in attrs:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key:
            continue
        out[str(key)] = _any_value(item.get("value"))
    return out


def _any_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        try:
            return int(value["intValue"])
        except (TypeError, ValueError):
            return value["intValue"]
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "bytesValue" in value:
        return value["bytesValue"]
    kv = value.get("kvlistValue") or {}
    if isinstance(kv, dict) and kv.get("values"):
        return _attr_map(kv["values"])
    return value


def _nano(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _hex(raw: Any) -> str:
    if isinstance(raw, bytes):
        return raw.hex()
    return str(raw or "")
