# Consumer contract

Versioned interface for **another system** (CI, an improver product, Task AI, a gateway-backed agent). Phthos Eval **scores** and returns diagnosis JSON. It does **not** apply the fix.

Diagnosis schema **0.3.0** (`additionalProperties: false`). Includes `gold_version` and `gold_stale`. Do not put `agent_version` inside the diagnosis file. Live ingest stores it as `ingests.agent_id`. Living gold: [`GOLD.md`](GOLD.md).

## Auth

| Mode | Machines |
|------|----------|
| Hosted | `Authorization: Bearer pk_…` or `X-Phthos-Key` |
| OSS self-host | Open local HTTP (no accounts) |

Always **public HTTPS + API key** when the engine is on another host. No Docker DNS, no shared compose, no `TASK_AI_*` in this repo.

## Diagnosis (schema 0.3.0)

`change_class` is enough to branch:

| Value | Consumer typically |
|-------|--------------------|
| `prompt` | Edit instructions / stop a loop |
| `tool` | Rename, schema, or allow-list |
| `policy` | Deny-list / safety rules |
| `model` | Model id or budget |
| `finetune_data` | Train **their** stack on an export |
| `none` | No change |

Offline:

```bash
phthos-eval run -d dataset.json -o diagnosis.json
phthos-eval check diagnosis.json
```

## Poll and webhook

Poll summaries (not full traces):

```
GET /v1/diagnoses?since=&agent_id=&limit=
GET /v1/scores?since=&agent_id=&limit=
GET /v1/diagnoses/{run_id}
```

If a workspace webhook is set (`POST /v1/alerts`), each scored run POSTs:

```json
{
  "event": "diagnosis",
  "run_id": "…",
  "change_class": "tool",
  "passed": false,
  "schema_version": "0.3.0",
  "gold_version": "g_…",
  "gold_stale": false,
  "scores": { "task_success": 0.0 }
}
```

Score-drop alerts stay `{ "event": "score_drop", … }`. Webhooks never include traces.

## Agent version and before/after

Submit a versioned dataset run (diagnosis still returned at the top level):

```
POST /v1/datasets/{id}/run
{ "agent_version": "v2" }
```

Same cases, two runs:

```
POST /v1/compare
{ "before_run_id": "…", "after_run_id": "…" }
```

or `{ "dataset_id", "agent_version", "baseline_run_id" }`.

Offline:

```bash
phthos-eval compare --before before.json --after after.json
```

`task_success_delta` is after − before. Live watch after deploy: `GET /v1/scores?agent_id=v2` (same scorers).

## Living gold

Versioned pack of tool schemas, policy, SOP hash, and **confirmed** cases. Live scores bind to the active pack (`gold_version` / `gold_stale`). Sampled fails become candidates; a human or CI token must confirm. The judge cannot confirm.

```
PUT  /v1/gold/{agent_id}
GET  /v1/gold/{agent_id}
POST /v1/gold/{agent_id}/sync
GET  /v1/gold/{agent_id}/candidates?status=pending
GET  /v1/gold/{agent_id}/export
POST /v1/gold/candidates/{id}/confirm
POST /v1/gold/candidates/{id}/reject
```

```bash
phthos-eval gold -f gold.json --dataset-out dataset.json
phthos-eval run -d gold.json -o diagnosis.json
```

Details: [`GOLD.md`](GOLD.md).

## Fine-tune export (file only)

```bash
phthos-eval export-finetune -d dataset.json --diagnosis diagnosis.json -o ft.json
```

```
GET /v1/export/finetune?dataset_id=&run_id=
```

Format `phthos-eval-finetune.v1`: pass/fail + evidence + traces. **Their** trainer consumes it. This product does not train or update weights.

## Example

[`examples/consumer/`](../examples/consumer/) — a script outside the engine reads `change_class`, writes `agent.json`, re-records, re-evals. Eval never writes that file.

## Split-stack

Task AI and the Phthos gateway are **customers**: `https://…` + API key. MCP/brain URLs stay in those products.
