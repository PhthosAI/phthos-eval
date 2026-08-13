# Atomic Agents

DuckDuckGo search tool. `sink.wrap(...)`, run Atomic Agents as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/atomic_agents/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/atomic_agents/lib/agent.py
python agent_integration_examples/atomic_agents/live/agent.py
```
