# LangGraph

DuckDuckGo search tool. `sink.wrap(...)`, run LangGraph as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/langgraph/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/langgraph/lib/agent.py
python agent_integration_examples/langgraph/live/agent.py
```
