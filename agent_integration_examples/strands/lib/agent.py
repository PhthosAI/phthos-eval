"""Offline: wrap a Strands agent, run it, score.

    pip install -r agent_integration_examples/strands/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/strands/lib/agent.py
"""

import os

from ddgs import DDGS
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from phthos_eval import TraceSink

@tool
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Strands still runs the agent
        Agent(model=OpenAIModel(model_id="gpt-4o-mini"), tools=[duckduckgo_search])
    )
    agent("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
