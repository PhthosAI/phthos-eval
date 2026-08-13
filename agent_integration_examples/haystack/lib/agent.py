"""Offline: wrap a Haystack agent, run it, score.

    pip install -r agent_integration_examples/haystack/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/haystack/lib/agent.py
"""

import os

from ddgs import DDGS
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.tools import tool
from phthos_eval import TraceSink

@tool
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Haystack still runs the agent
        Agent(chat_generator=OpenAIChatGenerator(model="gpt-4o-mini"), tools=[duckduckgo_search])
    )
    agent.run(messages=[ChatMessage.from_user("What is DuckDuckGo?")])  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
