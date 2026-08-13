from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from phthos_eval import TraceSink, instrument
from phthos_eval.wrap import _ADAPTERS, FRAMEWORKS, detect


class FakeAdk:
    def __init__(self) -> None:
        self.before_model_callback = None
        self.after_model_callback = None
        self.before_tool_callback = None
        self.after_tool_callback = None


FakeAdk.__module__ = "google.adk.agents.llm_agent"


class Ctx:
    def __init__(self) -> None:
        self.state: dict = {}


def _mod(cls: type, module: str) -> type:
    cls.__module__ = module
    return cls


def test_wrap_adk_records_llm_and_tool() -> None:
    sink = TraceSink()
    agent = sink.wrap(FakeAdk())
    ctx = Ctx()
    agent.before_model_callback(ctx, None)
    agent.after_model_callback(ctx, None)
    tool_ctx = Ctx()
    tool = SimpleNamespace(name="duckduckgo_search")
    agent.before_tool_callback(tool, {"query": "ddg"}, tool_ctx)
    agent.after_tool_callback(tool, {"query": "ddg"}, tool_ctx, "hits")
    assert [s["type"] for s in sink.spans] == ["llm", "tool"]
    assert sink.spans[1]["name"] == "duckduckgo_search"
    doc = sink.diagnose(expected_tools=["duckduckgo_search"])
    assert doc["scores"]["task_success"] == 1.0


def test_wrap_adk_keeps_existing_callback() -> None:
    seen: list[str] = []
    agent = FakeAdk()
    agent.after_tool_callback = lambda *a: seen.append("user") or None
    sink = TraceSink()
    sink.wrap(agent)
    assert isinstance(agent.after_tool_callback, list)
    ctx = Ctx()
    tool = SimpleNamespace(name="search")
    for fn in agent.after_tool_callback:
        fn(tool, {}, ctx, None)
    assert seen == ["user"]
    assert sink.spans[0]["name"] == "search"


def test_instrument_tuple() -> None:
    agent, sink = instrument(FakeAdk())
    agent.after_model_callback(Ctx(), None)
    assert sink.spans[0]["type"] == "llm"


def test_wrap_langchain_with_config() -> None:
    class Runnable:
        def with_config(self, *, callbacks):
            self.callbacks = callbacks
            return self

    _mod(Runnable, "langchain_core.runnables.base")
    sink = TraceSink()
    agent = sink.wrap(Runnable())
    handler = agent.callbacks[0]
    handler.on_llm_start({}, ["hi"], run_id="1")
    handler.on_llm_end(None, run_id="1")
    handler.on_tool_start({"name": "search"}, "q", run_id="2", inputs={"query": "q"})
    handler.on_tool_end("ok", run_id="2")
    assert [s["type"] for s in sink.spans] == ["llm", "tool"]
    assert sink.spans[1]["name"] == "search"


def test_wrap_crewai_step_callback() -> None:
    class CrewAgent:
        def __init__(self) -> None:
            self.role = "researcher"
            self.step_callback = None

    _mod(CrewAgent, "crewai.agent")
    sink = TraceSink()
    agent = sink.wrap(CrewAgent())
    agent.step_callback(SimpleNamespace(tool="search", tool_input={"q": "x"}))
    assert sink.spans[0]["name"] == "search"


def test_wrap_openai_agents_hooks() -> None:
    class Agent:
        def __init__(self) -> None:
            self.hooks = None
            self.tools = []
            self.instructions = "help"

    _mod(Agent, "agents.agent")
    sink = TraceSink()
    agent = sink.wrap(Agent())
    tool = SimpleNamespace(name="lookup", params={"q": "1"})
    asyncio.run(agent.hooks.on_tool_start(None, agent, tool))
    asyncio.run(agent.hooks.on_tool_end(None, agent, tool, "ok"))
    assert sink.spans[0]["name"] == "lookup"


def test_wrap_llama_index_callback_manager() -> None:
    class Manager:
        def __init__(self) -> None:
            self.handlers: list = []

        def add_handler(self, handler) -> None:
            self.handlers.append(handler)

    class Agent:
        def __init__(self) -> None:
            self.callback_manager = Manager()

    _mod(Agent, "llama_index.core.agent")
    sink = TraceSink()
    agent = sink.wrap(Agent())
    handler = agent.callback_manager.handlers[0]
    eid = handler.on_event_start("function_call")
    handler.on_event_end(
        "function_call",
        payload={"tool": "search", "arguments": {"q": "x"}},
        event_id=eid,
    )
    assert sink.spans[0]["name"] == "search"


