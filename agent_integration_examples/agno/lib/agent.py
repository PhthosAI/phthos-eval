"""Offline: wrap a Agno agent, run it, score.

    pip install -r agent_integration_examples/agno/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/agno/lib/agent.py
"""

import os

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from ddgs import DDGS
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Agno still runs the agent
        Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[duckduckgo_search],
            instructions="Use duckduckgo_search.",
        )
    )
    agent.run("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
