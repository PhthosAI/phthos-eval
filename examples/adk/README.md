# Google ADK — DuckDuckGo search

One tool. Two scripts (lib vs live). Add four callbacks to an existing `Agent`, then score. Eval does not wrap ADK or apply a fix.

```powershell
pip install google-adk ddgs phthos-eval
$env:GOOGLE_API_KEY="your-gemini-key"

python examples/adk/lib.py    # offline diagnosis in the terminal
python examples/adk/live.py   # POST /v1/traces — UI http://127.0.0.1:8765
```

Paste block is at the top of each file.
