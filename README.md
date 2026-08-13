# Phthos Eval

Pip package for offline agent eval. Deterministic scorers first. Optional LLM **judge** uses **your** key. This repo does not apply fixes.

Python 3.11+. **Pip only** (no npm).

## Install

```bash
pip install phthos-eval
```

Or from git until the first PyPI release is cut:

```bash
pip install "phthos-eval @ git+https://github.com/PhthosAI/phthos-eval.git"
```

From a clone:

```bash
pip install -e ".[dev]"
```

## Run

```bash
python -m phthos_eval run -d fixtures/dataset.json -o diagnosis.json
python -m phthos_eval check diagnosis.json
```

CI gate (exit 1 if any failure):

```bash
python -m phthos_eval run -d eval/dataset.json -o diagnosis.json --fail-on-findings
```

Copy-paste workflow: [`examples/github-eval.yml`](examples/github-eval.yml).

## Read the JSON

`diagnosis.json` is versioned (`schema_version`: `0.1.0`). Breaking schema changes bump the **major** package version.

| Field | Meaning |
|-------|---------|
| `scores` | `task_success`, `cost`, `latency_ms`, `policy_hits`, `n_run_reliability` |
| `failures[].type` | `wrong_tool`, `loop`, `budget`, `policy` |
| `failures[].span_id` | Where it happened |
| `change_class` | `prompt` \| `tool` \| `policy` \| `model` \| `finetune_data` \| `none` |
| `evidence` | Span / step pointers, not an essay |
| `judge` | Optional LLM score; `skipped: true` with no key |

Python:

```python
from phthos_eval import Diagnosis, Scorer, failure, run_dataset, validate_diagnosis

class NoEmptyReply:
    def score(self, trace, *, case, dataset, case_id, trace_index):
        if not trace.get("spans"):
            return [failure("policy", "missing", case_id=case_id, trace_index=trace_index)]
        return []

doc = run_dataset(dataset, scorers=[NoEmptyReply()])  # or omit scorers for defaults
assert validate_diagnosis(doc) == []
print(doc["change_class"], doc["scores"])
```

## Keys (do not mix)

| Env | Whose | Used for |
|-----|--------|----------|
| Agent provider keys | The system under test | Running the agent (not this package) |
| `OPENAI_API_KEY` or `PHTHOS_EVAL_API_KEY` | You | Optional **judge** only |

Without a judge key, deterministic scorers still run. Optional: `PHTHOS_EVAL_JUDGE_BASE_URL` (OpenAI-compatible, Ollama, gateway), `PHTHOS_EVAL_JUDGE_MODEL`.

No hosted LLM is required.

## Examples

- [`fixtures/dataset.json`](fixtures/dataset.json) — unit fixture
- [`examples/support_agent/`](examples/support_agent/) — recorded support-agent traces (dogfood in this repo, not a Task AI merge)

## Dev

```bash
python -m pytest
python -m ruff check src tests
```
