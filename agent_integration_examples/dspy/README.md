# DSPy

DuckDuckGo search tool. `sink.wrap(...)`, run DSPy as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/dspy/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/dspy/lib/agent.py
python agent_integration_examples/dspy/live/agent.py
```
