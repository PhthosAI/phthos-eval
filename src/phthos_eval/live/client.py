from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode, urljoin


class LiveError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"live engine HTTP {status}: {body}")
        self.status = status
        self.body = body


class LiveClient:
    """HTTP client for a live engine (self-host or hosted). Ingest does not wait for scoring."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        timeout: float = 10,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.api_key = api_key
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))

    def health(self) -> dict[str, Any]:
        return self._json("GET", "health")

    def status(self) -> dict[str, Any]:
        return self._json("GET", "status")

    def scores(
        self,
        limit: int = 50,
        *,
        since: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return self._json("GET", "v1/scores" + self._qs(limit=limit, since=since, agent_id=agent_id))

    def diagnoses(
        self,
        *,
        since: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._json(
            "GET",
            "v1/diagnoses" + self._qs(since=since, agent_id=agent_id, limit=limit),
        )

    def diagnosis(self, run_id: str) -> dict[str, Any]:
        return self._json("GET", f"v1/diagnoses/{run_id}")

    def me(self) -> dict[str, Any]:
        return self._json("GET", "v1/me")

    def signup(self, email: str, password: str, workspace_name: str = "workspace") -> dict[str, Any]:
        return self._json(
            "POST",
            "v1/signup",
            {"email": email, "password": password, "workspace_name": workspace_name},
        )

    def login(self, email: str, password: str) -> dict[str, Any]:
        return self._json("POST", "v1/login", {"email": email, "password": password})

    def logout(self) -> dict[str, Any]:
        return self._json("POST", "v1/logout", {})

    def put_dataset(self, name: str, dataset: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "v1/datasets", {"name": name, "dataset": dataset})

    def datasets(self) -> dict[str, Any]:
        return self._json("GET", "v1/datasets")

    def dataset(self, dataset_id: str) -> dict[str, Any]:
        return self._json("GET", f"v1/datasets/{dataset_id}")

    def run_dataset(self, dataset_id: str, *, agent_version: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if agent_version:
            body["agent_version"] = agent_version
        return self._json("POST", f"v1/datasets/{dataset_id}/run", body)

    def compare(
        self,
        *,
        before_run_id: str | None = None,
        after_run_id: str | None = None,
        dataset_id: str | None = None,
        agent_version: str | None = None,
        baseline_run_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if before_run_id:
            body["before_run_id"] = before_run_id
        if after_run_id:
            body["after_run_id"] = after_run_id
        if dataset_id:
            body["dataset_id"] = dataset_id
        if agent_version:
            body["agent_version"] = agent_version
        if baseline_run_id:
            body["baseline_run_id"] = baseline_run_id
        return self._json("POST", "v1/compare", body)

    def export_bundle(self) -> dict[str, Any]:
        return self._json("GET", "v1/export")

    def export_finetune(self, dataset_id: str, *, run_id: str | None = None) -> dict[str, Any]:
        return self._json(
            "GET",
            "v1/export/finetune" + self._qs(dataset_id=dataset_id, run_id=run_id),
        )

    def set_alerts(
        self,
        *,
        webhook_url: str | None = None,
        alert_email: str | None = None,
        min_pass_rate: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if webhook_url is not None:
            body["webhook_url"] = webhook_url
        if alert_email is not None:
            body["alert_email"] = alert_email
        if min_pass_rate is not None:
            body["min_pass_rate"] = min_pass_rate
        return self._json("POST", "v1/alerts", body)

    def alerts(self) -> dict[str, Any]:
        return self._json("GET", "v1/alerts")

    def plans(self) -> dict[str, Any]:
        return self._json("GET", "v1/plans")

    def plan(self) -> dict[str, Any]:
        return self._json("GET", "v1/plan")

    def usage(self) -> dict[str, Any]:
        return self._json("GET", "v1/usage")

    def members(self) -> dict[str, Any]:
        return self._json("GET", "v1/members")

    def invite(self, email: str, password: str, role: str = "member") -> dict[str, Any]:
        return self._json(
            "POST", "v1/members", {"email": email, "password": password, "role": role}
        )

    def set_role(self, user_id: str, role: str) -> dict[str, Any]:
        return self._json("POST", f"v1/members/{user_id}/role", {"role": role})

    def judge_settings(self) -> dict[str, Any]:
        return self._json("GET", "v1/judge")

    def set_judge(
        self,
        mode: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"mode": mode}
        if api_key is not None:
            body["api_key"] = api_key
        if base_url is not None:
            body["base_url"] = base_url
        if model is not None:
            body["model"] = model
        return self._json("POST", "v1/judge", body)

    def set_plan_ops(self, workspace_id: str, plan: str, ops_secret: str) -> dict[str, Any]:
        return self._json(
            "POST",
            "v1/ops/plan",
            {"workspace_id": workspace_id, "plan": plan},
            extra_headers={"X-Phthos-Ops": ops_secret},
        )

    def sso_consume(
        self,
        email: str,
        *,
        workspace_id: str,
        exp: str,
        sig: str,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            "v1/sso/consume",
            {"email": email, "workspace_id": workspace_id, "exp": exp, "sig": sig},
        )

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

    def _json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(
            urljoin(self.base_url, path),
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise LiveError(exc.code, err_body) from exc

    def _qs(self, **kwargs: Any) -> str:
        parts = {k: str(v) for k, v in kwargs.items() if v is not None}
        if not parts:
            return ""
        return "?" + urlencode(parts)
