"""Offline: wrap a LangChain agent, run it, score.

    pip install -r agent_integration_examples/langchain/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/langchain/lib/agent.py
"""

import os

from ddgs import DDGS
from langchain.agents import create_agent
from langchain_core.tools import tool
from phthos_eval import TraceSink

@tool
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; LangChain still runs the agent
        create_agent("gpt-4o-mini", tools=[duckduckgo_search])
    )
    agent.invoke({"messages": [{"role": "user", "content": "What is DuckDuckGo?"}]})  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
