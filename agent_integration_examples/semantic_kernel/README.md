# Semantic Kernel

DuckDuckGo search tool. `sink.wrap(...)`, run Semantic Kernel as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/semantic_kernel/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/semantic_kernel/lib/agent.py
python agent_integration_examples/semantic_kernel/live/agent.py
```
