"""Live. Wrap an existing ADK agent; POST spans to the engine.

    pip install google-adk ddgs phthos-eval
    set GOOGLE_API_KEY=your-gemini-key
    python agent_integration_examples/google_adk/live/agent.py

Engine: docker compose up (this repo). UI: http://127.0.0.1:8765

    from phthos_eval import TraceSink
    from phthos_eval.live import LiveClient
    sink = TraceSink()
    agent = sink.wrap(Agent(...))
    LiveClient("http://127.0.0.1:8765").ingest(
        sink.spans, agent_id="search_agent", expected_tools=["duckduckgo_search"],
    )
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from ddgs import DDGS
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from phthos_eval import TraceSink
from phthos_eval.live import LiveClient
from phthos_eval.live.client import LiveError


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


url = os.environ.get("PHTHOS_EVAL_URL", "http://127.0.0.1:8765")
client = LiveClient(url)
try:
    print("engine", client.health())
except LiveError as exc:
    sys.exit(f"live engine not up at {url}: {exc}")

sink = asyncio.run(run_agent())
print("ingest", sink.ingest(
    client,
    agent_id="search_agent",
    case_id="ddg",
    expected_tools=["duckduckgo_search"],
))
print("open", url)
