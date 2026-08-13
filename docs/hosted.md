# Hosted mode

Same live engine as [self-host](../examples/live/README.md). We (or you) set `PHTHOS_EVAL_HOSTED=1` / `--hosted` and expose a URL. **OSS self-host is unchanged** if you omit that flag.

Stripe, SAML ACS, and billing UI are the **cloud overlay** (`phthos-eval-cloud`), not this package. The engine has plan/RBAC/SSO hooks: [`PLANS.md`](PLANS.md).

## Run it

```bash
phthos-eval live --hosted --host 0.0.0.0 -c examples/live/config.json
# or
PHTHOS_EVAL_HOSTED=1 docker compose -f docker-compose.hosted.yml up --build
```

Open the URL → sign up. Copy the API key (shown once).

| Env | Meaning |
|-----|---------|
| `PHTHOS_EVAL_HOSTED` | `1` = require login / Bearer key; isolate tenants |
| `PHTHOS_EVAL_RETENTION_DAYS` | Default `30` |
| `PHTHOS_EVAL_ALERT_MIN_PASS_RATE` | Default `0.8` until the workspace overrides it |
| `PHTHOS_EVAL_SMTP_HOST` / `PORT` / `USER` / `PASSWORD` / `FROM` | Email alerts (optional) |
| `PHTHOS_EVAL_PUBLIC_URL` | `https://…` so session cookies get `Secure` |
| `PHTHOS_EVAL_OPS_SECRET` | `X-Phthos-Ops` to set workspace plan |
| `PHTHOS_EVAL_SSO_SECRET` | HMAC for `POST /v1/sso/consume` |
| `PHTHOS_EVAL_HOSTED_JUDGE_API_KEY` | Our key for Pro hosted-judge (metered). Unset on OSS. |

## Auth

- UI: email + password cookie (`POST /v1/signup`, `/v1/login`)
- API / CI: `Authorization: Bearer pk_…` or `X-Phthos-Key`
- `/health` and `/status` stay public (no tenant data)

```python
from phthos_eval.live import LiveClient

client = LiveClient("https://eval.example.com", api_key="pk_…")
client.ingest(spans=[...], agent_id="support", expected_tools=["search"])
```

Team B cannot `GET /v1/diagnoses/{id}` for team A’s runs.

## Dashboard

Logged-in UI: live scores, history, datasets (upload / run / download), alerts (webhook and optional email). No prompt editor. Eval does not apply a fix.

## Offline + CI

Keep using the pip package locally (no Docker, no cloud):

```bash
pip install phthos-eval
phthos-eval run -d eval/dataset.json -o diagnosis.json --fail-on-findings
```

Or the same dataset against the hosted engine:

```python
client = LiveClient(os.environ["PHTHOS_EVAL_CLOUD_URL"], api_key=os.environ["PHTHOS_EVAL_CLOUD_KEY"])
created = client.put_dataset("ci", json.load(open("eval/dataset.json")))
before = client.run_dataset(created["id"], agent_version="v1")
# you change the agent outside eval, then:
after = client.run_dataset(created["id"], agent_version="v2")
client.compare(before_run_id=before["run_id"], after_run_id=after["run_id"])
```

Same diagnosis schema as OSS (0.3.0, including `gold_version`). Consumer contract (poll, webhook, living gold, fine-tune export): [`CONSUMER.md`](CONSUMER.md), [`GOLD.md`](GOLD.md). Hosted: GET gold is any workspace user; PUT / sync / confirm / reject need **admin**.

Export everything: `GET /v1/export`. Labeled trajectories for **their** trainer: `GET /v1/export/finetune?dataset_id=`.

## Status

`GET /status` → `{ ok, product, mode: "hosted"|"self-host", schema_version, sample_rate, judge, retention_days }`.
