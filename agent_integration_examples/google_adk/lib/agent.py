"""Offline: wrap an ADK agent, run it, score.

    pip install -r agent_integration_examples/google_adk/requirements.txt
    $env:GOOGLE_API_KEY="your-gemini-key"
    python agent_integration_examples/google_adk/lib/agent.py
"""

import asyncio
import os

from ddgs import DDGS
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from phthos_eval import TraceSink


def duckduckgo_search(query: str) -> str:
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))


async def main() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("Set GOOGLE_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; ADK still runs the agent
        Agent(
            name="search",
            model="gemini-flash-latest",
            instruction="Use duckduckgo_search.",
            tools=[duckduckgo_search],
        )
    )
    runner = InMemoryRunner(agent=agent, app_name="demo")  # ADK, not eval
    await runner.session_service.create_session(app_name="demo", user_id="u", session_id="s")
    async for _ in runner.run_async(  # one user turn; sink fills during this run
        user_id="u",
        session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text="What is DuckDuckGo?")]),
    ):
        pass

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
