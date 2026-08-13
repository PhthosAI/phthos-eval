# LlamaIndex

DuckDuckGo search tool. `sink.wrap(...)`, run LlamaIndex as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/llama_index/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/llama_index/lib/agent.py
python agent_integration_examples/llama_index/live/agent.py
```
