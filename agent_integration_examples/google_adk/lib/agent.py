"""Offline. Wrap an existing ADK agent; score captured spans.

    pip install google-adk ddgs phthos-eval
    set GOOGLE_API_KEY=your-gemini-key
    python agent_integration_examples/google_adk/lib/agent.py

    from phthos_eval import TraceSink
    sink = TraceSink()
    agent = sink.wrap(Agent(...))  # keep running ADK as usual
    # after the run:
    sink.diagnose(expected_tools=["duckduckgo_search"])
"""

from __future__ import annotations

import asyncio
import os
import uuid

from ddgs import DDGS
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from phthos_eval import TraceSink


def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    hits = DDGS().text(query, max_results=3, backend="duckduckgo")
    return str(hits)


async def run_agent() -> TraceSink:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("Set GOOGLE_API_KEY (Gemini) and retry.")
    sink = TraceSink()
    agent = sink.wrap(
        Agent(
            name="search_agent",
            model="gemini-flash-latest",
            instruction="Use duckduckgo_search to answer. Do not invent URLs.",
            tools=[duckduckgo_search],
        )
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
    return sink


sink = asyncio.run(run_agent())
doc = sink.diagnose(
    expected_tools=["duckduckgo_search"],
    budget={"max_cost_usd": 1.0, "max_steps": 8},
    tool_schemas={
        "duckduckgo_search": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        }
    },
)
print("change_class=", doc["change_class"], "task_success=", doc["scores"]["task_success"])
print("tools=", [s.get("name") for s in sink.spans if s.get("type") == "tool"])
