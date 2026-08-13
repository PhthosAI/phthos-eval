from __future__ import annotations

import hmac
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qs, urlparse

from phthos_eval.compare import compare_diagnoses
from phthos_eval.constants import SCHEMA_VERSION
from phthos_eval.finetune_export import labeled_trajectories
from phthos_eval.gold import config_from_pack, pack_from_body, pack_to_dataset, source_hashes
from phthos_eval.live.access import (
    AccessError,
    enforce_ingest_limit,
    enforce_score_limit,
    enforce_seat_limit,
    require_role,
)
from phthos_eval.live.alerts import fire_score_drop, post_webhook
from phthos_eval.live.auth import (
    COOKIE_NAME,
    LOCAL_WORKSPACE,
    clear_session_cookie,
    hash_password,
    identity_from_headers,
    parse_cookie,
    session_cookie,
    valid_email,
    verify_password,
    verify_sso,
)
from phthos_eval.live.config import LiveSettings, should_sample
from phthos_eval.live.otel import is_otlp, otlp_to_traces
from phthos_eval.live.score import score_one_trace
from phthos_eval.live.store import Store
from phthos_eval.live.ui import AUTH_PAGE, HOSTED_PAGE, PAGE
from phthos_eval.plans import PLANS, ROLES, plan_of, public_catalog
from phthos_eval.runner import run_dataset


