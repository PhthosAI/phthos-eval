# PydanticAI

DuckDuckGo search tool. `sink.wrap(...)`, run PydanticAI as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/pydantic_ai/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/pydantic_ai/lib/agent.py
python agent_integration_examples/pydantic_ai/live/agent.py
```
