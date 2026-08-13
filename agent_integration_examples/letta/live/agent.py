"""Live: wrap a Letta agent, POST spans. Engine: docker compose up. UI http://127.0.0.1:8765

    pip install -r agent_integration_examples/letta/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/letta/live/agent.py
"""

import os

from ddgs import DDGS
from letta_client import Letta
from phthos_eval import TraceSink
from phthos_eval.live import LiveClient

def duckduckgo_search(query: str) -> str:
    """Search the web with DuckDuckGo."""
    return str(DDGS().text(query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    client = LiveClient(os.environ.get("PHTHOS_EVAL_URL", "http://127.0.0.1:8765"))  # HTTP to the engine
    print("engine", client.health())  # optional: fail fast if compose is not up

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Letta still runs the agent
        Letta(base_url="http://localhost:8283")
    )
    created = agent.agents.create(name="search", memory_blocks=[], tools=["duckduckgo_search"])
    agent.agents.messages.create(created.id, input="What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required live: POST spans to the engine (does not call the agent). agent_id is a UI label.
    print("ingest", sink.ingest(client, agent_id="search", expected_tools=["duckduckgo_search"]))
    print("open", client.base_url)  # optional: UI that scores those traces


main()
