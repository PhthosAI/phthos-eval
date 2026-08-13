"""Live: wrap a Langroid agent, POST spans. Engine: docker compose up. UI http://127.0.0.1:8765

    pip install -r agent_integration_examples/langroid/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/langroid/live/agent.py
"""

import os

from ddgs import DDGS
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tool_message import ToolMessage
from phthos_eval import TraceSink
from phthos_eval.live import LiveClient

class DuckduckgoSearchTool(ToolMessage):
    request: str = "duckduckgo_search"
    query: str

    def handle(self) -> str:
        return str(DDGS().text(self.query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    client = LiveClient(os.environ.get("PHTHOS_EVAL_URL", "http://127.0.0.1:8765"))  # HTTP to the engine
    print("engine", client.health())  # optional: fail fast if compose is not up

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Langroid still runs the agent
        ChatAgent(ChatAgentConfig(name="search", system_message="Use duckduckgo_search."))
    )
    agent.enable_message(DuckduckgoSearchTool)
    agent.llm_response("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required live: POST spans to the engine (does not call the agent). agent_id is a UI label.
    print("ingest", sink.ingest(client, agent_id="search", expected_tools=["duckduckgo_search"]))
    print("open", client.base_url)  # optional: UI that scores those traces


main()
