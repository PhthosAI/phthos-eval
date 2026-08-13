# AutoGen / AG2

DuckDuckGo search tool. `sink.wrap(...)`, run AutoGen / AG2 as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/autogen/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/autogen/lib/agent.py
python agent_integration_examples/autogen/live/agent.py
```
