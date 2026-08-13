"""Offline: wrap a AutoGen / AG2 agent, run it, score.

    pip install -r agent_integration_examples/autogen/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/autogen/lib/agent.py
"""

import os
import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from ddgs import DDGS
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; AutoGen / AG2 still runs the agent
        AssistantAgent(
            "search",
            model_client=OpenAIChatCompletionClient(model="gpt-4o-mini"),
            tools=[duckduckgo_search],
            system_message="Use duckduckgo_search.",
        )
    )
    await agent.run(task="What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
