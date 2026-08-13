"""Offline: wrap a LiveKit Agents agent, run it, score.

    pip install -r agent_integration_examples/livekit_agents/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/livekit_agents/lib/agent.py
"""

import os

from ddgs import DDGS
from livekit.agents import Agent, function_tool
from phthos_eval import TraceSink

class SearchAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="Use duckduckgo_search.")

    @function_tool
    async def duckduckgo_search(self, query: str) -> str:
        """Search the web with DuckDuckGo."""
        return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; LiveKit Agents still runs the agent
        SearchAgent()
    )
    print("wrapped", type(agent).__name__)  # run SearchAgent inside your LiveKit worker after wrap  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
