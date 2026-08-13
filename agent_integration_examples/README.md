# Agent integration examples

Same call for every Python agent stack: `sink.wrap(agent)`. Eval does not apply a fix. Scoring is one span shape; wrap is only the hook adapter.

```python
from phthos_eval import TraceSink

sink = TraceSink()
agent = sink.wrap(agent)
# run as usual
doc = sink.diagnose(expected_tools=["search"])
```

`TraceSink.frameworks` lists adapters: Google ADK, LangChain/LangGraph, CrewAI, OpenAI Agents SDK, LlamaIndex, PydanticAI, AutoGen/AG2, Microsoft Agent Framework, Semantic Kernel, Smolagents, Agno, Haystack, DSPy, CAMEL, Strands, Langroid, Letta, Atomic Agents, BeeAI, LiveKit Agents.

Runnable sample (DuckDuckGo):

```text
agent_integration_examples/
  google_adk/
    lib/     offline
    live/    POST /v1/traces
```

```powershell
pip install google-adk ddgs phthos-eval
$env:GOOGLE_API_KEY="your-gemini-key"
python agent_integration_examples/google_adk/lib/agent.py
python agent_integration_examples/google_adk/live/agent.py
```

Anything else: OpenTelemetry OpenInference → `POST /v1/otel/traces`, or `sink.add_llm` / `sink.add_tool`.
