# Live engine (self-host)

Same scorers as `phthos-eval run`, on a **sampled** stream. Data stays in `./phthos-eval-data` (or the Compose volume). No hosted LLM. No auto-fix.

Tenant login / cloud URL is optional **hosted mode** on this same image: [`docs/hosted.md`](../../docs/hosted.md) and `docker-compose.hosted.yml`. Default Compose below is still open self-host (no accounts).

Default sample rate is **5%**. The LLM judge is **off** unless you pass `--live-judge` *and* set a key. Do not run a judge on 100% of production.

## Docker Compose

From the repo root (`phthos-eval/public`):

```bash
docker compose up --build
```

UI: http://127.0.0.1:8765  
Health: `GET /health`  
Ingest: `POST /v1/traces`

Demo (sample rate 1.0 so every posted trace is scored — **demo only**):

```bash
# Unix
PHTHOS_EVAL_SAMPLE_RATE=1 docker compose up --build

# Windows PowerShell
$env:PHTHOS_EVAL_SAMPLE_RATE=1; docker compose up --build
```

In another terminal:

```bash
pip install phthos-eval
phthos-eval live-demo --url http://127.0.0.1:8765
```

Then open the UI. ADK DuckDuckGo agent: [`examples/adk/lib.py`](../adk/lib.py) / [`live.py`](../adk/live.py). Failed runs: **Save to offline dataset** writes `phthos-eval-data/from-live.json`. Re-score with the phase 2 runner:

```bash
phthos-eval run -d phthos-eval-data/from-live.json -o diagnosis.json
```

Stop; nothing is uploaded:

```bash
docker compose down
```

SQLite stays in the `phthos-eval-data` volume / folder on your machine.

## Without Docker

```bash
phthos-eval live -c examples/live/config.json --sample-rate 0.05
```

## Ingest

SDK (does not wait for scoring):

```python
from phthos_eval.live import LiveClient

client = LiveClient("http://127.0.0.1:8765")
client.ingest(
    spans=[{"id": "s0", "type": "tool", "name": "search", "args": {"query": "x"}}],
    agent_id="support",
    expected_tools=["search"],
)
```

Or `POST /v1/traces` with that JSON. OTLP/HTTP **JSON** (OpenInference or GenAI attributes): `POST /v1/otel/traces`, or the same `/v1/traces` if the body has `resourceSpans`. Protobuf is not accepted.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` or `/status` | Process up, mode, schema version, sample rate, judge on/off |
| GET | `/v1/scores` | Pass rate, cost, policy hits, recent sampled runs |
| GET | `/v1/diagnoses/{id}` | Full diagnosis JSON (same schema as offline) |
| POST | `/v1/traces` | Ingest (202 immediately) |
| POST | `/v1/otel/traces` | OTLP JSON ingest |
| POST | `/v1/diagnoses/{id}/export` | Append that run to an offline dataset |

## Cost

| Knob | Default | Why |
|------|---------|-----|
| `PHTHOS_EVAL_SAMPLE_RATE` | `0.05` | Score a slice of prod, not every turn |
| Judge key | unset | Deterministic scorers only; no token bill |
| `PHTHOS_EVAL_LIVE_JUDGE` | off | Even with a key, live judge is opt-in |

Production: keep sample rate in 1–10% and leave the judge off unless you know the bill.
