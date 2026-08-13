# Smolagents

DuckDuckGo search tool. `sink.wrap(...)`, run Smolagents as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/smolagents/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/smolagents/lib/agent.py
python agent_integration_examples/smolagents/live/agent.py
```
