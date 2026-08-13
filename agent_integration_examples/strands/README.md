# Strands

DuckDuckGo search tool. `sink.wrap(...)`, run Strands as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/strands/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/strands/lib/agent.py
python agent_integration_examples/strands/live/agent.py
```
