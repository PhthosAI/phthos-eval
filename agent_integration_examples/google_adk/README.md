# Google ADK

DuckDuckGo search tool. `sink.wrap(Agent(...))`, run ADK as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/google_adk/requirements.txt
$env:GOOGLE_API_KEY="your-gemini-key"
python agent_integration_examples/google_adk/lib/agent.py
python agent_integration_examples/google_adk/live/agent.py
```
