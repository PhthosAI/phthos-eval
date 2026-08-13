from __future__ import annotations

from typing import Any

# Hosted cloud plans. Self-host ignores these (unlimited, no billing).
# Money is ops (retention, SSO, hosted judges, seats), not whether the score is real.

PLANS: dict[str, dict[str, Any]] = {
    "self-host": {
        "id": "self-host",
        "name": "Self-host (OSS)",
        "price_usd_month": 0,
        "retention_days": 0,
        "ingest_per_day": None,
        "scores_per_month": None,
        "seats": None,
        "hosted_judge": False,
        "saml": False,
        "support": None,
        "sla": False,
    },
    "free": {
        "id": "free",
        "name": "Free (hosted)",
        "price_usd_month": 0,
        "retention_days": 30,
        "ingest_per_day": 2_000,
        "scores_per_month": 10_000,
        "seats": 3,
        "hosted_judge": False,
        "saml": False,
        "support": "community",
        "sla": False,
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price_usd_month": 49,
        "retention_days": 365,
        "ingest_per_day": 100_000,
        "scores_per_month": 500_000,
        "seats": 25,
        "hosted_judge": True,
        "saml": True,
        "support": "email, 1 business day",
        "sla": True,
    },
}

ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
ROLES = tuple(ROLE_RANK)


def plan_of(plan_id: str | None) -> dict[str, Any]:
    if plan_id in PLANS:
        return PLANS[plan_id]
    return PLANS["free"]


def role_at_least(role: str | None, minimum: str) -> bool:
    return ROLE_RANK.get(role or "viewer", 0) >= ROLE_RANK.get(minimum, 0)


def public_catalog() -> list[dict[str, Any]]:
    return [dict(p) for p in PLANS.values()]
