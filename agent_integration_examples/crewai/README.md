# CrewAI

DuckDuckGo search tool. `sink.wrap(...)`, run CrewAI as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/crewai/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/crewai/lib/agent.py
python agent_integration_examples/crewai/live/agent.py
```
