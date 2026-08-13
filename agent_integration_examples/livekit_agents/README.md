# LiveKit Agents

DuckDuckGo search tool. `sink.wrap(...)`, run LiveKit Agents as usual, then `diagnose` (lib) or `ingest` (live).

Full voice runtime needs a LiveKit room. This sample shows wrap on the Agent object.

```powershell
pip install -r agent_integration_examples/livekit_agents/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/livekit_agents/lib/agent.py
python agent_integration_examples/livekit_agents/live/agent.py
```
