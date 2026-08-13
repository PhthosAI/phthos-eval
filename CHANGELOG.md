# Changelog

## 0.6.1 — 2026-08-13

- Google ADK example: one script, lib + live — [`examples/adk/hours.py`](examples/adk/hours.py). Four Agent callbacks, then `run_dataset` or `LiveClient.ingest`.

## 0.6.0 — 2026-08-13

- Consumer contract: poll `GET /v1/diagnoses`, diagnosis webhooks (`event: diagnosis`, no traces), `POST /v1/compare`, `POST /v1/datasets/{id}/run` with `agent_version` (stored on ingest, not in diagnosis JSON). Schema stays **0.2.0**.
- Fine-tune **export only**: `phthos-eval export-finetune` / `GET /v1/export/finetune` (`phthos-eval-finetune.v1`). This product does not train.
- CLI `phthos-eval compare`. Example consumer loop: [`examples/consumer/`](examples/consumer/). Docs: [`docs/CONSUMER.md`](docs/CONSUMER.md).

## 0.5.0 — 2026-08-13

- Hosted **plans** (free / pro): longer retention, volume caps, seats, optional hosted judge, SAML hook. Deterministic scorers and diagnosis schema stay free. Self-host ignores plans.
- RBAC: `owner` / `admin` / `member` / `viewer`. `GET /v1/usage`, `/v1/plan`, `/v1/members`.
- Cloud overlay hooks: `POST /v1/ops/plan`, `POST /v1/sso/consume`. Hosted judge is metered when the operator sets `PHTHOS_EVAL_HOSTED_JUDGE_API_KEY` (BYOK still works). Catalog: [`docs/PLANS.md`](docs/PLANS.md).

## 0.4.0 — 2026-08-13

- Optional **hosted mode** (`--hosted` / `PHTHOS_EVAL_HOSTED=1`): email sign-up, API keys, isolated tenants, datasets, score-drop alerts (webhook / SMTP), workspace export. Same engine and diagnosis schema as self-host. OSS `phthos-eval live` without the flag is unchanged (no accounts).
- `GET /status` (and `/health`) report `mode`, `schema_version`, retention. Privacy: [`docs/PRIVACY.md`](docs/PRIVACY.md). How to run hosted: [`docs/hosted.md`](docs/hosted.md).

## 0.3.0 — 2026-08-13

- Diagnosis schema **0.2.0**: industry profile — `pass^N` (`task_success`), mean N-run reliability, `pass@N`, cost-per-task, p50/p95 latency, tool steps, token sum if logged, per-type hit counts.
- `n_run_reliability` is no longer a duplicate of `task_success`.

## 0.2.3 — 2026-08-13

- README diagrams as PNG with absolute GitHub URLs so PyPI can load them (relative SVG only works on GitHub).

## 0.2.2 — 2026-08-13

- Fix README diagrams (valid SVG + markdown image links). Sample metrics table from the bundled fixture.

## 0.2.1 — 2026-08-13

- README diagrams: overview, offline vs live, diagnosis artifact, live sampling/UI.

## 0.2.0 — 2026-08-13

- Self-host live engine: `phthos-eval live`, Docker Compose, SQLite history.
- Ingest via SDK (`LiveClient`) or OTLP/HTTP JSON. Default sample rate 5%. Scoring is async.
- Same diagnosis schema as offline. Export a sampled run into a dataset for `phthos-eval run`.
- Minimal UI (pass rate, cost, policy hits, diagnosis JSON). LLM judge off unless `--live-judge`.

## 0.1.1 — 2026-08-13

- User-facing README: install from PyPI, project integration, metrics, framework-agnostic traces (LangChain, Google ADK, OTel later).
- CI example installs from PyPI.

## 0.1.0 — 2026-08-13

First pip package.

- Versioned diagnosis schema `0.1.0` (`schema/diagnosis.v0.1.0.json`; current is `0.2.0`). Breaking schema changes bump the major version.
- Offline CLI: `phthos-eval run` / `phthos-eval check`.
- Deterministic scorers (tool, schema, budget, policy, loop). Optional BYOK LLM judge.
- Custom `Scorer` hook. `--fail-on-findings` for CI.
