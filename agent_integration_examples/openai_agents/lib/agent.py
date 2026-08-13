"""Offline: wrap a OpenAI Agents SDK agent, run it, score.

    pip install -r agent_integration_examples/openai_agents/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/openai_agents/lib/agent.py
"""

import os

from agents import Agent, Runner, function_tool
from ddgs import DDGS
from phthos_eval import TraceSink

@function_tool
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; OpenAI Agents SDK still runs the agent
        Agent(name="search", instructions="Use duckduckgo_search.", tools=[duckduckgo_search])
    )
    Runner.run_sync(agent, "What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
