# Privacy — what this engine stores

Applies to **self-host** (`phthos-eval live`) and **hosted mode** (`--hosted` / `PHTHOS_EVAL_HOSTED=1`). The operators of a hosted URL (including PhthosAI’s cloud) should publish their own retention/contact details; this file is what the software does.

## What is stored

| Data | Why | Where |
|------|-----|--------|
| Sampled traces (span JSON) | Score with the same offline scorers | SQLite `ingests` |
| Diagnosis JSON (schema 0.3.0) | Dashboard, export, CI | SQLite `diagnoses` |
| Gold packs + candidates | Versioned contract; pending live fails | SQLite `gold_packs`, `gold_observed`, `gold_candidates` |
| Offline datasets you upload | Run the same `run_dataset` path | SQLite `datasets` (hosted) |
| Email + password hash | Sign-up / login (hosted only) | SQLite `users` (PBKDF2) |
| API key hashes | Ingest / CI (hosted only) | SQLite `api_keys` (SHA-256 of `pk_…`) |
| Alert webhook / email | Score-drop notices | SQLite `workspaces` |

Passwords and raw API keys are not stored. The plaintext API key is shown **once** at sign-up.

## What is not stored / not sent

- Traces are **not** sent to a model PhthosAI owns. Default is deterministic scorers only.
- Optional LLM judge is **BYOK**: your `OPENAI_API_KEY` / `PHTHOS_EVAL_API_KEY` and optional `PHTHOS_EVAL_JUDGE_BASE_URL`. Off unless `--live-judge`.
- No prompt editor, no auto-fix, no fine-tune from these scores.
- Unsampled traces are recorded as skipped ingest rows (no diagnosis) so sample counts are honest; they are still subject to retention.

## Retention default

**30 days** in hosted mode (`PHTHOS_EVAL_RETENTION_DAYS`). On process start, rows older than that are deleted. Self-host does not auto-prune (your disk, your choice).

## Export (no hostage data)

- One run: `POST /v1/diagnoses/{id}/export` → offline dataset JSON
- Hosted workspace: `GET /v1/export` → diagnoses + datasets
- Fine-tune file (not training): `GET /v1/export/finetune` / `phthos-eval export-finetune`
- OSS CLI: `phthos-eval run` on that JSON, no cloud required

## Self-host

Omit `--hosted`. No accounts. Data stays in `PHTHOS_EVAL_DATA_DIR` (default `./phthos-eval-data`) on the machine that runs the process.
