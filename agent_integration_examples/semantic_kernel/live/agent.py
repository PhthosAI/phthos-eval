"""Live: wrap a Semantic Kernel agent, POST spans. Engine: docker compose up. UI http://127.0.0.1:8765

    pip install -r agent_integration_examples/semantic_kernel/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/semantic_kernel/live/agent.py
"""

import os
import asyncio

from ddgs import DDGS
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import kernel_function
from phthos_eval import TraceSink
from phthos_eval.live import LiveClient

class SearchPlugin:
    @kernel_function(name="duckduckgo_search")
    def duckduckgo_search(self, query: str) -> str:
        """Search the web with DuckDuckGo."""
        return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    client = LiveClient(os.environ.get("PHTHOS_EVAL_URL", "http://127.0.0.1:8765"))  # HTTP to the engine
    print("engine", client.health())  # optional: fail fast if compose is not up

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

    # required live: POST spans to the engine (does not call the agent). agent_id is a UI label.
    print("ingest", sink.ingest(client, agent_id="search", expected_tools=["duckduckgo_search"]))
    print("open", client.base_url)  # optional: UI that scores those traces


asyncio.run(main())
