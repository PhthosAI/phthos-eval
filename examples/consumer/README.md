# Example consumer (not an improver product)

A **different system** — this folder — reads diagnosis JSON, changes `agent.json`, and asks eval to score again. Phthos Eval never edits the agent, opens a PR, or trains weights.

```
cases.json + agent.json  →  record.py  →  dataset
dataset                  →  phthos-eval run  →  diagnosis
diagnosis                →  apply.py  →  agent.json   ← eval does not do this
then record + run again  →  compare
```

```bash
pip install phthos-eval
cd examples/consumer
python loop.py
```

Expect `task_success_delta > 0`: the broken tool name `lookup` is remapped to `search` **by this consumer** after `change_class` is `tool`.

| File | Who owns it |
|------|-------------|
| `agent.json` | The consumer (starts with empty `rename_tools`) |
| `cases.json` | The consumer (trace templates) |
| `record.py` | The consumer (apply rename, emit dataset) |
| `apply.py` | The consumer (branch on `change_class`) |
| `loop.py` | The consumer (gate: re-eval improved) |

Offline compare without this loop:

```bash
phthos-eval run -d dataset.json -o before.json
# you change the agent
phthos-eval run -d dataset.json -o after.json
phthos-eval compare --before before.json --after after.json
```

Hosted / live: HTTPS + API key only. Contract: [`docs/CONSUMER.md`](../../docs/CONSUMER.md).
