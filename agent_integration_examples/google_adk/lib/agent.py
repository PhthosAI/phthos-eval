"""Offline: wrap an ADK agent, run it, score.

    pip install google-adk ddgs phthos-eval
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

    sink = TraceSink()
    agent = sink.wrap(
        Agent(
            name="search",
            model="gemini-flash-latest",
            instruction="Use duckduckgo_search.",
            tools=[duckduckgo_search],
        )
    )
    runner = InMemoryRunner(agent=agent, app_name="demo")
    await runner.session_service.create_session(app_name="demo", user_id="u", session_id="s")
    async for _ in runner.run_async(
        user_id="u",
        session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text="What is DuckDuckGo?")]),
    ):
        pass

    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
