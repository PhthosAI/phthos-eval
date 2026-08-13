from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from phthos_eval.plans import plan_of, role_at_least


class AccessError(Exception):
    def __init__(self, status: int, error: str, extra: dict[str, Any] | None = None) -> None:
        super().__init__(error)
        self.status = status
        self.error = error
        self.extra = extra or {}

    def body(self) -> dict[str, Any]:
        return {"error": self.error, **self.extra}


def require_role(ident: dict[str, str] | None, minimum: str) -> None:
    role = (ident or {}).get("role") or "viewer"
    if not role_at_least(role, minimum):
        raise AccessError(403, "forbidden", {"need_role": minimum, "role": role})


def enforce_ingest_limit(store: Any, workspace_id: str, hosted: bool) -> None:
    if not hosted:
        return
    ws = store.get_workspace(workspace_id) or {}
    plan = plan_of(ws.get("plan"))
    cap = plan.get("ingest_per_day")
    if cap is None:
        return
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    used = store.count_ingests_since(workspace_id, since)
    if used >= int(cap):
        raise AccessError(
            429,
            "rate_limited",
            {"limit": "ingest_per_day", "plan": plan["id"], "used": used, "cap": cap},
        )


def enforce_score_limit(store: Any, workspace_id: str, hosted: bool) -> None:
    if not hosted:
        return
    ws = store.get_workspace(workspace_id) or {}
    plan = plan_of(ws.get("plan"))
    cap = plan.get("scores_per_month")
    if cap is None:
        return
    now = datetime.now(UTC)
    since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = store.count_diagnoses_since(workspace_id, since)
    if used >= int(cap):
        raise AccessError(
            429,
            "rate_limited",
            {"limit": "scores_per_month", "plan": plan["id"], "used": used, "cap": cap},
        )


def enforce_seat_limit(store: Any, workspace_id: str) -> None:
    ws = store.get_workspace(workspace_id) or {}
    plan = plan_of(ws.get("plan"))
    cap = plan.get("seats")
    if cap is None:
        return
    used = store.count_users(workspace_id)
    if used >= int(cap):
        raise AccessError(
            403,
            "seat_limit",
            {"plan": plan["id"], "used": used, "cap": cap},
        )
