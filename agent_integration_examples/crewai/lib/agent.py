"""Offline: wrap a CrewAI agent, run it, score.

    pip install -r agent_integration_examples/crewai/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/crewai/lib/agent.py
"""

import os

from crewai import Agent, Crew, LLM, Task
from crewai.tools import tool
from ddgs import DDGS
from phthos_eval import TraceSink

@tool("duckduckgo_search")
def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; CrewAI still runs the agent
        Agent(
            role="researcher",
            goal="Answer using duckduckgo_search.",
            backstory="You search the web.",
            tools=[duckduckgo_search],
            llm=LLM(model="gpt-4o-mini"),
        )
    )
    Crew(
        agents=[agent],
        tasks=[Task(description="What is DuckDuckGo?", expected_output="A short answer", agent=agent)],
    ).kickoff()  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
