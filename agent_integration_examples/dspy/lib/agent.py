"""Offline: wrap a DSPy agent, run it, score.

    pip install -r agent_integration_examples/dspy/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/dspy/lib/agent.py
"""

import os

import dspy
from ddgs import DDGS
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; DSPy still runs the agent
        dspy.ReAct("question -> answer", tools=[dspy.Tool(duckduckgo_search)])
    )
    dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))
    agent(question="What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
