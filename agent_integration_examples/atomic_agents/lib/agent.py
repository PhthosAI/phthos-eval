"""Offline: wrap a Atomic Agents agent, run it, score.

    pip install -r agent_integration_examples/atomic_agents/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/atomic_agents/lib/agent.py
"""

import os

from atomic_agents import AgentConfig, AtomicAgent, BasicChatInputSchema, BasicChatOutputSchema
from ddgs import DDGS
from instructor import from_openai
from openai import OpenAI
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Atomic Agents still runs the agent
        AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](
            config=AgentConfig(client=from_openai(OpenAI()), model="gpt-4o-mini")
        )
    )
    agent.run(BasicChatInputSchema(chat_message="What is DuckDuckGo?"))  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
