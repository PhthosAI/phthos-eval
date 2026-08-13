from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qs, urlparse

from phthos_eval.constants import SCHEMA_VERSION
from phthos_eval.live.alerts import fire_score_drop
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
)
from phthos_eval.live.config import LiveSettings, should_sample
from phthos_eval.live.otel import is_otlp, otlp_to_traces
from phthos_eval.live.score import score_one_trace
from phthos_eval.live.store import Store
from phthos_eval.live.ui import AUTH_PAGE, HOSTED_PAGE, PAGE
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
        if self.settings.hosted and self.settings.retention_days > 0:
            self.store.prune(self.settings.retention_days)
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

    def scores(self, limit: int = 50, workspace_id: str = LOCAL_WORKSPACE) -> dict[str, Any]:
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
                }
                for row in self.store.recent(limit, workspace_id)
            ],
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

    def run_saved_dataset(self, workspace_id: str, dataset_id: str) -> dict[str, Any]:
        row = self.store.get_dataset(workspace_id, dataset_id)
        if not row:
            raise KeyError(dataset_id)
        diagnosis = run_dataset(row["body"], judge=self.settings.live_judge)
        ingest_id = str(diagnosis.get("run_id") or uuid.uuid4())
        self.store.put_ingest(
            ingest_id,
            agent_id="dataset",
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
        return diagnosis

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
            diagnosis = score_one_trace(
                trace,
                config=self.config,
                case_id=str(row.get("case_id") or ingest_id),
                expected_tools=expected,
                run_id=ingest_id,
                judge=self.settings.live_judge,
            )
            self.store.put_diagnosis(ingest_id, diagnosis)
            self._maybe_alert(str(row.get("workspace_id") or LOCAL_WORKSPACE))
        except Exception as exc:  # noqa: BLE001 - worker must keep running
            self.store.mark_error(ingest_id, str(exc))

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
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Phthos-Key"
                },
            )

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path in {"/health", "/v1/health", "/status", "/v1/status"}:
                self._json(200, app.status_body())
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
                ident = self._identity() or {}
                user = app.store.get_user(ident["user_id"]) if ident.get("user_id") else None
                self._json(
                    200,
                    {
                        "workspace_id": workspace_id,
                        "workspace_name": ws.get("name"),
                        "email": (user or {}).get("email") or "",
                    },
                )
                return
            if path == "/v1/scores":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["50"])[0])
                self._json(200, app.scores(limit=max(1, min(limit, 200)), workspace_id=workspace_id))
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
            if path == "/v1/export":
                self._json(200, app.export_bundle(workspace_id))
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
            workspace_id = self._need_workspace()
            if workspace_id is None:
                return
            if path in {"/v1/traces", "/v1/otel/traces"}:
                try:
                    if path.endswith("/otel/traces") or is_otlp(payload):
                        body = app.ingest_otlp(payload, workspace_id=workspace_id)
                    else:
                        body = app.ingest_native(payload, workspace_id=workspace_id)
                except (ValueError, TypeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(202, body)
                return
            if path.startswith("/v1/diagnoses/") and path.endswith("/export"):
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
                did = path[len("/v1/datasets/") : -len("/run")].strip("/")
                try:
                    doc = app.run_saved_dataset(workspace_id, did)
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(200, doc)
                return
            if path == "/v1/alerts":
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
            self._json(404, {"error": "not_found"})

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
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
