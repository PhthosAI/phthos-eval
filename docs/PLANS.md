# Hosted plans

Money is **ops**, not whether the score is real. OSS / self-host (`phthos-eval live` without `--hosted`) is unlimited and never talks to Stripe.

| Plan | Price | Retention | Ingests / day | Scores / month | Seats | Hosted judge | SAML |
|------|-------|-----------|---------------|----------------|-------|--------------|------|
| Self-host (OSS) | $0 | yours | unlimited | unlimited | unlimited | no (BYOK only) | n/a |
| Free (hosted) | $0 | 30 days | 2,000 | 10,000 | 3 | no | no |
| Pro | $49 / month | 365 days | 100,000 | 500,000 | 25 | yes (metered) | yes |

Deterministic scorers and diagnosis schema **0.3.0** are on every plan. Going over a hosted volume cap returns HTTP 429; the score is not faked.

Hosted judge (Pro): we call a model with **our** key and meter `hosted_judge` usage (`GET /v1/usage`). BYOK remains available (`judge_mode=byok`). OSS has no hosted-judge dependency.

SAML and Stripe live in the **cloud overlay** (`phthos-eval-cloud`), not this package. The engine exposes `POST /v1/sso/consume` and `POST /v1/ops/plan` for that overlay.

See also [`PRIVACY.md`](PRIVACY.md) and [`hosted.md`](hosted.md).
