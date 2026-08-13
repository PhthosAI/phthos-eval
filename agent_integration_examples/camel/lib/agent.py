"""Offline: wrap a CAMEL agent, run it, score.

    pip install -r agent_integration_examples/camel/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/camel/lib/agent.py
"""

import os

from camel.agents import ChatAgent
from camel.models import ModelFactory
from camel.toolkits import FunctionTool
from camel.types import ModelPlatformType, ModelType
from ddgs import DDGS
from phthos_eval import TraceSink

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; CAMEL still runs the agent
        ChatAgent(
            model=ModelFactory.create(ModelPlatformType.OPENAI, ModelType.GPT_4O_MINI),
            tools=[FunctionTool(duckduckgo_search)],
        )
    )
    agent.step("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