class LiveApp:
    def __init__(self, settings: LiveSettings) -> None:
        self.settings = settings
        self.store = Store(settings.db_path)
        self.config = settings.dataset_config()
        self.queue: Queue[str] = Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run_worker, daemon=True)

    def start(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.hosted:
            for ws in self.store.list_workspaces():
                days = int(plan_of(ws.get("plan")).get("retention_days") or 0)
                if days > 0:
                    self.store.prune(days, ws["id"])
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        self._worker.join(timeout=2)
        self.store.close()

    def wait_idle(self, timeout: float = 10) -> None:
        self.queue.join()

    def status_body(self) -> dict[str, Any]:
        return {
            "ok": True,
            "product": "phthos-eval",
            "mode": "hosted" if self.settings.hosted else "self-host",
            "schema_version": SCHEMA_VERSION,
            "sample_rate": self.settings.sample_rate,
            "judge": "on" if self.settings.live_judge else "off",
            "hosted": self.settings.hosted,
            "retention_days": self.settings.retention_days if self.settings.hosted else None,
            "hosted_judge": bool(self.settings.hosted_judge_api_key) if self.settings.hosted else False,
        }

    def ingest_native(
        self, payload: dict[str, Any], workspace_id: str = LOCAL_WORKSPACE
    ) -> dict[str, Any]:
        spans = payload.get("spans")
        if not isinstance(spans, list):
            raise TypeError("spans must be an array")
        ingest_id = str(uuid.uuid4())
        sample_key = str(payload.get("trace_id") or ingest_id)
        sampled = should_sample(sample_key, self.settings.sample_rate)
        trace = {"spans": spans}
        expected = payload.get("expected_tools")
        if expected is not None and not isinstance(expected, list):
            raise TypeError("expected_tools must be an array")
        if self.settings.hosted:
            enforce_ingest_limit(self.store, workspace_id, True)
            if sampled:
                enforce_score_limit(self.store, workspace_id, True)
        self.store.put_ingest(
            ingest_id,
            agent_id=str(payload.get("agent_id") or "default"),
            case_id=str(payload.get("case_id") or ingest_id),
            sampled=sampled,
            trace=trace,
            expected_tools=list(expected) if expected is not None else None,
            workspace_id=workspace_id,
        )
        if sampled:
            self.queue.put(ingest_id)
        return {"accepted": True, "sampled": sampled, "id": ingest_id}

    def ingest_otlp(
        self, payload: dict[str, Any], workspace_id: str = LOCAL_WORKSPACE
    ) -> dict[str, Any]:
        traces = otlp_to_traces(payload)
        results = []
        for item in traces:
            native = {
                "trace_id": item["trace_id"],
                "agent_id": "otel",
                "case_id": item["trace_id"],
                "spans": item["spans"],
            }
            results.append(self.ingest_native(native, workspace_id=workspace_id))
        sampled = sum(1 for r in results if r["sampled"])
        return {
            "accepted": True,
            "traces": len(results),
            "sampled": sampled,
            "ids": [r["id"] for r in results],
        }

    def scores(
        self,
        limit: int = 50,
        workspace_id: str = LOCAL_WORKSPACE,
        *,
        since: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        counts = self.store.counts(workspace_id)
        summary = self.store.summary(workspace_id)
        return {
            **counts,
            **summary,
            "sample_rate": self.settings.sample_rate,
            "judge": "on" if self.settings.live_judge else "off",
            "schema_version": SCHEMA_VERSION,
            "runs": [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "passed": bool(row["passed"]),
                    "change_class": row["change_class"],
                    "cost": row["cost"],
                    "policy_hits": row["policy_hits"],
                    "agent_id": row.get("agent_id"),
                    "gold_version": row.get("gold_version"),
                    "gold_stale": bool(row.get("gold_stale")),
                }
                for row in self.store.recent(
                    limit, workspace_id, since=since, agent_id=agent_id
                )
            ],
            "gold": self.store.list_gold_stale(workspace_id),
            "gold_stale": any(g["stale"] for g in self.store.list_gold_stale(workspace_id)),
        }

    def export(
        self,
        run_id: str,
        path: Path | None = None,
        workspace_id: str = LOCAL_WORKSPACE,
    ) -> dict[str, Any]:
        diagnosis = self.store.get_diagnosis(run_id, workspace_id)
        if not diagnosis:
            raise KeyError(run_id)
        ingest = self.store.get_ingest(run_id, workspace_id)
        if not ingest:
            raise KeyError(run_id)
        dest = path or self.settings.export_path
        return self.store.append_export(
            dest,
            diagnosis=diagnosis,
            ingest=ingest,
            config=self.config,
        )

    def export_bundle(self, workspace_id: str) -> dict[str, Any]:
        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "schema_version": SCHEMA_VERSION,
            "workspace_id": workspace_id,
            "diagnoses": self.store.list_diagnoses(workspace_id),
            "datasets": self.store.all_datasets(workspace_id),
        }

    def put_gold(self, workspace_id: str, agent_id: str, body: dict[str, Any]) -> dict[str, Any]:
        pack = pack_from_body(agent_id, body)
        stored = self.store.put_gold_pack(workspace_id, pack)
        return {"pack": stored, "stale": False}

    def get_gold(self, workspace_id: str, agent_id: str) -> dict[str, Any] | None:
        pack = self.store.active_gold(workspace_id, agent_id)
        if not pack:
            return None
        stale = self.store.gold_stale(workspace_id, agent_id)
        return {"pack": pack, "stale": stale, "version": pack.get("version"), "agent_id": agent_id}

    def sync_gold(self, workspace_id: str, agent_id: str, body: dict[str, Any]) -> dict[str, Any]:
        pack = self.store.active_gold(workspace_id, agent_id)
        if not pack:
            raise KeyError(agent_id)
        hashes = source_hashes(
            tool_schemas=body.get("tool_schemas") if isinstance(body.get("tool_schemas"), dict) else {},
            policy=body.get("policy") if isinstance(body.get("policy"), dict) else {},
            sop=body.get("sop") if body.get("sop") is not None else body.get("sop_clauses"),
        )
        stale = self.store.observe_gold_sources(workspace_id, agent_id, hashes)
        return {
            "agent_id": agent_id,
            "version": pack.get("version"),
            "stale": stale,
            "source_hashes": pack.get("source_hashes"),
            "observed": hashes,
        }

    def confirm_candidate(self, workspace_id: str, candidate_id: str) -> dict[str, Any]:
        cand = self.store.get_candidate(workspace_id, candidate_id)
        if not cand:
            raise KeyError(candidate_id)
        if cand["status"] != "pending":
            raise ValueError("candidate is not pending")
        agent_id = str(cand["agent_id"])
        pack = self.store.active_gold(workspace_id, agent_id)
        if not pack:
            raise KeyError(agent_id)
        cases = list(pack.get("cases") or [])
        case = dict(cand["case"])
        case_id = str(case.get("id") or cand["ingest_id"])
        if any(str(c.get("id")) == case_id for c in cases):
            self.store.set_candidate_status(workspace_id, candidate_id, "confirmed")
            return {"ok": True, "pack": pack, "stale": self.store.gold_stale(workspace_id, agent_id)}
        cases.append(case)
        new_pack = pack_from_body(
            agent_id,
            {
                **pack,
                "cases": cases,
                "sop_clauses": pack.get("sop_clauses"),
            },
        )
        stored = self.store.put_gold_pack(workspace_id, new_pack, align_observed=False)
        self.store.set_candidate_status(workspace_id, candidate_id, "confirmed")
        return {"ok": True, "pack": stored, "stale": self.store.gold_stale(workspace_id, agent_id)}

    def reject_candidate(self, workspace_id: str, candidate_id: str) -> dict[str, Any]:
        cand = self.store.get_candidate(workspace_id, candidate_id)
        if not cand:
            raise KeyError(candidate_id)
        self.store.set_candidate_status(workspace_id, candidate_id, "rejected")
        return {"ok": True, "id": candidate_id, "status": "rejected"}

    def signup(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        email = str(payload.get("email") or "")
        password = str(payload.get("password") or "")
        name = str(payload.get("workspace_name") or "workspace")
        if not valid_email(email):
            raise ValueError("invalid email")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        if self.store.get_user_by_email(email):
            raise FileExistsError("email already registered")
        workspace_id = self.store.create_workspace(name)
        user_id = self.store.create_user(email, hash_password(password), workspace_id)
        api_key = self.store.add_api_key(workspace_id)
        token = self.store.create_session(user_id, workspace_id)
        return (
            {
                "ok": True,
                "email": email.strip().lower(),
                "workspace_id": workspace_id,
                "api_key": api_key,
            },
            token,
        )

    def login(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        email = str(payload.get("email") or "")
        password = str(payload.get("password") or "")
        user = self.store.get_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            raise PermissionError("invalid credentials")
        token = self.store.create_session(user["id"], user["workspace_id"])
        return ({"ok": True, "workspace_id": user["workspace_id"]}, token)

    def sso_consume(self, email: str, workspace_id: str | None = None) -> tuple[dict[str, Any], str]:
        if not valid_email(email):
            raise ValueError("invalid email")
        user = self.store.get_user_by_email(email)
        if user:
            token = self.store.create_session(user["id"], user["workspace_id"])
            return (
                {"ok": True, "workspace_id": user["workspace_id"], "email": email.strip().lower()},
                token,
            )
        wid = workspace_id or self.store.create_workspace(email.split("@")[0])
        uid = self.store.create_user(email, "", wid, role="owner")
        token = self.store.create_session(uid, wid)
        return (
            {
                "ok": True,
                "workspace_id": wid,
                "email": email.strip().lower(),
                "created": True,
            },
            token,
        )

    def judge_for(
        self, workspace_id: str
    ) -> tuple[bool | dict[str, Any], str]:
        """Return (judge arg for run_dataset, source). source is off|env|byok|hosted."""
        if not self.settings.hosted:
            if self.settings.live_judge:
                return True, "env"
            return False, "off"
        ws = self.store.get_workspace(workspace_id) or {}
        plan = plan_of(ws.get("plan"))
        mode = str(ws.get("judge_mode") or "off")
        if mode == "hosted":
            if not plan.get("hosted_judge"):
                return False, "off"
            if not self.settings.hosted_judge_api_key:
                return False, "off"
            return (
                {
                    "api_key": self.settings.hosted_judge_api_key,
                    "base_url": self.settings.hosted_judge_base_url,
                    "model": self.settings.hosted_judge_model,
                },
                "hosted",
            )
        if mode == "byok" and ws.get("byok_key"):
            return (
                {
                    "api_key": ws.get("byok_key"),
                    "base_url": ws.get("byok_base_url"),
                    "model": ws.get("byok_model"),
                },
                "byok",
            )
        return False, "off"

    def usage_body(self, workspace_id: str) -> dict[str, Any]:
        ws = self.store.get_workspace(workspace_id) or {}
        plan = plan_of(ws.get("plan"))
        now = datetime.now(UTC)
        day_ago = (now - timedelta(days=1)).isoformat()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        return {
            "plan": plan["id"],
            "retention_days": plan["retention_days"],
            "ingest_last_24h": self.store.count_ingests_since(workspace_id, day_ago),
            "ingest_per_day": plan["ingest_per_day"],
            "scores_this_month": self.store.count_diagnoses_since(workspace_id, month_start),
            "scores_per_month": plan["scores_per_month"],
            "hosted_judge_this_month": self.store.count_usage(
                workspace_id, "hosted_judge", month_start
            ),
            "seats_used": self.store.count_users(workspace_id),
            "seats": plan["seats"],
            "hosted_judge_allowed": bool(plan.get("hosted_judge")),
            "saml_allowed": bool(plan.get("saml")),
        }

    def run_saved_dataset(
        self,
        workspace_id: str,
        dataset_id: str,
        *,
        agent_version: str | None = None,
    ) -> dict[str, Any]:
        row = self.store.get_dataset(workspace_id, dataset_id)
        if not row:
            raise KeyError(dataset_id)
        if self.settings.hosted:
            enforce_score_limit(self.store, workspace_id, True)
        judge_arg, source = self.judge_for(workspace_id)
        diagnosis = run_dataset(row["body"], judge=judge_arg)
        ingest_id = str(diagnosis.get("run_id") or uuid.uuid4())
        self.store.put_ingest(
            ingest_id,
            agent_id=str(agent_version or "dataset"),
            case_id=str(row["name"]),
            sampled=True,
            trace={"spans": [], "source": "dataset", "dataset_id": dataset_id},
            expected_tools=None,
            workspace_id=workspace_id,
            status="scored",
        )
        if diagnosis.get("run_id") != ingest_id:
            diagnosis = {**diagnosis, "run_id": ingest_id}
        self.store.put_diagnosis(ingest_id, diagnosis)
        if source == "hosted":
            self.store.add_usage(workspace_id, "hosted_judge")
        self._notify_diagnosis(workspace_id, diagnosis)
        return diagnosis

    def list_diagnoses(
        self,
        workspace_id: str,
        *,
        since: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "diagnoses": [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "passed": bool(row["passed"]),
                    "change_class": row["change_class"],
                    "cost": row["cost"],
                    "policy_hits": row["policy_hits"],
                    "agent_id": row.get("agent_id"),
                }
                for row in self.store.recent(
                    limit, workspace_id, since=since, agent_id=agent_id
                )
            ],
        }

    def compare_runs(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        before_id = str(payload.get("before_run_id") or payload.get("baseline_run_id") or "")
        after_id = str(payload.get("after_run_id") or "")
        dataset_id = str(payload.get("dataset_id") or "")
        agent_version = str(payload.get("agent_version") or "")
        if not after_id and dataset_id and agent_version:
            after_id = self._latest_run_id(
                workspace_id, agent_id=agent_version, dataset_id=dataset_id
            ) or ""
        if not before_id or not after_id:
            raise ValueError("before_run_id and after_run_id are required")
        before = self.store.get_diagnosis(before_id, workspace_id)
        after = self.store.get_diagnosis(after_id, workspace_id)
        if not before or not after:
            raise KeyError("diagnosis not found")
        return compare_diagnoses(before, after)

    def export_finetune(
        self,
        workspace_id: str,
        *,
        dataset_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        row = self.store.get_dataset(workspace_id, dataset_id)
        if not row:
            raise KeyError(dataset_id)
        rid = run_id or self._latest_run_id(workspace_id, dataset_id=dataset_id)
        if not rid:
            raise KeyError("diagnosis")
        diagnosis = self.store.get_diagnosis(rid, workspace_id)
        if not diagnosis:
            raise KeyError(rid)
        return labeled_trajectories(row["body"], diagnosis)

    def _latest_run_id(
        self,
        workspace_id: str,
        *,
        agent_id: str | None = None,
        dataset_id: str | None = None,
    ) -> str | None:
        for row in self.store.recent(200, workspace_id, agent_id=agent_id):
            rid = str(row["id"])
            if not dataset_id:
                return rid
            ingest = self.store.get_ingest(rid, workspace_id)
            if ingest:
                try:
                    trace = json.loads(ingest["trace_json"])
                except (json.JSONDecodeError, TypeError):
                    trace = {}
                if trace.get("dataset_id") == dataset_id:
                    return rid
            doc = self.store.get_diagnosis(rid, workspace_id) or {}
            if doc.get("dataset_id") == dataset_id:
                return rid
        return None

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            try:
                ingest_id = self.queue.get(timeout=0.2)
            except Empty:
                continue
            try:
                self._score(ingest_id)
            finally:
                self.queue.task_done()

    def _score(self, ingest_id: str) -> None:
        row = self.store.get_ingest(ingest_id)
        if not row:
            return
        try:
            trace = json.loads(row["trace_json"])
            expected = (
                json.loads(row["expected_tools_json"])
                if row.get("expected_tools_json")
                else None
            )
            workspace_id = str(row.get("workspace_id") or LOCAL_WORKSPACE)
            agent_id = str(row.get("agent_id") or "default")
            pack = self.store.active_gold(workspace_id, agent_id)
            stale = self.store.gold_stale(workspace_id, agent_id) if pack else False
            config = config_from_pack(pack, self.config) if pack else self.config
            if expected is None and config.get("default_expected_tools"):
                expected = list(config["default_expected_tools"])
            judge_arg, source = self.judge_for(workspace_id)
            diagnosis = score_one_trace(
                trace,
                config=config,
                case_id=str(row.get("case_id") or ingest_id),
                expected_tools=expected,
                run_id=ingest_id,
                judge=judge_arg,
                gold_version=str(pack["version"]) if pack else None,
                gold_stale=stale,
            )
            self.store.put_diagnosis(ingest_id, diagnosis)
            cases = diagnosis.get("cases") or []
            passed = bool(cases) and all(bool(c.get("passed")) for c in cases)
            change_class = str(diagnosis.get("change_class") or "none")
            if (not passed or change_class != "none") and row.get("sampled"):
                case = {
                    "id": str(row.get("case_id") or ingest_id),
                    "traces": [trace],
                }
                if expected:
                    case["expected_tools"] = expected
                self.store.put_candidate(
                    workspace_id,
                    agent_id=agent_id,
                    ingest_id=ingest_id,
                    case=case,
                    change_class=change_class,
                )
            if source == "hosted":
                self.store.add_usage(workspace_id, "hosted_judge")
            self._notify_diagnosis(workspace_id, diagnosis)
            self._maybe_alert(workspace_id)
        except Exception as exc:  # noqa: BLE001 - worker must keep running
            self.store.mark_error(ingest_id, str(exc))

    def _notify_diagnosis(self, workspace_id: str, diagnosis: dict[str, Any]) -> None:
        ws = self.store.get_workspace(workspace_id)
        url = (ws or {}).get("alert_webhook")
        if not url:
            return
        cases = diagnosis.get("cases") or []
        payload = {
            "event": "diagnosis",
            "run_id": diagnosis.get("run_id"),
            "change_class": diagnosis.get("change_class"),
            "passed": bool(cases) and all(bool(c.get("passed")) for c in cases),
            "schema_version": diagnosis.get("schema_version") or SCHEMA_VERSION,
            "gold_version": diagnosis.get("gold_version"),
            "gold_stale": bool(diagnosis.get("gold_stale")),
            "scores": {
                "task_success": (diagnosis.get("scores") or {}).get("task_success"),
            },
        }
        post_webhook(url, payload)

    def _maybe_alert(self, workspace_id: str) -> None:
        if not self.settings.hosted:
            return
        ws = self.store.get_workspace(workspace_id)
        if not ws:
            return
        counts = self.store.counts(workspace_id)
        summary = self.store.summary(workspace_id)
        new = summary.get("pass_rate")
        if counts["scored"] < 2 or new is None:
            self.store.set_last_pass_rate(workspace_id, new)
            return
        prev = ws.get("last_pass_rate")
        threshold = ws.get("alert_min_pass_rate")
        if threshold is None:
            threshold = self.settings.alert_min_pass_rate
        dropped = (
            prev is not None
            and float(prev) >= float(threshold)
            and float(new) < float(threshold)
        )
        self.store.set_last_pass_rate(workspace_id, new)
        if not dropped:
            return
        payload = {
            "event": "score_drop",
            "workspace_id": workspace_id,
            "pass_rate": new,
            "previous_pass_rate": prev,
            "threshold": float(threshold),
            "scored": counts["scored"],
        }
        channels = fire_score_drop(
            webhook_url=ws.get("alert_webhook"),
            alert_email=ws.get("alert_email"),
            smtp_host=self.settings.smtp_host,
            smtp_port=self.settings.smtp_port,
            smtp_user=self.settings.smtp_user,
            smtp_password=self.settings.smtp_password,
            smtp_from=self.settings.smtp_from,
            payload=payload,
        )
        payload["channels"] = channels
        self.store.log_alert(workspace_id, "score_drop", payload)


def make_handler(app: LiveApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            self._begin(
                204,
                extra={
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Phthos-Key",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
                },
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path in {"/health", "/v1/health", "/status", "/v1/status"}:
                self._json(200, app.status_body())
                return
            if path in {"/v1/plans"}:
                self._json(200, {"plans": public_catalog()})
                return
            if path in {"/login", "/signup"}:
                if not app.settings.hosted:
                    self._json(404, {"error": "not_found"})
                    return
                self._html(200, AUTH_PAGE)
                return
            if path in {"/", "/ui"}:
                if app.settings.hosted:
                    ident = self._identity()
                    if not ident:
                        self._redirect("/login")
                        return
                    self._html(200, HOSTED_PAGE)
                    return
                self._html(200, PAGE)
                return
            workspace_id = self._need_workspace()
            if workspace_id is None:
                return
            if path == "/v1/me":
                ws = app.store.get_workspace(workspace_id) or {}
                ident = self._identity() or {"role": "owner"}
                user = app.store.get_user(ident["user_id"]) if ident.get("user_id") else None
                plan = plan_of(ws.get("plan"))
                self._json(
                    200,
                    {
                        "workspace_id": workspace_id,
                        "workspace_name": ws.get("name"),
                        "email": (user or {}).get("email") or "",
                        "role": ident.get("role") or (user or {}).get("role") or "owner",
                        "plan": plan["id"],
                    },
                )
                return
            if path == "/v1/plan":
                ws = app.store.get_workspace(workspace_id) or {}
                plan = plan_of(ws.get("plan"))
                self._json(200, {"plan": plan, "catalog": public_catalog()})
                return
            if path == "/v1/usage":
                self._json(200, app.usage_body(workspace_id))
                return
            if path == "/v1/members":
                self._json(200, {"members": app.store.list_users(workspace_id)})
                return
            if path == "/v1/judge":
                ws = app.store.get_workspace(workspace_id) or {}
                self._json(
                    200,
                    {
                        "mode": ws.get("judge_mode") or "off",
                        "hosted_available": bool(app.settings.hosted_judge_api_key)
                        and bool(plan_of(ws.get("plan")).get("hosted_judge")),
                        "byok_configured": bool(ws.get("byok_key")),
                    },
                )
                return
            if path == "/v1/scores":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["50"])[0])
                since = (qs.get("since") or [None])[0]
                agent_id = (qs.get("agent_id") or [None])[0]
                self._json(
                    200,
                    app.scores(
                        limit=max(1, min(limit, 200)),
                        workspace_id=workspace_id,
                        since=since,
                        agent_id=agent_id,
                    ),
                )
                return
            if path == "/v1/datasets":
                self._json(200, {"datasets": app.store.list_datasets(workspace_id)})
                return
            if path.startswith("/v1/datasets/"):
                did = path[len("/v1/datasets/") :]
                row = app.store.get_dataset(workspace_id, did)
                if not row:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, row)
                return
            if path == "/v1/alerts":
                ws = app.store.get_workspace(workspace_id) or {}
                self._json(
                    200,
                    {
                        "webhook_url": ws.get("alert_webhook"),
                        "alert_email": ws.get("alert_email"),
                        "min_pass_rate": ws.get("alert_min_pass_rate")
                        if ws.get("alert_min_pass_rate") is not None
                        else app.settings.alert_min_pass_rate,
                        "recent": app.store.recent_alerts(workspace_id),
                    },
                )
                return
            if path == "/v1/export/finetune":
                qs = parse_qs(parsed.query)
                did = (qs.get("dataset_id") or [""])[0]
                rid = (qs.get("run_id") or [None])[0]
                if not did:
                    self._json(400, {"error": "dataset_id required"})
                    return
                try:
                    body = app.export_finetune(
                        workspace_id, dataset_id=did, run_id=rid or None
                    )
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, body)
                return
            if path == "/v1/export":
                self._json(200, app.export_bundle(workspace_id))
                return
            if path.startswith("/v1/gold/"):
                rest = path[len("/v1/gold/") :]
                if rest.endswith("/candidates"):
                    agent_id = rest[: -len("/candidates")].strip("/")
                    qs = parse_qs(parsed.query)
                    status = (qs.get("status") or ["pending"])[0]
                    self._json(
                        200,
                        {
                            "agent_id": agent_id,
                            "candidates": app.store.list_candidates(
                                workspace_id, agent_id, status=status
                            ),
                        },
                    )
                    return
                if rest.endswith("/export"):
                    agent_id = rest[: -len("/export")].strip("/")
                    pack = app.store.active_gold(workspace_id, agent_id)
                    if not pack:
                        self._json(404, {"error": "not_found"})
                        return
                    self._json(200, pack_to_dataset(pack))
                    return
                agent_id = rest.strip("/")
                if "/" in agent_id or not agent_id:
                    self._json(404, {"error": "not_found"})
                    return
                body = app.get_gold(workspace_id, agent_id)
                if not body:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, body)
                return
            if path == "/v1/diagnoses":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["50"])[0])
                since = (qs.get("since") or [None])[0]
                agent_id = (qs.get("agent_id") or [None])[0]
                self._json(
                    200,
                    app.list_diagnoses(
                        workspace_id,
                        since=since,
                        agent_id=agent_id,
                        limit=max(1, min(limit, 200)),
                    ),
                )
                return
            if path.startswith("/v1/diagnoses/"):
                rest = path[len("/v1/diagnoses/") :]
                if "/export" in rest:
                    self._json(405, {"error": "use POST to export"})
                    return
                doc = app.store.get_diagnosis(rest, workspace_id)
                if not doc:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, doc)
                return
            self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                payload = self._read_json()
            except (ValueError, TypeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            if path == "/v1/signup":
                if not app.settings.hosted:
                    self._json(404, {"error": "not_found"})
                    return
                try:
                    body, token = app.signup(payload)
                except FileExistsError as exc:
                    self._json(409, {"error": str(exc)})
                    return
                except sqlite3.IntegrityError:
                    self._json(409, {"error": "email already registered"})
                    return
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(201, body, extra={"Set-Cookie": session_cookie(token, secure=app.settings.cookie_secure)})
                return
            if path == "/v1/login":
                if not app.settings.hosted:
                    self._json(404, {"error": "not_found"})
                    return
                try:
                    body, token = app.login(payload)
                except PermissionError as exc:
                    self._json(401, {"error": str(exc)})
                    return
                self._json(200, body, extra={"Set-Cookie": session_cookie(token, secure=app.settings.cookie_secure)})
                return
            if path == "/v1/logout":
                raw = parse_cookie(self.headers.get("Cookie"), COOKIE_NAME)
                if raw:
                    app.store.delete_session(raw)
                self._json(
                    200,
                    {"ok": True},
                    extra={"Set-Cookie": clear_session_cookie(secure=app.settings.cookie_secure)},
                )
                return
            if path == "/v1/sso/consume":
                if not app.settings.hosted or not app.settings.sso_secret:
                    self._json(404, {"error": "not_found"})
                    return
                email = str(payload.get("email") or "")
                wid = str(payload.get("workspace_id") or "")
                exp = str(payload.get("exp") or "")
                sig = str(payload.get("sig") or "")
                if not exp or exp < datetime.now(UTC).isoformat():
                    self._json(401, {"error": "sso_expired"})
                    return
                if not verify_sso(app.settings.sso_secret, email, wid, exp, sig):
                    self._json(401, {"error": "sso_invalid"})
                    return
                try:
                    body, token = app.sso_consume(email, wid or None)
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(
                    200,
                    body,
                    extra={"Set-Cookie": session_cookie(token, secure=app.settings.cookie_secure)},
                )
                return
            if path == "/v1/ops/plan":
                secret = app.settings.ops_secret
                got = self.headers.get("X-Phthos-Ops") or ""
                if not secret or not got or not hmac.compare_digest(secret, got):
                    self._json(401, {"error": "unauthorized"})
                    return
                wid = str(payload.get("workspace_id") or "")
                plan_id = str(payload.get("plan") or "")
                if plan_id not in PLANS or plan_id == "self-host":
                    self._json(400, {"error": "invalid plan"})
                    return
                if not app.store.get_workspace(wid):
                    self._json(404, {"error": "not_found"})
                    return
                app.store.set_workspace_plan(wid, plan_id)
                self._json(200, {"ok": True, "workspace_id": wid, "plan": plan_id})
                return
            workspace_id = self._need_workspace()
            if workspace_id is None:
                return
            ident = self._identity() or {"role": "owner", "via": "local"}
            if path in {"/v1/traces", "/v1/otel/traces"}:
                try:
                    require_role(ident, "member")
                    if path.endswith("/otel/traces") or is_otlp(payload):
                        body = app.ingest_otlp(payload, workspace_id=workspace_id)
                    else:
                        body = app.ingest_native(payload, workspace_id=workspace_id)
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                except (ValueError, TypeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(202, body)
                return
            if path.startswith("/v1/diagnoses/") and path.endswith("/export"):
                try:
                    require_role(ident, "member")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                run_id = path[len("/v1/diagnoses/") : -len("/export")].strip("/")
                dest = Path(payload["path"]) if payload.get("path") else None
                try:
                    result = app.export(run_id, dest, workspace_id=workspace_id)
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, result)
                return
            if path == "/v1/datasets":
                try:
                    require_role(ident, "member")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                body = payload.get("dataset")
                if not isinstance(body, dict):
                    self._json(400, {"error": "dataset must be an object"})
                    return
                did = app.store.put_dataset(
                    workspace_id, str(payload.get("name") or "dataset"), body
                )
                self._json(201, {"id": did, "name": payload.get("name") or "dataset"})
                return
            if path.startswith("/v1/datasets/") and path.endswith("/run"):
                try:
                    require_role(ident, "member")
                    did = path[len("/v1/datasets/") : -len("/run")].strip("/")
                    version = payload.get("agent_version")
                    doc = app.run_saved_dataset(
                        workspace_id,
                        did,
                        agent_version=str(version) if version else None,
                    )
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(200, doc)
                return
            if path == "/v1/compare":
                try:
                    require_role(ident, "member")
                    body = app.compare_runs(workspace_id, payload)
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(200, body)
                return
            if path == "/v1/alerts":
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                webhook = payload.get("webhook_url")
                email = payload.get("alert_email")
                rate = payload.get("min_pass_rate")
                app.store.update_alerts(
                    workspace_id,
                    webhook=str(webhook) if webhook is not None else None,
                    email=str(email) if email is not None else None,
                    min_pass_rate=float(rate) if rate is not None else None,
                )
                ws = app.store.get_workspace(workspace_id) or {}
                self._json(
                    200,
                    {
                        "ok": True,
                        "webhook_url": ws.get("alert_webhook"),
                        "alert_email": ws.get("alert_email"),
                        "min_pass_rate": ws.get("alert_min_pass_rate"),
                    },
                )
                return
            if path == "/v1/members":
                try:
                    require_role(ident, "admin")
                    enforce_seat_limit(app.store, workspace_id)
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                email = str(payload.get("email") or "")
                password = str(payload.get("password") or "")
                role = str(payload.get("role") or "member")
                if role not in ROLES or role == "owner":
                    self._json(400, {"error": "invalid role"})
                    return
                if not valid_email(email) or len(password) < 8:
                    self._json(400, {"error": "invalid email or password"})
                    return
                if app.store.get_user_by_email(email):
                    self._json(409, {"error": "email already registered"})
                    return
                uid = app.store.create_user(
                    email, hash_password(password), workspace_id, role=role
                )
                self._json(201, {"id": uid, "email": email.strip().lower(), "role": role})
                return
            if path.startswith("/v1/members/") and path.endswith("/role"):
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                uid = path[len("/v1/members/") : -len("/role")].strip("/")
                role = str(payload.get("role") or "")
                if role not in ROLES or role == "owner":
                    self._json(400, {"error": "invalid role"})
                    return
                if not app.store.set_user_role(workspace_id, uid, role):
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, {"ok": True, "id": uid, "role": role})
                return
            if path == "/v1/judge":
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                mode = str(payload.get("mode") or "off")
                if mode not in {"off", "byok", "hosted"}:
                    self._json(400, {"error": "invalid mode"})
                    return
                ws = app.store.get_workspace(workspace_id) or {}
                plan = plan_of(ws.get("plan"))
                if mode == "hosted" and not plan.get("hosted_judge"):
                    self._json(403, {"error": "hosted_judge_requires_pro"})
                    return
                app.store.set_judge_settings(
                    workspace_id,
                    mode=mode,
                    byok_key=str(payload["api_key"]) if payload.get("api_key") else None,
                    byok_base_url=str(payload["base_url"]) if payload.get("base_url") else None,
                    byok_model=str(payload["model"]) if payload.get("model") else None,
                )
                self._json(200, {"ok": True, "mode": mode})
                return
            if path.startswith("/v1/gold/candidates/") and path.endswith("/confirm"):
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                if str(payload.get("source") or "").strip().lower() == "judge":
                    self._json(400, {"error": "judge_cannot_confirm"})
                    return
                cid = path[len("/v1/gold/candidates/") : -len("/confirm")].strip("/")
                try:
                    body = app.confirm_candidate(workspace_id, cid)
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(200, body)
                return
            if path.startswith("/v1/gold/candidates/") and path.endswith("/reject"):
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                cid = path[len("/v1/gold/candidates/") : -len("/reject")].strip("/")
                try:
                    body = app.reject_candidate(workspace_id, cid)
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, body)
                return
            if path.startswith("/v1/gold/") and path.endswith("/sync"):
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                agent_id = path[len("/v1/gold/") : -len("/sync")].strip("/")
                try:
                    body = app.sync_gold(workspace_id, agent_id, payload)
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, body)
                return
            if path.startswith("/v1/gold/"):
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                agent_id = path[len("/v1/gold/") :].strip("/")
                if not agent_id or "/" in agent_id:
                    self._json(404, {"error": "not_found"})
                    return
                try:
                    body = app.put_gold(workspace_id, agent_id, payload)
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(201, body)
                return
            self._json(404, {"error": "not_found"})

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                payload = self._read_json()
            except (ValueError, TypeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            workspace_id = self._need_workspace()
            if workspace_id is None:
                return
            ident = self._identity() or {"role": "owner", "via": "local"}
            if path.startswith("/v1/gold/"):
                try:
                    require_role(ident, "admin")
                except AccessError as exc:
                    self._json(exc.status, exc.body())
                    return
                agent_id = path[len("/v1/gold/") :].strip("/")
                if not agent_id or "/" in agent_id:
                    self._json(404, {"error": "not_found"})
                    return
                try:
                    body = app.put_gold(workspace_id, agent_id, payload)
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(201, body)
                return
            self._json(405, {"error": "method_not_allowed"})

        def _identity(self) -> dict[str, str] | None:
            return identity_from_headers(
                app.store,
                authorization=self.headers.get("Authorization"),
                x_key=self.headers.get("X-Phthos-Key"),
                cookie=self.headers.get("Cookie"),
            )

        def _need_workspace(self) -> str | None:
            if not app.settings.hosted:
                return LOCAL_WORKSPACE
            ident = self._identity()
            if not ident:
                self._json(401, {"error": "unauthorized"})
                return None
            return ident["workspace_id"]

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            if not raw:
                return {}
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("invalid json") from exc
            if not isinstance(data, dict):
                raise TypeError("body must be an object")
            return data

        def _json(
            self,
            status: int,
            body: dict[str, Any],
            extra: dict[str, str] | None = None,
        ) -> None:
            raw = json.dumps(body).encode("utf-8")
            headers = {"Content-Length": str(len(raw))}
            if extra:
                headers.update(extra)
            self._begin(status, "application/json", extra=headers)
            self.wfile.write(raw)

        def _html(self, status: int, page: str) -> None:
            raw = page.encode("utf-8")
            self._begin(
                status,
                "text/html; charset=utf-8",
                extra={"Content-Length": str(len(raw))},
            )
            self.wfile.write(raw)

        def _redirect(self, location: str) -> None:
            self._begin(302, extra={"Location": location, "Content-Length": "0"})

        def _begin(
            self,
            status: int,
            content_type: str = "application/json",
            extra: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()

    return Handler


def serve(settings: LiveSettings) -> None:
    app = LiveApp(settings)
    app.start()
    httpd = ThreadingHTTPServer((settings.host, settings.port), make_handler(app))
    display = settings.host if settings.host != "0.0.0.0" else "127.0.0.1"
    mode = "hosted" if settings.hosted else "self-host"
    print(
        f"phthos-eval live ({mode})  http://{display}:{httpd.server_address[1]}  "
        f"sample_rate={settings.sample_rate}  judge="
        f"{'on' if settings.live_judge else 'off'}  data={settings.data_dir}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopping", flush=True)
    finally:
        httpd.shutdown()
        app.stop()


def serve_in_thread(settings: LiveSettings) -> tuple[LiveApp, ThreadingHTTPServer, str]:
    """Start the engine (port 0 = ephemeral). Caller must shutdown the server."""
    app = LiveApp(settings)
    app.start()
    httpd = ThreadingHTTPServer((settings.host, settings.port), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address[:2]
    return app, httpd, f"http://{host}:{port}"
