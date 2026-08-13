# Changelog

## 0.1.0 — 2026-08-13

First pip package.

- Versioned diagnosis schema `0.1.0` (`schema/diagnosis.v0.1.0.json`). Breaking schema changes bump the major version.
- Offline CLI: `phthos-eval run` / `phthos-eval check`.
- Deterministic scorers (tool, schema, budget, policy, loop). Optional BYOK LLM judge.
- Custom `Scorer` hook. `--fail-on-findings` for CI.
