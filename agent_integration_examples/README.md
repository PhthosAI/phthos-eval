# Agent integration examples

Layout: **framework / lib | live**. Phthos Eval does not import these frameworks. Copy the four callbacks onto your existing agent, then score. Eval does not apply a fix.

```text
agent_integration_examples/
  google_adk/
    lib/     offline — run_dataset
    live/    live engine — POST /v1/traces
```

```powershell
pip install google-adk ddgs phthos-eval
$env:GOOGLE_API_KEY="your-gemini-key"

python agent_integration_examples/google_adk/lib/agent.py
python agent_integration_examples/google_adk/live/agent.py
```

Live UI: http://127.0.0.1:8765 (`docker compose up` from this repo).
