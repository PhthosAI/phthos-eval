# Changelog

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
