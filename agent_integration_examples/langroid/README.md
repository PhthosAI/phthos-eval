# Langroid

DuckDuckGo search tool. `sink.wrap(...)`, run Langroid as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/langroid/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/langroid/lib/agent.py
python agent_integration_examples/langroid/live/agent.py
```
