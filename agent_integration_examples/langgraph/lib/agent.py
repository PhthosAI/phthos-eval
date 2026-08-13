"""Offline: wrap a LangGraph agent, run it, score.

    pip install -r agent_integration_examples/langgraph/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/langgraph/lib/agent.py
"""

import os

from ddgs import DDGS
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from phthos_eval import TraceSink

@tool
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; LangGraph still runs the agent
        create_react_agent(ChatOpenAI(model="gpt-4o-mini"), [duckduckgo_search])
    )
    agent.invoke({"messages": [("user", "What is DuckDuckGo?")]})  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
