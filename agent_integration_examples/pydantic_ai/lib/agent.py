"""Offline: wrap a PydanticAI agent, run it, score.

    pip install -r agent_integration_examples/pydantic_ai/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/pydantic_ai/lib/agent.py
"""

import os

from ddgs import DDGS
from pydantic_ai import Agent
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; PydanticAI still runs the agent
        Agent("openai:gpt-4o-mini", instructions="Use duckduckgo_search.", tools=[duckduckgo_search])
    )
    agent.run_sync("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
