from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qs, urlparse

from phthos_eval.live.config import LiveSettings, should_sample
from phthos_eval.live.otel import is_otlp, otlp_to_traces
from phthos_eval.live.score import score_one_trace
from phthos_eval.live.store import Store
from phthos_eval.live.ui import PAGE


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
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        self._worker.join(timeout=2)
        self.store.close()

    def wait_idle(self, timeout: float = 10) -> None:
        self.queue.join()

    def ingest_native(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        )
        if sampled:
            self.queue.put(ingest_id)
        return {"accepted": True, "sampled": sampled, "id": ingest_id}

    def ingest_otlp(self, payload: dict[str, Any]) -> dict[str, Any]:
        traces = otlp_to_traces(payload)
        results = []
        for item in traces:
            native = {
                "trace_id": item["trace_id"],
                "agent_id": "otel",
                "case_id": item["trace_id"],
                "spans": item["spans"],
            }
            results.append(self.ingest_native(native))
        sampled = sum(1 for r in results if r["sampled"])
        return {
            "accepted": True,
            "traces": len(results),
            "sampled": sampled,
            "ids": [r["id"] for r in results],
        }

    def scores(self, limit: int = 50) -> dict[str, Any]:
        counts = self.store.counts()
        summary = self.store.summary()
        return {
            **counts,
            **summary,
            "sample_rate": self.settings.sample_rate,
            "judge": "on" if self.settings.live_judge else "off",
            "runs": [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "passed": bool(row["passed"]),
                    "change_class": row["change_class"],
                    "cost": row["cost"],
                    "policy_hits": row["policy_hits"],
                }
                for row in self.store.recent(limit)
            ],
        }

    def export(self, run_id: str, path: Path | None = None) -> dict[str, Any]:
        diagnosis = self.store.get_diagnosis(run_id)
        if not diagnosis:
            raise KeyError(run_id)
        ingest = self.store.get_ingest(run_id)
        if not ingest:
            raise KeyError(run_id)
        dest = path or self.settings.export_path
        return self.store.append_export(
            dest,
            diagnosis=diagnosis,
            ingest=ingest,
            config=self.config,
        )

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
        except Exception as exc:  # noqa: BLE001 - worker must keep running
            self.store.mark_error(ingest_id, str(exc))


def make_handler(app: LiveApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            self._begin(204, extra={"Access-Control-Allow-Headers": "Content-Type"})

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path in {"/", "/ui"}:
                self._begin(200, "text/html; charset=utf-8")
                self.wfile.write(PAGE.encode("utf-8"))
                return
            if path in {"/health", "/v1/health"}:
                self._json(
                    200,
                    {
                        "ok": True,
                        "sample_rate": app.settings.sample_rate,
                        "judge": "on" if app.settings.live_judge else "off",
                    },
                )
                return
            if path == "/v1/scores":
                qs = parse_qs(parsed.query)
                limit = int((qs.get("limit") or ["50"])[0])
                self._json(200, app.scores(limit=max(1, min(limit, 200))))
                return
            if path.startswith("/v1/diagnoses/"):
                rest = path[len("/v1/diagnoses/") :]
                if "/export" in rest:
                    self._json(405, {"error": "use POST to export"})
                    return
                doc = app.store.get_diagnosis(rest)
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
            if path in {"/v1/traces", "/v1/otel/traces"}:
                try:
                    if path.endswith("/otel/traces") or is_otlp(payload):
                        body = app.ingest_otlp(payload)
                    else:
                        body = app.ingest_native(payload)
                except (ValueError, TypeError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(202, body)
                return
            if path.startswith("/v1/diagnoses/") and path.endswith("/export"):
                run_id = path[len("/v1/diagnoses/") : -len("/export")].strip("/")
                dest = Path(payload["path"]) if payload.get("path") else None
                try:
                    result = app.export(run_id, dest)
                except KeyError:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, result)
                return
            self._json(404, {"error": "not_found"})

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

        def _json(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode("utf-8")
            self._begin(status, "application/json", extra={"Content-Length": str(len(raw))})
            self.wfile.write(raw)

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
    print(
        f"phthos-eval live  http://{display}:{httpd.server_address[1]}  "
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
