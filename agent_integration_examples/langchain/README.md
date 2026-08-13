# LangChain

DuckDuckGo search tool. `sink.wrap(...)`, run LangChain as usual, then `diagnose` (lib) or `ingest` (live).

```powershell
pip install -r agent_integration_examples/langchain/requirements.txt
$env:OPENAI_API_KEY="your-key"
python agent_integration_examples/langchain/lib/agent.py
python agent_integration_examples/langchain/live/agent.py
```
