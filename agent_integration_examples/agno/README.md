# Agno

DuckDuckGo search tool. `sink.wrap(...)`, run Agno as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/agno/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/agno/lib/agent.py
python agent_integration_examples/agno/live/agent.py
```
