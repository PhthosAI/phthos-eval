"""Capture llm/tool spans from an existing agent. No framework import required.

    from phthos_eval import TraceSink

    sink = TraceSink()
    agent = sink.wrap(agent)   # ADK, LangChain/LangGraph, CrewAI
    # run the agent as usual
    doc = sink.diagnose(expected_tools=["search"])
"""

from __future__ import annotations

import time
from typing import Any

from phthos_eval.runner import run_dataset

_ADK_ATTRS = (
    "before_model_callback",
    "after_model_callback",
    "before_tool_callback",
    "after_tool_callback",
)
_STATE_KEY = "_phthos_t"


def instrument(agent: Any, *, sink: TraceSink | None = None) -> tuple[Any, TraceSink]:
    """Attach a sink and return ``(agent, sink)``."""
    s = sink or TraceSink()
    return s.wrap(agent), s


class TraceSink:
    """In-process span buffer. ``wrap`` attaches collectors; you still run the agent."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self._n = 0

    def reset(self) -> None:
        self.spans = []
        self._n = 0

    def wrap(self, agent: Any) -> Any:
        """Return the same agent (or a LangChain configured copy) with collectors attached.

        Does not replace the framework runtime. Unknown types get a short error pointing
        at ``add_llm`` / ``add_tool`` or OpenTelemetry ingest.
        """
        kind = _kind(agent)
        if kind == "adk":
            return self._wrap_adk(agent)
        if kind == "langchain":
            return self._wrap_langchain(agent)
        if kind == "crewai":
            return self._wrap_crewai(agent)
        raise TypeError(
            f"TraceSink cannot wrap {type(agent).__module__}.{type(agent).__name__}. "
            "Known: Google ADK, LangChain/LangGraph (with_config or .callbacks), CrewAI. "
            "Call sink.add_llm(...) / sink.add_tool(...) yourself, or POST OpenTelemetry "
            "OpenInference JSON to /v1/otel/traces."
        )

    def add_llm(
        self,
        *,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        tokens: float | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        span: dict[str, Any] = {
            "id": self._id(),
            "type": "llm",
            "latency_ms": round(float(latency_ms), 3),
            "cost_usd": float(cost_usd),
            **extra,
        }
        if tokens is not None:
            span["tokens"] = tokens
        self.spans.append(span)
        return span

    def add_tool(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        **extra: Any,
    ) -> dict[str, Any]:
        span: dict[str, Any] = {
            "id": self._id(),
            "type": "tool",
            "name": name,
            "args": dict(args or {}),
            "latency_ms": round(float(latency_ms), 3),
            "cost_usd": float(cost_usd),
            **extra,
        }
        self.spans.append(span)
        return span

    def diagnose(
        self,
        *,
        expected_tools: list[str] | None = None,
        budget: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        tool_schemas: dict[str, Any] | None = None,
        case_id: str = "run",
        dataset_id: str = "trace-sink",
        judge: bool = False,
    ) -> dict[str, Any]:
        """Score the captured spans with the same offline runner."""
        return run_dataset(
            {
                "id": dataset_id,
                "n_runs": 1,
                "budget": budget or {"max_cost_usd": 1e9, "max_steps": 10_000},
                "policy": policy or {"deny_tools": []},
                "tool_schemas": tool_schemas or {},
                "cases": [
                    {
                        "id": case_id,
                        "expected_tools": expected_tools or [],
                        "traces": [{"spans": list(self.spans)}],
                    }
                ],
            },
            judge=judge,
        )

    def ingest(self, client: Any, **kwargs: Any) -> Any:
        """POST spans through a ``LiveClient`` (or anything with ``ingest(spans, **kw)``)."""
        return client.ingest(self.spans, **kwargs)

    def _id(self) -> str:
        self._n += 1
        return f"s{self._n}"

    def _wrap_adk(self, agent: Any) -> Any:
        _prepend(agent, "before_model_callback", self._adk_before_model)
        _prepend(agent, "after_model_callback", self._adk_after_model)
        _prepend(agent, "before_tool_callback", self._adk_before_tool)
        _prepend(agent, "after_tool_callback", self._adk_after_tool)
        return agent

    def _adk_before_model(self, callback_context: Any, llm_request: Any) -> None:
        del llm_request
        _stamp(callback_context)

    def _adk_after_model(self, callback_context: Any, llm_response: Any) -> None:
        self.add_llm(latency_ms=_elapsed(callback_context), **_llm_usage(llm_response))

    def _adk_before_tool(self, tool: Any, args: Any, tool_context: Any) -> None:
        del tool, args
        _stamp(tool_context)

    def _adk_after_tool(
        self, tool: Any, args: Any, tool_context: Any, tool_response: Any
    ) -> None:
        del tool_response
        name = getattr(tool, "name", None) or str(tool)
        raw = args if isinstance(args, dict) else {}
        self.add_tool(str(name), raw, latency_ms=_elapsed(tool_context))

    def _wrap_langchain(self, agent: Any) -> Any:
        handler = _langchain_handler(self)
        with_config = getattr(agent, "with_config", None)
        if callable(with_config):
            return with_config(callbacks=[handler])
        callbacks = getattr(agent, "callbacks", None)
        if callbacks is not None and hasattr(callbacks, "add_handler"):
            callbacks.add_handler(handler)
            return agent
        if isinstance(callbacks, list):
            agent.callbacks = [*callbacks, handler]
            return agent
        agent.callbacks = [handler]
        return agent

    def _wrap_crewai(self, agent: Any) -> Any:
        prev = getattr(agent, "step_callback", None)

        def _cb(output: Any) -> None:
            name = getattr(output, "tool", None)
            if name:
                raw = getattr(output, "tool_input", None)
                args = raw if isinstance(raw, dict) else {"input": raw}
                self.add_tool(str(name), args)
            if callable(prev):
                prev(output)

        agent.step_callback = _cb
        return agent


def _kind(agent: Any) -> str | None:
    mod = str(type(agent).__module__ or "")
    if mod.startswith("google.adk") or all(hasattr(agent, a) for a in _ADK_ATTRS):
        return "adk"
    if mod.startswith("crewai") or (
        hasattr(agent, "step_callback") and hasattr(agent, "role")
    ):
        return "crewai"
    if callable(getattr(agent, "with_config", None)) or hasattr(agent, "callbacks"):
        return "langchain"
    return None


def _prepend(obj: Any, name: str, fn: Any) -> None:
    existing = getattr(obj, name, None)
    if existing is None:
        setattr(obj, name, fn)
    elif isinstance(existing, list):
        setattr(obj, name, [fn, *existing])
    else:
        setattr(obj, name, [fn, existing])


def _stamp(ctx: Any) -> None:
    state = getattr(ctx, "state", None)
    now = time.perf_counter()
    if state is None:
        try:
            ctx.state = {_STATE_KEY: now}
        except (AttributeError, TypeError):
            return
        return
    try:
        state[_STATE_KEY] = now
    except (TypeError, KeyError, AttributeError):
        return


def _elapsed(ctx: Any) -> float:
    state = getattr(ctx, "state", None) or {}
    try:
        raw = state.get(_STATE_KEY)
        t0 = float(raw) if raw is not None else time.perf_counter()
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return (time.perf_counter() - t0) * 1000


def _llm_usage(llm_response: Any) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    um = getattr(llm_response, "usage_metadata", None)
    if um is None and isinstance(llm_response, dict):
        um = llm_response.get("usage_metadata")
    if um is None:
        return extra
    inn = getattr(um, "prompt_token_count", None) or getattr(um, "input_tokens", None)
    out = getattr(um, "candidates_token_count", None) or getattr(um, "output_tokens", None)
    if isinstance(um, dict):
        inn = um.get("prompt_token_count", um.get("input_tokens"))
        out = um.get("candidates_token_count", um.get("output_tokens"))
    if inn is not None:
        extra["input_tokens"] = inn
    if out is not None:
        extra["output_tokens"] = out
    return extra


def _langchain_handler(sink: TraceSink) -> Any:
    base: type = object
    try:
        from langchain_core.callbacks.base import BaseCallbackHandler as base
    except ImportError:
        try:
            from langchain.callbacks.base import BaseCallbackHandler as base
        except ImportError:
            base = object

    class PhthosLangChainHandler(base):  # type: ignore[misc, valid-type]
        ignore_chain = True
        ignore_retriever = True
        raise_error = False

        def __init__(self) -> None:
            if base is not object:
                super().__init__()
            self._sink = sink
            self._t: dict[str, float] = {}
            self._tools: dict[str, dict[str, Any]] = {}

        def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
            self._t[str(kwargs.get("run_id"))] = time.perf_counter()

        def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
            self._t[str(kwargs.get("run_id"))] = time.perf_counter()

        def on_llm_end(self, response: Any, **kwargs: Any) -> None:
            t0 = self._t.pop(str(kwargs.get("run_id")), time.perf_counter())
            self._sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)

        def on_tool_start(self, serialized: Any, input_str: Any, **kwargs: Any) -> None:
            rid = str(kwargs.get("run_id"))
            self._t[rid] = time.perf_counter()
            name = None
            if isinstance(serialized, dict):
                name = serialized.get("name")
            name = name or kwargs.get("name") or "tool"
            raw = kwargs.get("inputs")
            args = raw if isinstance(raw, dict) else {"input": input_str}
            self._tools[rid] = {"name": str(name), "args": args}

        def on_tool_end(self, output: Any, **kwargs: Any) -> None:
            rid = str(kwargs.get("run_id"))
            t0 = self._t.pop(rid, time.perf_counter())
            meta = self._tools.pop(rid, {"name": "tool", "args": {}})
            self._sink.add_tool(
                meta["name"],
                meta["args"],
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

    return PhthosLangChainHandler()
