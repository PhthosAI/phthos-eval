# Google ADK

One DuckDuckGo search tool. Copy the four callbacks onto an existing `Agent`, then score. Eval does not wrap ADK or apply a fix.

| Folder | Mode |
|--------|------|
| [`lib/`](lib/agent.py) | Offline `run_dataset` |
| [`live/`](live/agent.py) | Live engine `POST /v1/traces` |

```powershell
pip install google-adk ddgs phthos-eval
$env:GOOGLE_API_KEY="your-gemini-key"

python agent_integration_examples/google_adk/lib/agent.py
python agent_integration_examples/google_adk/live/agent.py
```
