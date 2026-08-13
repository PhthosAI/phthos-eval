# Google ADK

`sink.wrap(Agent(...))`, run ADK as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install google-adk ddgs phthos-eval
$env:GOOGLE_API_KEY="your-gemini-key"
python agent_integration_examples/google_adk/lib/agent.py
python agent_integration_examples/google_adk/live/agent.py
```