def test_wrap_pydantic_ai_event_handler() -> None:
    class Agent:
        def __init__(self) -> None:
            self.event_stream_handler = None

    _mod(Agent, "pydantic_ai.agent")
    sink = TraceSink()
    agent = sink.wrap(Agent())

    class FunctionToolCallEvent:
        def __init__(self) -> None:
            self.tool_name = "search"
            self.args = {"q": "x"}

    asyncio.run(agent.event_stream_handler(None, FunctionToolCallEvent()))
    assert sink.spans[0]["name"] == "search"


def test_wrap_autogen_register_hook() -> None:
    class Agent:
        def __init__(self) -> None:
            self.hook = None

        def register_hook(self, name, fn=None):
            self.hook = fn if fn is not None else name

    _mod(Agent, "autogen.agentchat.conversable_agent")
    sink = TraceSink()
    agent = sink.wrap(Agent())
    agent.hook(None, {"type": "tool_call", "name": "search", "args": {"q": "x"}})
    assert sink.spans[0]["name"] == "search"


def test_wrap_semantic_kernel_filter() -> None:
    class Kernel:
        def __init__(self) -> None:
            self.filter = None

        def add_filter(self, kind, fn):
            self.filter = fn

    _mod(Kernel, "semantic_kernel.kernel")
    sink = TraceSink()
    kernel = sink.wrap(Kernel())
    ctx = SimpleNamespace(function=SimpleNamespace(name="lookup"), arguments={"city": "x"})

    async def nxt(_ctx):
        return "ok"

    asyncio.run(kernel.filter(ctx, nxt))
    assert sink.spans[0]["name"] == "lookup"


def test_wrap_smolagents_step_callbacks() -> None:
    class Agent:
        def __init__(self) -> None:
            self.step_callbacks = []

    _mod(Agent, "smolagents.agents")
    sink = TraceSink()
    agent = sink.wrap(Agent())
    agent.step_callbacks[-1](
        SimpleNamespace(tool_calls=[SimpleNamespace(name="search", arguments={"q": "x"})])
    )
    assert sink.spans[0]["name"] == "search"


def test_wrap_agno_tool_hooks() -> None:
    class Agent:
        def __init__(self) -> None:
            self.tool_hooks = []

    _mod(Agent, "agno.agent")
    sink = TraceSink()
    agent = sink.wrap(Agent())
    out = agent.tool_hooks[0]("search", lambda a: "ok", {"q": "x"})
    assert out == "ok"
    assert sink.spans[0]["name"] == "search"


def test_wrap_haystack_run_harvest() -> None:
    class Agent:
        def run(self, query: str):
            del query
            return {"type": "tool_call", "name": "search", "args": {"q": "x"}}

    _mod(Agent, "haystack.components.agents")
    sink = TraceSink()
    agent = sink.wrap(Agent())
    agent.run("hi")
    assert sink.spans[0]["name"] == "search"


def test_wrap_dspy_forward() -> None:
    class Program:
        def forward(self, q: str) -> str:
            return q

    _mod(Program, "dspy.predict")
    sink = TraceSink()
    program = sink.wrap(Program())
    assert program.forward("hi") == "hi"
    assert sink.spans[0]["type"] == "llm"


def test_wrap_camel_step() -> None:
    class ChatAgent:
        def step(self, msg: str) -> str:
            return msg

    _mod(ChatAgent, "camel.agents")
    sink = TraceSink()
    agent = sink.wrap(ChatAgent())
    agent.step("hi")
    assert sink.spans[0]["type"] == "llm"


def test_add_llm_tool_without_wrap() -> None:
    sink = TraceSink()
    sink.add_llm(latency_ms=10)
    sink.add_tool("search", {"query": "x"})
    assert len(sink.spans) == 2


def test_wrap_unknown_explains() -> None:
    with pytest.raises(TypeError, match="OpenTelemetry"):
        TraceSink().wrap(object())


def test_framework_aliases_have_adapters() -> None:
    aliases = {"langgraph": "langchain", "ag2": "autogen"}
    for name in FRAMEWORKS:
        assert aliases.get(name, name) in _ADAPTERS


def test_detect_microsoft_and_strands() -> None:
    class Ms:
        pass

    class Strands:
        pass

    _mod(Ms, "agent_framework.agent")
    _mod(Strands, "strands.agent")
    assert detect(Ms()) == "microsoft_agent_framework"
    assert detect(Strands()) == "strands"
