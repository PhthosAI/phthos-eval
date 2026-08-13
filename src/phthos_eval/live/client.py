from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin


class LiveError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"live engine HTTP {status}: {body}")
        self.status = status
        self.body = body


class LiveClient:
    """HTTP client for a self-hosted live engine. Ingest does not wait for scoring."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765", timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._json("GET", "health")

    def scores(self, limit: int = 50) -> dict[str, Any]:
        return self._json("GET", f"v1/scores?limit={int(limit)}")

    def diagnosis(self, run_id: str) -> dict[str, Any]:
        return self._json("GET", f"v1/diagnoses/{run_id}")

    def ingest(
        self,
        spans: list[dict[str, Any]],
        *,
        agent_id: str = "default",
        case_id: str | None = None,
        expected_tools: list[str] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_id": agent_id, "spans": spans}
        if case_id:
            body["case_id"] = case_id
        if expected_tools is not None:
            body["expected_tools"] = expected_tools
        if trace_id:
            body["trace_id"] = trace_id
        return self._json("POST", "v1/traces", body)

    def ingest_otlp(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "v1/otel/traces", payload)

    def export(self, run_id: str, path: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if path:
            body["path"] = path
        return self._json("POST", f"v1/diagnoses/{run_id}/export", body)

    def _json(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            urljoin(self.base_url, path),
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise LiveError(exc.code, err_body) from exc
