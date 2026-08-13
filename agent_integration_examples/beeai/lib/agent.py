"""Offline: wrap a BeeAI agent, run it, score.

    pip install -r agent_integration_examples/beeai/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/beeai/lib/agent.py
"""

import os
import asyncio

from beeai_framework.agents.react import ReActAgent
from beeai_framework.backend import ChatModel
from beeai_framework.memory import UnconstrainedMemory
from beeai_framework.tools import tool
from ddgs import DDGS
from phthos_eval import TraceSink

@tool
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; BeeAI still runs the agent
        ReActAgent(
            llm=ChatModel.from_name("openai:gpt-4o-mini"),
            tools=[duckduckgo_search],
            memory=UnconstrainedMemory(),
        )
    )
    await agent.run("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
