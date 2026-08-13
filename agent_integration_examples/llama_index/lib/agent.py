"""Offline: wrap a LlamaIndex agent, run it, score.

    pip install -r agent_integration_examples/llama_index/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/llama_index/lib/agent.py
"""

import os
import asyncio

from ddgs import DDGS
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; LlamaIndex still runs the agent
        FunctionAgent(
            name="search",
            tools=[duckduckgo_search],
            llm=OpenAI(model="gpt-4o-mini"),
            system_prompt="Use duckduckgo_search.",
        )
    )
    await agent.run("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
