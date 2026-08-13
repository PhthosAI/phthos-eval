"""Live: wrap a Atomic Agents agent, POST spans. Engine: docker compose up. UI http://127.0.0.1:8765

    pip install -r agent_integration_examples/atomic_agents/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/atomic_agents/live/agent.py
"""

import os

from atomic_agents import AgentConfig, AtomicAgent, BasicChatInputSchema, BasicChatOutputSchema
from ddgs import DDGS
from instructor import from_openai
from openai import OpenAI
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
    agent = sink.wrap(  # required: attach collectors; Atomic Agents still runs the agent
        AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](
            config=AgentConfig(client=from_openai(OpenAI()), model="gpt-4o-mini")
        )
    )
    agent.run(BasicChatInputSchema(chat_message="What is DuckDuckGo?"))  # one user turn; sink fills during this run

    # required live: POST spans to the engine (does not call the agent). agent_id is a UI label.
    print("ingest", sink.ingest(client, agent_id="search", expected_tools=["duckduckgo_search"]))
    print("open", client.base_url)  # optional: UI that scores those traces


main()
