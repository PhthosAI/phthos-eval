"""Attach TraceSink collectors onto market agent objects. No framework install required.

Detection is by module prefix (then a few duck-types). Each adapter only sets hooks /
filters / a run wrapper — the framework still runs the agent.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from typing import Any

FRAMEWORKS: tuple[str, ...] = (
    "google_adk",
    "langchain",
    "langgraph",
    "crewai",
    "openai_agents",
    "llama_index",
    "pydantic_ai",
    "autogen",
    "ag2",
    "microsoft_agent_framework",
    "semantic_kernel",
    "smolagents",
    "agno",
    "haystack",
    "dspy",
    "camel",
    "strands",
    "langroid",
    "letta",
    "atomic_agents",
    "beeai",
    "livekit_agents",
)

_ADK_ATTRS = (
    "before_model_callback",
    "after_model_callback",
    "before_tool_callback",
    "after_tool_callback",
)
_STATE_KEY = "_phthos_t"
_RUN_NAMES = (
    "run",
    "run_sync",
    "run_async",
    "ainvoke",
    "invoke",
    "kickoff",
    "chat",
    "step",
    "generate_reply",
    "send_message",
)


def wrap_agent(sink: Any, agent: Any) -> Any:
    kind = detect(agent)
    if kind is None:
        raise TypeError(
            f"TraceSink cannot wrap {type(agent).__module__}.{type(agent).__name__}. "
            f"Known: {', '.join(FRAMEWORKS)}. "
            "Call sink.add_llm(...) / sink.add_tool(...) yourself, or POST OpenTelemetry "
            "OpenInference JSON to /v1/otel/traces."
        )
    return _ADAPTERS[kind](sink, agent)


def detect(agent: Any) -> str | None:
    mod = str(type(agent).__module__ or "")
    if (mod == "agents" or mod.startswith("agents.")) and (
        hasattr(agent, "hooks") or (hasattr(agent, "tools") and hasattr(agent, "instructions"))
    ):
        return "openai_agents"
    for prefix, kind in _PREFIXES:
        if mod == prefix or mod.startswith(prefix + "."):
            return kind
    if all(hasattr(agent, a) for a in _ADK_ATTRS):
        return "google_adk"
    if hasattr(agent, "step_callback") and hasattr(agent, "role"):
        return "crewai"
    if callable(getattr(agent, "with_config", None)) or hasattr(agent, "callbacks"):
        return "langchain"
    return None


_PREFIXES: tuple[tuple[str, str], ...] = (
    ("google.adk", "google_adk"),
    ("pydantic_ai", "pydantic_ai"),
    ("llama_index", "llama_index"),
    ("crewai", "crewai"),
    ("smolagents", "smolagents"),
    ("agno", "agno"),
    ("semantic_kernel", "semantic_kernel"),
    ("autogen_agentchat", "autogen"),
    ("autogen", "autogen"),
    ("ag2", "autogen"),
    ("agent_framework", "microsoft_agent_framework"),
    ("haystack", "haystack"),
    ("dspy", "dspy"),
    ("camel", "camel"),
    ("strands", "strands"),
    ("langroid", "langroid"),
    ("letta", "letta"),
    ("atomic_agents", "atomic_agents"),
    ("beeai_framework", "beeai"),
    ("beeai", "beeai"),
    ("livekit.agents", "livekit_agents"),
    ("langchain_core", "langchain"),
    ("langchain_community", "langchain"),
    ("langchain", "langchain"),
    ("langgraph", "langchain"),
)


def _wrap_adk(sink: Any, agent: Any) -> Any:
    def before_model(ctx: Any, req: Any) -> None:
        del req
        _stamp(ctx)

    def after_model(ctx: Any, resp: Any) -> None:
        sink.add_llm(latency_ms=_elapsed(ctx), **_llm_usage(resp))

    def before_tool(tool: Any, args: Any, ctx: Any) -> None:
        del tool, args
        _stamp(ctx)

    def after_tool(tool: Any, args: Any, ctx: Any, resp: Any) -> None:
        del resp
        name = getattr(tool, "name", None) or str(tool)
        raw = args if isinstance(args, dict) else {}
        sink.add_tool(str(name), raw, latency_ms=_elapsed(ctx))

    _prepend(agent, "before_model_callback", before_model)
    _prepend(agent, "after_model_callback", after_model)
    _prepend(agent, "before_tool_callback", before_tool)
    _prepend(agent, "after_tool_callback", after_tool)
    return agent


def _wrap_langchain(sink: Any, agent: Any) -> Any:
    handler = _langchain_handler(sink)
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


def _wrap_crewai(sink: Any, agent: Any) -> Any:
    prev = getattr(agent, "step_callback", None)

    def _cb(output: Any) -> None:
        name = getattr(output, "tool", None)
        if name:
            raw = getattr(output, "tool_input", None)
            args = raw if isinstance(raw, dict) else {"input": raw}
            sink.add_tool(str(name), args)
        if callable(prev):
            prev(output)

    agent.step_callback = _cb
    if hasattr(agent, "agents") and isinstance(agent.agents, list):
        for member in agent.agents:
            _wrap_crewai(sink, member)
    return agent


def _wrap_openai_agents(sink: Any, agent: Any) -> Any:
    ours = _OpenAIHooks(sink)
    prev = getattr(agent, "hooks", None)
    agent.hooks = _ChainHooks(ours, prev) if prev is not None else ours
    return agent


def _wrap_llama_index(sink: Any, agent: Any) -> Any:
    handler = _LlamaLegacyHandler(sink)
    cm = getattr(agent, "callback_manager", None)
    if cm is not None and hasattr(cm, "add_handler"):
        cm.add_handler(handler)
        return agent
    try:
        from llama_index.core.instrumentation import get_dispatcher

        get_dispatcher().add_event_handler(_LlamaEventHandler(sink))
    except ImportError:
        _patch_run_methods(sink, agent)
    return agent


def _wrap_pydantic_ai(sink: Any, agent: Any) -> Any:
    prev = getattr(agent, "event_stream_handler", None)

    async def handler(ctx: Any, event: Any) -> None:
        _record_named_event(sink, event)
        await _maybe_await(prev, ctx, event)

    try:
        agent.event_stream_handler = handler
        return agent
    except (AttributeError, TypeError):
        _patch_run_methods(sink, agent)
        return agent


def _wrap_autogen(sink: Any, agent: Any) -> Any:
    register = getattr(agent, "register_hook", None)
    if callable(register):
        def _hook(sender: Any, message: Any) -> Any:
            _harvest_obj(sink, message, depth=0)
            return message

        try:
            register("process_message_before_send", _hook)
        except TypeError:
            register(_hook)
        return agent
    _patch_run_methods(sink, agent)
    return agent


def _wrap_microsoft_agent(sink: Any, agent: Any) -> Any:
    add = getattr(agent, "add_middleware", None) or getattr(agent, "use", None)
    if callable(add):
        async def mw(context: Any, nxt: Any) -> Any:
            t0 = time.perf_counter()
            out = nxt(context)
            if inspect.isawaitable(out):
                out = await out
            _record_tool_from(sink, context, latency_ms=(time.perf_counter() - t0) * 1000)
            _harvest_obj(sink, out, depth=0)
            return out

        add(mw)
        return agent
    _patch_run_methods(sink, agent)
    return agent


def _wrap_semantic_kernel(sink: Any, agent: Any) -> Any:
    add_filter = getattr(agent, "add_filter", None)
    kernel = agent if callable(add_filter) else getattr(agent, "kernel", None)
    add_filter = getattr(kernel, "add_filter", None) if kernel is not None else add_filter
    if not callable(add_filter):
        _patch_run_methods(sink, agent)
        return agent

    async def fn_filter(context: Any, nxt: Any) -> Any:
        t0 = time.perf_counter()
        out = nxt(context)
        if inspect.isawaitable(out):
            out = await out
        fn = getattr(context, "function", None)
        name = getattr(fn, "name", None) or "function"
        args = _sk_args(context)
        sink.add_tool(str(name), args, latency_ms=(time.perf_counter() - t0) * 1000)
        return out

    add_filter("function_invocation", fn_filter)
    return agent


def _wrap_smolagents(sink: Any, agent: Any) -> Any:
    def _cb(step_log: Any) -> None:
        calls = getattr(step_log, "tool_calls", None) or []
        for call in calls:
            name = getattr(call, "name", None) or getattr(call, "tool_name", None)
            args = getattr(call, "arguments", None) or getattr(call, "args", None) or {}
            if name:
                sink.add_tool(str(name), args if isinstance(args, dict) else {"input": args})
        if not calls:
            _harvest_obj(sink, step_log, depth=0)

    cbs = getattr(agent, "step_callbacks", None)
    if isinstance(cbs, list):
        agent.step_callbacks = [*cbs, _cb]
    else:
        try:
            agent.step_callbacks = [_cb]
        except (AttributeError, TypeError):
            _patch_run_methods(sink, agent)
    return agent


def _wrap_agno(sink: Any, agent: Any) -> Any:
    def hook(function_name: Any, function_call: Any, arguments: Any) -> Any:
        t0 = time.perf_counter()
        out = function_call(arguments)
        if inspect.isawaitable(out):
            return _await_tool(sink, str(function_name), arguments, out, t0)
        sink.add_tool(
            str(function_name),
            arguments if isinstance(arguments, dict) else {"input": arguments},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
        return out

    hooks = getattr(agent, "tool_hooks", None)
    if isinstance(hooks, list):
        agent.tool_hooks = [hook, *hooks]
        return agent
    try:
        agent.tool_hooks = [hook]
        return agent
    except (AttributeError, TypeError):
        _patch_run_methods(sink, agent)
        return agent


def _wrap_haystack(sink: Any, agent: Any) -> Any:
    _patch_run_methods(sink, agent, harvest=True)
    return agent


def _wrap_dspy(sink: Any, agent: Any) -> Any:
    orig = getattr(agent, "forward", None)
    if not callable(orig):
        _patch_run_methods(sink, agent)
        return agent

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        out = orig(*args, **kwargs)
        sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
        _harvest_obj(sink, out, depth=0)
        return out

    agent.forward = wrapped
    return agent


def _wrap_camel(sink: Any, agent: Any) -> Any:
    orig = getattr(agent, "step", None)
    if callable(orig):
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            out = orig(*args, **kwargs)
            sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
            _harvest_obj(sink, out, depth=0)
            return out

        agent.step = wrapped
        return agent
    _patch_run_methods(sink, agent)
    return agent


def _wrap_strands(sink: Any, agent: Any) -> Any:
    hooks = getattr(agent, "hooks", None)
    add = getattr(hooks, "add_callback", None) if hooks is not None else None
    if callable(add):
        def before(event: Any) -> None:
            _stamp(event)

        def after_tool(event: Any) -> None:
            tool = getattr(event, "tool_use", None) or getattr(event, "tool", None)
            name = getattr(tool, "name", None) or getattr(event, "tool_name", None) or "tool"
            args = getattr(tool, "input", None) or getattr(event, "tool_input", None) or {}
            sink.add_tool(str(name), args if isinstance(args, dict) else {}, latency_ms=_elapsed(event))

        def after_model(event: Any) -> None:
            sink.add_llm(latency_ms=_elapsed(event))

        for label, fn in (
            ("BeforeToolCallEvent", before),
            ("AfterToolCallEvent", after_tool),
            ("BeforeModelCallEvent", before),
            ("AfterModelCallEvent", after_model),
        ):
            try:
                add(label, fn)
            except TypeError:
                add(fn)
        return agent
    _patch_run_methods(sink, agent)
    return agent


def _wrap_langroid(sink: Any, agent: Any) -> Any:
    orig = getattr(agent, "llm_response", None)
    if callable(orig):
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            out = orig(*args, **kwargs)
            sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
            _harvest_obj(sink, out, depth=0)
            return out

        agent.llm_response = wrapped
        return agent
    _patch_run_methods(sink, agent)
    return agent


def _wrap_letta(sink: Any, agent: Any) -> Any:
    _patch_run_methods(sink, agent, harvest=True)
    return agent


def _wrap_atomic(sink: Any, agent: Any) -> Any:
    _patch_run_methods(sink, agent, harvest=True)
    return agent


def _wrap_beeai(sink: Any, agent: Any) -> Any:
    _patch_run_methods(sink, agent, harvest=True)
    return agent


def _wrap_livekit(sink: Any, agent: Any) -> Any:
    _patch_run_methods(sink, agent, harvest=True)
    return agent


_ADAPTERS: dict[str, Callable[[Any, Any], Any]] = {
    "google_adk": _wrap_adk,
    "langchain": _wrap_langchain,
    "crewai": _wrap_crewai,
    "openai_agents": _wrap_openai_agents,
    "llama_index": _wrap_llama_index,
    "pydantic_ai": _wrap_pydantic_ai,
    "autogen": _wrap_autogen,
    "microsoft_agent_framework": _wrap_microsoft_agent,
    "semantic_kernel": _wrap_semantic_kernel,
    "smolagents": _wrap_smolagents,
    "agno": _wrap_agno,
    "haystack": _wrap_haystack,
    "dspy": _wrap_dspy,
    "camel": _wrap_camel,
    "strands": _wrap_strands,
    "langroid": _wrap_langroid,
    "letta": _wrap_letta,
    "atomic_agents": _wrap_atomic,
    "beeai": _wrap_beeai,
    "livekit_agents": _wrap_livekit,
}


class _OpenAIHooks:
    def __init__(self, sink: Any) -> None:
        self._sink = sink
        self._t: dict[str, float] = {}

    async def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self._t["llm"] = time.perf_counter()

    async def on_llm_end(self, *args: Any, **kwargs: Any) -> None:
        t0 = self._t.pop("llm", time.perf_counter())
        self._sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)

    async def on_tool_start(self, context: Any, agent: Any, tool: Any, **kwargs: Any) -> None:
        del context, agent
        self._t[id(tool)] = time.perf_counter()

    async def on_tool_end(
        self, context: Any, agent: Any, tool: Any, result: Any = None, **kwargs: Any
    ) -> None:
        del context, agent, result
        t0 = self._t.pop(id(tool), time.perf_counter())
        name = getattr(tool, "name", None) or str(tool)
        args = getattr(tool, "params", None) or getattr(tool, "arguments", None) or {}
        self._sink.add_tool(
            str(name),
            args if isinstance(args, dict) else {"input": args},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    async def on_start(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def on_end(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def on_handoff(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def on_agent_start(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def on_agent_end(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


class _ChainHooks:
    def __init__(self, ours: Any, theirs: Any) -> None:
        self._ours = ours
        self._theirs = theirs

    def __getattr__(self, name: str) -> Any:
        async def _fwd(*args: Any, **kwargs: Any) -> None:
            await _maybe_await(getattr(self._ours, name, None), *args, **kwargs)
            await _maybe_await(getattr(self._theirs, name, None), *args, **kwargs)

        return _fwd


class _LlamaLegacyHandler:
    def __init__(self, sink: Any) -> None:
        self._sink = sink
        self._t: dict[str, float] = {}

    def on_event_start(self, event_type: Any, payload: Any = None, **kwargs: Any) -> str:
        eid = str(kwargs.get("event_id") or time.perf_counter())
        self._t[eid] = time.perf_counter()
        return eid

    def on_event_end(
        self, event_type: Any, payload: Any = None, *, event_id: Any = None, **kwargs: Any
    ) -> None:
        t0 = self._t.pop(str(event_id), time.perf_counter())
        kind = str(getattr(event_type, "value", event_type) or "").lower()
        payload = payload or {}
        if kind in {"llm", "agent_step"}:
            self._sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
        if kind in {"function_call"}:
            name = payload.get("function_call") or payload.get("tool") or "tool"
            if hasattr(name, "name"):
                name = name.name
            args = payload.get("arguments") or payload.get("tool_input") or {}
            self._sink.add_tool(str(name), args if isinstance(args, dict) else {})


class _LlamaEventHandler:
    def __init__(self, sink: Any) -> None:
        self._sink = sink

    def handle(self, event: Any, **kwargs: Any) -> None:
        _record_named_event(self._sink, event)


def _langchain_handler(sink: Any) -> Any:
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


def _sk_args(context: Any) -> dict[str, Any]:
    raw = getattr(context, "arguments", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    items = getattr(raw, "items", None)
    if callable(items):
        return {str(k): v for k, v in items()}
    return {}


def _record_named_event(sink: Any, event: Any) -> None:
    name = type(event).__name__.lower()
    if "toolcall" in name or "functiontoolcall" in name or "tool_call" in name:
        tool = getattr(event, "tool_name", None) or getattr(event, "name", None)
        part = getattr(event, "part", None)
        if tool is None and part is not None:
            tool = getattr(part, "tool_name", None)
        args = getattr(event, "args", None) or getattr(event, "tool_args", None) or {}
        if part is not None and not args:
            args = getattr(part, "args", None) or {}
        if tool:
            sink.add_tool(str(tool), args if isinstance(args, dict) else {})
    elif "llm" in name or "modelresponse" in name or "partstart" in name:
        sink.add_llm()


def _record_tool_from(sink: Any, obj: Any, *, latency_ms: float) -> None:
    name = getattr(obj, "function_name", None) or getattr(obj, "name", None)
    if not name:
        fn = getattr(obj, "function", None)
        name = getattr(fn, "name", None)
    if not name:
        return
    args = getattr(obj, "arguments", None) or getattr(obj, "args", None) or {}
    sink.add_tool(str(name), args if isinstance(args, dict) else {}, latency_ms=latency_ms)


def _patch_run_methods(sink: Any, obj: Any, *, harvest: bool = True) -> None:
    for name in _RUN_NAMES:
        orig = getattr(obj, name, None)
        if not callable(orig) or getattr(orig, "_phthos_patched", False):
            continue
        setattr(obj, name, _wrap_run(sink, orig, harvest=harvest))


def _wrap_run(sink: Any, orig: Any, *, harvest: bool) -> Any:
    if inspect.iscoroutinefunction(orig):
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            out = await orig(*args, **kwargs)
            if harvest:
                _harvest_obj(sink, out, depth=0)
                if not sink.spans:
                    sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
            return out

        wrapped._phthos_patched = True  # type: ignore[attr-defined]
        return wrapped

    def wrapped_sync(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        out = orig(*args, **kwargs)
        if inspect.isawaitable(out):
            return _harvest_async(sink, out, t0, harvest)
        if harvest:
            _harvest_obj(sink, out, depth=0)
            if not sink.spans:
                sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
        return out

    wrapped_sync._phthos_patched = True  # type: ignore[attr-defined]
    return wrapped_sync


async def _harvest_async(sink: Any, out: Any, t0: float, harvest: bool) -> Any:
    result = await out
    if harvest:
        _harvest_obj(sink, result, depth=0)
        if not sink.spans:
            sink.add_llm(latency_ms=(time.perf_counter() - t0) * 1000)
    return result


async def _await_tool(sink: Any, name: str, arguments: Any, out: Any, t0: float) -> Any:
    result = await out
    sink.add_tool(
        name,
        arguments if isinstance(arguments, dict) else {"input": arguments},
        latency_ms=(time.perf_counter() - t0) * 1000,
    )
    return result


async def _maybe_await(fn: Any, *args: Any, **kwargs: Any) -> None:
    if not callable(fn):
        return
    out = fn(*args, **kwargs)
    if inspect.isawaitable(out):
        await out


def _harvest_obj(sink: Any, obj: Any, *, depth: int) -> None:
    if obj is None or depth > 4:
        return
    if isinstance(obj, (str, bytes, int, float, bool)):
        return
    msgs = getattr(obj, "all_messages", None)
    if callable(msgs):
        try:
            obj = msgs()
        except TypeError:
            pass
    items = getattr(obj, "new_items", None)
    if items:
        obj = items
    if isinstance(obj, dict):
        name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
        if obj.get("type") in {"tool", "function_call", "tool_call"} and name:
            sink.add_tool(str(name), obj.get("args") or obj.get("arguments") or {})
            return
        for value in list(obj.values())[:12]:
            _harvest_obj(sink, value, depth=depth + 1)
        return
    if isinstance(obj, (list, tuple)):
        for item in obj[:24]:
            _harvest_obj(sink, item, depth=depth + 1)
        return
    for attr in ("tool_calls", "tools_used", "messages", "parts", "items"):
        nested = getattr(obj, attr, None)
        if nested:
            _harvest_obj(sink, nested, depth=depth + 1)
    name = getattr(obj, "tool_name", None) or getattr(obj, "name", None)
    kind = type(obj).__name__.lower()
    if name and ("tool" in kind or "functioncall" in kind):
        args = getattr(obj, "args", None) or getattr(obj, "arguments", None) or {}
        sink.add_tool(str(name), args if isinstance(args, dict) else {})
