# CAMEL

DuckDuckGo search tool. `sink.wrap(...)`, run CAMEL as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/camel/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/camel/lib/agent.py
python agent_integration_examples/camel/live/agent.py
```
