# BeeAI

DuckDuckGo search tool. `sink.wrap(...)`, run BeeAI as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/beeai/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/beeai/lib/agent.py
python agent_integration_examples/beeai/live/agent.py
```
