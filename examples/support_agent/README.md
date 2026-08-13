# Support-agent example

Recorded traces: look up an order, never issue a refund.

```bash
pip install phthos-eval
python -m phthos_eval run -d examples/support_agent/dataset.json -o diagnosis.json
```

`status-ok` should pass. `refund-denied` should fail (`policy`, and usually `wrong_tool`).
