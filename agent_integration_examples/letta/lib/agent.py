"""Offline: wrap a Letta agent, run it, score.

    pip install -r agent_integration_examples/letta/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/letta/lib/agent.py
"""

import os

from ddgs import DDGS
from letta_client import Letta
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Letta still runs the agent
        Letta(base_url="http://localhost:8283")
    )
    created = agent.agents.create(name="search", memory_blocks=[], tools=["duckduckgo_search"])
    agent.agents.messages.create(created.id, input="What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
