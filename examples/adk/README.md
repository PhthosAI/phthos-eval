# Google ADK examples

Phthos Eval does **not** import ADK. You add **four callbacks** on your existing `Agent`, then either `run_dataset` (lib) or `LiveClient.ingest` (live). Eval does not apply a fix.

```text
your ADK Agent
  before/after model + tool callbacks  →  spans[]
spans[]  →  phthos-eval run     (lib / CI)
spans[]  →  POST /v1/traces     (live UI)
```

One script, both modes:

```bash
pip install google-adk phthos-eval
python examples/adk/hours.py          # lib — diagnosis in the terminal
python examples/adk/hours.py --live   # live engine; open http://127.0.0.1:8765
```

Live engine (from this repo root):

```powershell
$env:PHTHOS_EVAL_SAMPLE_RATE=1
docker compose -p phthos-eval up -d
```

| Case in `hours.py` | Tool | Expect |
|--------------------|------|--------|
| `hours-ok` | `search` | pass |
| `hours-lookup` | `lookup` | `wrong_tool` |
| `hours-refund` | `send_money` | `policy` |

Paste block is at the top of [`hours.py`](hours.py). Set `GOOGLE_API_KEY` to use Gemini instead of the scripted demo model.
