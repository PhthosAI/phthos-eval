"""Offline (lib). One ADK agent, one DuckDuckGo search tool.

    pip install google-adk ddgs phthos-eval
    set GOOGLE_API_KEY=your-gemini-key
    python agent_integration_examples/google_adk/lib/agent.py

Paste onto an existing Agent (then run_dataset on sink.spans):

    sink = EvalSink()
    agent = Agent(
        ...,
        before_model_callback=sink.before_model_callback,
        after_model_callback=sink.after_model_callback,
        before_tool_callback=sink.before_tool_callback,
        after_tool_callback=sink.after_tool_callback,
    )
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any

from ddgs import DDGS
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from phthos_eval.runner import run_dataset


class EvalSink:
    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self._n = 0

    def _id(self) -> str:
        self._n += 1
        return f"s{self._n}"

    def before_model_callback(self, callback_context, llm_request):
        callback_context.state["_t"] = time.perf_counter()

    def after_model_callback(self, callback_context, llm_response):
        t0 = float(callback_context.state.get("_t") or time.perf_counter())
        self.spans.append(
            {
                "id": self._id(),
                "type": "llm",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
                "cost_usd": 0.001,
            }
        )

    def before_tool_callback(self, tool, args, tool_context):
        tool_context.state["_t"] = time.perf_counter()

    def after_tool_callback(self, tool, args, tool_context, tool_response):
        t0 = float(tool_context.state.get("_t") or time.perf_counter())
        self.spans.append(
            {
                "id": self._id(),
                "type": "tool",
                "name": tool.name,
                "args": dict(args or {}),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
                "cost_usd": 0.0,
            }
        )


def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    hits = DDGS().text(query, max_results=3, backend="duckduckgo")
    return str(hits)


async def run_agent() -> list[dict[str, Any]]:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("Set GOOGLE_API_KEY (Gemini) and retry.")
    sink = EvalSink()
    agent = Agent(
        name="search_agent",
        model="gemini-flash-latest",
        instruction="Use duckduckgo_search to answer. Do not invent URLs.",
        tools=[duckduckgo_search],
        before_model_callback=sink.before_model_callback,
        after_model_callback=sink.after_model_callback,
        before_tool_callback=sink.before_tool_callback,
        after_tool_callback=sink.after_tool_callback,
    )
    runner = InMemoryRunner(agent=agent, app_name="adk-ddg")
    sid = uuid.uuid4().hex[:8]
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id="u", session_id=sid
    )
    async for _ in runner.run_async(
        user_id="u",
        session_id=sid,
        new_message=types.Content(role="user", parts=[types.Part(text="What is DuckDuckGo?")]),
    ):
        pass
    return sink.spans


spans = asyncio.run(run_agent())
doc = run_dataset(
    {
        "id": "adk-ddg",
        "n_runs": 1,
        "budget": {"max_cost_usd": 1.0, "max_steps": 8},
        "policy": {"deny_tools": []},
        "tool_schemas": {
            "duckduckgo_search": {
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            }
        },
        "cases": [
            {
                "id": "ddg",
                "expected_tools": ["duckduckgo_search"],
                "traces": [{"spans": spans}],
            }
        ],
    },
    judge=False,
)
print("change_class=", doc["change_class"], "task_success=", doc["scores"]["task_success"])
print("tools=", [s.get("name") for s in spans if s.get("type") == "tool"])
