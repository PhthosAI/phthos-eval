# Support-agent dogfood

Recorded traces for a support agent (lookup order / no refunds). Lives in this repo — not Task AI or the gateway.

```bash
pip install "phthos-eval @ git+https://github.com/PhthosAI/phthos-eval.git"
python -m phthos_eval run -d examples/support_agent/dataset.json -o diagnosis.json
```

`refund-denied` should fail with `policy` (and `wrong_tool`). `status-ok` should pass.
