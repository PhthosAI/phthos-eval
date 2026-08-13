"""Offline: wrap a Langroid agent, run it, score.

    pip install -r agent_integration_examples/langroid/requirements.txt
    $env:OPENAI_API_KEY="your-key"
    python agent_integration_examples/langroid/lib/agent.py
"""

import os

from ddgs import DDGS
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tool_message import ToolMessage
from phthos_eval import TraceSink

class DuckduckgoSearchTool(ToolMessage):
    request: str = "duckduckgo_search"
    query: str

    def handle(self) -> str:
        return str(DDGS().text(self.query, max_results=3, backend="duckduckgo"))

def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY and retry.")

    sink = TraceSink()  # required: buffer for llm/tool spans
    agent = sink.wrap(  # required: attach collectors; Langroid still runs the agent
        ChatAgent(ChatAgentConfig(name="search", system_message="Use duckduckgo_search."))
    )
    agent.enable_message(DuckduckgoSearchTool)
    agent.llm_response("What is DuckDuckGo?")  # one user turn; sink fills during this run

    # required offline: score spans in-process (no live engine)
    print(sink.diagnose(expected_tools=["duckduckgo_search"]))


main()
