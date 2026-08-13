# Microsoft Agent Framework

DuckDuckGo search tool. `sink.wrap(...)`, run Microsoft Agent Framework as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/microsoft_agent_framework/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/microsoft_agent_framework/lib/agent.py
python agent_integration_examples/microsoft_agent_framework/live/agent.py
```
