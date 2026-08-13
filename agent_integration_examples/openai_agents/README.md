# OpenAI Agents SDK

DuckDuckGo search tool. `sink.wrap(...)`, run OpenAI Agents SDK as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/openai_agents/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/openai_agents/lib/agent.py
python agent_integration_examples/openai_agents/live/agent.py
```
