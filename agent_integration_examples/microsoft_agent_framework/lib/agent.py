"""Offline: wrap a Microsoft Agent Framework agent, run it, score.

    pip install -r agent_integration_examples/microsoft_agent_framework/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/microsoft_agent_framework/lib/agent.py
"""

import os
import asyncio

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from ddgs import DDGS
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Microsoft Agent Framework still runs the agent
        ChatAgent(
            chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),
            instructions="Use duckduckgo_search.",
            tools=[duckduckgo_search],
        )
    )
    await agent.run("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
