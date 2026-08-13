"""Live: wrap an ADK agent, POST spans. Engine: docker compose up. UI http://127.0.0.1:8765

    pip install google-adk ddgs phthos-eval
    $env:GOOGLE_API_KEY="your-gemini-key"
    python agent_integration_examples/google_adk/live/agent.py
"""

import asyncio
import os

from ddgs import DDGS
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from phthos_eval import TraceSink
from phthos_eval.live import LiveClient


def duckduckgo_search(query: str) -> str:
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))


async def main() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("Set GOOGLE_API_KEY and retry.")

    client = LiveClient(os.environ.get("PHTHOS_EVAL_URL", "http://127.0.0.1:8765"))  # HTTP to the engine
    print("engine", client.health())  # optional: fail fast if compose is not up

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

    # required live: POST spans to the engine (does not call the agent). agent_id is a UI label.
    print("ingest", sink.ingest(client, agent_id="search", expected_tools=["duckduckgo_search"]))
    print("open", client.base_url)  # optional: UI that scores those traces


asyncio.run(main())
