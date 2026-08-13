"""Offline: wrap a Semantic Kernel agent, run it, score.

    pip install -r agent_integration_examples/semantic_kernel/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/semantic_kernel/lib/agent.py
"""

import os
import asyncio

from ddgs import DDGS
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import kernel_function
from phthos_eval import TraceSink

class SearchPlugin:
    @kernel_function(name="duckduckgo_search")
    def duckduckgo_search(self, query: str) -> str:
        """Search the web with DuckDuckGo."""
        return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    kernel = sink.wrap(  # required: attach collectors; Semantic Kernel still runs the agent
        Kernel()
    )
    kernel.add_service(OpenAIChatCompletion(ai_model_id="gpt-4o-mini"))
    kernel.add_plugin(SearchPlugin(), "search")
    await kernel.invoke_prompt(
        "Use duckduckgo_search to answer: What is DuckDuckGo?",
        arguments={"query": "What is DuckDuckGo?"},
    )  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


asyncio.run(main())
