# Haystack

DuckDuckGo search tool. `sink.wrap(...)`, run Haystack as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/haystack/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/haystack/lib/agent.py
python agent_integration_examples/haystack/live/agent.py
```
