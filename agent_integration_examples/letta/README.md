# Letta

DuckDuckGo search tool. `sink.wrap(...)`, run Letta as usual, then `diagnose` (lib) or `ingest` (live).

Letta server must be running (`letta server`). wrap attaches to the client.

```powershell
pip install -r agent_integration_examples/letta/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/letta/lib/agent.py
python agent_integration_examples/letta/live/agent.py
```
