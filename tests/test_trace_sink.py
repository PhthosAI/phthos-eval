from __future__ import annotations

from types import SimpleNamespace

import pytest

from phthos_eval import TraceSink, instrument


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
    assert sink.spans[1]["args"] == {"query": "ddg"}
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

    Runnable.__module__ = "langchain_core.runnables.base"
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

    CrewAgent.__module__ = "crewai.agent"
    sink = TraceSink()
    agent = sink.wrap(CrewAgent())
    agent.step_callback(SimpleNamespace(tool="search", tool_input={"q": "x"}))
    assert sink.spans[0]["name"] == "search"


def test_add_llm_tool_without_wrap() -> None:
    sink = TraceSink()
    sink.add_llm(latency_ms=10)
    sink.add_tool("search", {"query": "x"})
    assert len(sink.spans) == 2


def test_wrap_unknown_explains() -> None:
    with pytest.raises(TypeError, match="OpenTelemetry"):
        TraceSink().wrap(object())
