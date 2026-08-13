# Living gold

Versioned **gold pack** for an agent: tool schemas, policy, SOP hash, and **confirmed** cases. Live scores bind to the active pack. If the customer’s current schemas/SOP change and gold does not, the pack is **stale**.

Eval does **not** apply the agent fix. Task AI / gateway stay customers (public HTTPS + API key) — they are not wired in this repo.

Schema: [`schema/gold.v1.json`](../schema/gold.v1.json). Diagnosis **0.3.0** records `gold_version` and `gold_stale`.

## Put a pack

```
PUT /v1/gold/{agent_id}
{
  "tool_schemas": { "lookup_order": { "type": "object", "required": ["order_id"] } },
  "policy": { "deny_tools": ["issue_refund"] },
  "budget": { "max_steps": 8 },
  "sop": "Refunds require lookup_order first.",
  "default_expected_tools": ["lookup_order"],
  "cases": []
}
```

Creates a new version. Source hashes come from `tool_schemas` + `policy` + `sop`. OSS self-host: no auth. Hosted: admin/owner.

```
GET /v1/gold/{agent_id}   → { pack, stale, version, agent_id }
GET /v1/gold/{agent_id}/export   → offline dataset for `phthos-eval run`
```

## Sync (stale signal)

Customer sends **current** tools / policy / SOP. Cases are not rewritten.

```
POST /v1/gold/{agent_id}/sync
{ "tool_schemas": { … }, "policy": { … }, "sop": "…" }
```

If hashes differ from the active pack → `stale: true`. Scoring still runs and sets `gold_stale` on the diagnosis. `GET /v1/scores` includes `gold_stale`.

A new `PUT` with matching sources clears stale.

## Candidates

Sampled live runs that **fail** or have `change_class` ≠ `none` become pending candidates. Passing / `none` does not auto-enter gold. The judge cannot confirm.

```
GET /v1/gold/{agent_id}/candidates?status=pending
POST /v1/gold/candidates/{id}/confirm
POST /v1/gold/candidates/{id}/reject
```

`{"source":"judge"}` on confirm returns `400 judge_cannot_confirm`.

Confirm copies the case into a **new** gold version.

## CLI

```bash
phthos-eval gold -f gold.json --dataset-out dataset.json
phthos-eval gold -f gold.json --check-stale   # exit 2 if GET-shaped file has stale: true
phthos-eval run -d gold.json -o diagnosis.json   # gold pack or dataset
```

## Sampling

Live ingest is still sampled (`PHTHOS_EVAL_SAMPLE_RATE`, default 5%). This is not 100% production scoring and not a second trace warehouse.
