from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from phthos_eval.live.auth import (
    LOCAL_WORKSPACE,
    hash_token,
    new_api_key,
    new_session_token,
    normalize_email,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, spec: str) -> None:
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ingests (
                  id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  agent_id TEXT,
                  case_id TEXT,
                  sampled INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  trace_json TEXT NOT NULL,
                  expected_tools_json TEXT,
                  error TEXT,
                  workspace_id TEXT NOT NULL DEFAULT 'local'
                );
                CREATE TABLE IF NOT EXISTS diagnoses (
                  id TEXT PRIMARY KEY,
                  ingest_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  passed INTEGER NOT NULL,
                  change_class TEXT,
                  cost REAL,
                  policy_hits INTEGER,
                  diagnosis_json TEXT NOT NULL,
                  workspace_id TEXT NOT NULL DEFAULT 'local'
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  alert_webhook TEXT,
                  alert_email TEXT,
                  alert_min_pass_rate REAL,
                  last_pass_rate REAL,
                  plan TEXT NOT NULL DEFAULT 'free',
                  judge_mode TEXT NOT NULL DEFAULT 'off',
                  byok_key TEXT,
                  byok_base_url TEXT,
                  byok_model TEXT
                );
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  password_hash TEXT NOT NULL,
                  workspace_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'owner'
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                  id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  token_hash TEXT NOT NULL UNIQUE,
                  prefix TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  token_hash TEXT NOT NULL UNIQUE,
                  user_id TEXT NOT NULL,
                  workspace_id TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS datasets (
                  id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  body_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                  id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                  id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  kind TEXT NOT NULL
                );
                """
            )
            _ensure_column(self._conn, "ingests", "workspace_id", "TEXT NOT NULL DEFAULT 'local'")
            _ensure_column(self._conn, "diagnoses", "workspace_id", "TEXT NOT NULL DEFAULT 'local'")
            _ensure_column(self._conn, "workspaces", "plan", "TEXT NOT NULL DEFAULT 'free'")
            _ensure_column(self._conn, "workspaces", "judge_mode", "TEXT NOT NULL DEFAULT 'off'")
            _ensure_column(self._conn, "workspaces", "byok_key", "TEXT")
            _ensure_column(self._conn, "workspaces", "byok_base_url", "TEXT")
            _ensure_column(self._conn, "workspaces", "byok_model", "TEXT")
            _ensure_column(self._conn, "users", "role", "TEXT NOT NULL DEFAULT 'owner'")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingests_ws ON ingests(workspace_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_diagnoses_ws ON diagnoses(workspace_id, created_at)"
            )
            self._ensure_local_workspace()
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gold_packs (
                  id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  agent_id TEXT NOT NULL,
                  version TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  active INTEGER NOT NULL,
                  pack_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gold_observed (
                  workspace_id TEXT NOT NULL,
                  agent_id TEXT NOT NULL,
                  tools_hash TEXT,
                  policy_hash TEXT,
                  sop_hash TEXT,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (workspace_id, agent_id)
                );
                CREATE TABLE IF NOT EXISTS gold_candidates (
                  id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  agent_id TEXT NOT NULL,
                  ingest_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  case_json TEXT NOT NULL,
                  change_class TEXT,
                  UNIQUE (workspace_id, ingest_id)
                );
                CREATE INDEX IF NOT EXISTS idx_gold_packs_agent
                  ON gold_packs(workspace_id, agent_id, active);
                CREATE INDEX IF NOT EXISTS idx_gold_cand
                  ON gold_candidates(workspace_id, agent_id, status);
                """
            )
            _ensure_column(self._conn, "diagnoses", "gold_version", "TEXT")
            _ensure_column(self._conn, "diagnoses", "gold_stale", "INTEGER NOT NULL DEFAULT 0")
            self._conn.commit()

    def _ensure_local_workspace(self) -> None:
        row = self._conn.execute(
            "SELECT id FROM workspaces WHERE id = ?", (LOCAL_WORKSPACE,)
        ).fetchone()
        if not row:
            self._conn.execute(
                "INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?)",
                (LOCAL_WORKSPACE, "local", _now()),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def put_ingest(
        self,
        ingest_id: str,
        *,
        agent_id: str | None,
        case_id: str | None,
        sampled: bool,
        trace: dict[str, Any],
        expected_tools: list[str] | None,
        workspace_id: str = LOCAL_WORKSPACE,
        status: str | None = None,
    ) -> None:
        row_status = status or ("queued" if sampled else "skipped")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO ingests (
                  id, created_at, agent_id, case_id, sampled, status,
                  trace_json, expected_tools_json, error, workspace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    ingest_id,
                    _now(),
                    agent_id,
                    case_id,
                    int(sampled),
                    row_status,
                    json.dumps(trace),
                    json.dumps(expected_tools) if expected_tools is not None else None,
                    workspace_id,
                ),
            )
            self._conn.commit()

    def mark_error(self, ingest_id: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE ingests SET status = 'error', error = ? WHERE id = ?",
                (error, ingest_id),
            )
            self._conn.commit()

    def put_diagnosis(self, ingest_id: str, diagnosis: dict[str, Any]) -> None:
        scores = diagnosis.get("scores") or {}
        passed = bool(diagnosis.get("cases") and diagnosis["cases"][0].get("passed"))
        with self._lock:
            ingest = self._conn.execute(
                "SELECT workspace_id FROM ingests WHERE id = ?",
                (ingest_id,),
            ).fetchone()
            workspace_id = ingest["workspace_id"] if ingest else LOCAL_WORKSPACE
            self._conn.execute(
                """
                INSERT OR REPLACE INTO diagnoses (
                  id, ingest_id, created_at, passed, change_class, cost,
                  policy_hits, diagnosis_json, workspace_id, gold_version, gold_stale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    diagnosis.get("run_id") or ingest_id,
                    ingest_id,
                    _now(),
                    int(passed),
                    diagnosis.get("change_class"),
                    scores.get("cost"),
                    scores.get("policy_hits"),
                    json.dumps(diagnosis),
                    workspace_id,
                    diagnosis.get("gold_version"),
                    int(bool(diagnosis.get("gold_stale"))),
                ),
            )
            self._conn.execute(
                "UPDATE ingests SET status = 'scored', error = NULL WHERE id = ?",
                (ingest_id,),
            )
            self._conn.commit()

    def get_diagnosis(
        self, run_id: str, workspace_id: str | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            if workspace_id is None:
                row = self._conn.execute(
                    "SELECT diagnosis_json FROM diagnoses WHERE id = ?",
                    (run_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT diagnosis_json FROM diagnoses WHERE id = ? AND workspace_id = ?",
                    (run_id, workspace_id),
                ).fetchone()
        if not row:
            return None
        return json.loads(row["diagnosis_json"])

    def get_ingest(
        self, ingest_id: str, workspace_id: str | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            if workspace_id is None:
                row = self._conn.execute(
                    "SELECT * FROM ingests WHERE id = ?",
                    (ingest_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM ingests WHERE id = ? AND workspace_id = ?",
                    (ingest_id, workspace_id),
                ).fetchone()
        if not row:
            return None
        return dict(row)

    def counts(self, workspace_id: str = LOCAL_WORKSPACE) -> dict[str, int]:
        with self._lock:
            received = self._conn.execute(
                "SELECT COUNT(*) FROM ingests WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()[0]
            sampled = self._conn.execute(
                "SELECT COUNT(*) FROM ingests WHERE sampled = 1 AND workspace_id = ?",
                (workspace_id,),
            ).fetchone()[0]
            scored = self._conn.execute(
                "SELECT COUNT(*) FROM diagnoses WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()[0]
        return {
            "received": int(received),
            "sampled": int(sampled),
            "scored": int(scored),
        }

    def recent(
        self,
        limit: int = 50,
        workspace_id: str = LOCAL_WORKSPACE,
        *,
        since: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where = ["d.workspace_id = ?"]
        args: list[Any] = [workspace_id]
        if since:
            where.append("d.created_at >= ?")
            args.append(since)
        if agent_id:
            where.append("i.agent_id = ?")
            args.append(agent_id)
        args.append(limit)
        sql = f"""
                SELECT d.id, d.created_at, d.passed, d.change_class, d.cost, d.policy_hits,
                       i.agent_id, d.gold_version, d.gold_stale
                FROM diagnoses d
                LEFT JOIN ingests i ON i.id = d.ingest_id
                WHERE {' AND '.join(where)}
                ORDER BY d.created_at DESC
                LIMIT ?
                """
        with self._lock:
            rows = self._conn.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]

    def summary(self, workspace_id: str = LOCAL_WORKSPACE) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                  COUNT(*) AS n,
                  AVG(passed) AS pass_rate,
                  SUM(cost) AS cost,
                  SUM(policy_hits) AS policy_hits
                FROM diagnoses
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            ).fetchone()
        n = int(row["n"] or 0)
        return {
            "pass_rate": float(row["pass_rate"]) if n and row["pass_rate"] is not None else None,
            "cost": float(row["cost"]) if row["cost"] is not None else 0.0,
            "policy_hits": int(row["policy_hits"] or 0),
        }

    def list_diagnoses(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT diagnosis_json FROM diagnoses
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [json.loads(r["diagnosis_json"]) for r in rows]

    def prune(self, days: int, workspace_id: str | None = None) -> int:
        if days <= 0:
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._lock:
            if workspace_id:
                cur = self._conn.execute(
                    "DELETE FROM diagnoses WHERE created_at < ? AND workspace_id = ?",
                    (cutoff, workspace_id),
                )
                n = int(cur.rowcount or 0)
                self._conn.execute(
                    "DELETE FROM ingests WHERE created_at < ? AND workspace_id = ?",
                    (cutoff, workspace_id),
                )
            else:
                cur = self._conn.execute("DELETE FROM diagnoses WHERE created_at < ?", (cutoff,))
                n = int(cur.rowcount or 0)
                self._conn.execute("DELETE FROM ingests WHERE created_at < ?", (cutoff,))
            self._conn.commit()
        return n

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM workspaces").fetchall()
        return [dict(r) for r in rows]

    def set_workspace_plan(self, workspace_id: str, plan: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE workspaces SET plan = ? WHERE id = ?",
                (plan, workspace_id),
            )
            self._conn.commit()

    def set_judge_settings(
        self,
        workspace_id: str,
        *,
        mode: str,
        byok_key: str | None = None,
        byok_base_url: str | None = None,
        byok_model: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE workspaces
                SET judge_mode = ?,
                    byok_key = COALESCE(?, byok_key),
                    byok_base_url = COALESCE(?, byok_base_url),
                    byok_model = COALESCE(?, byok_model)
                WHERE id = ?
                """,
                (mode, byok_key, byok_base_url, byok_model, workspace_id),
            )
            self._conn.commit()

    def create_workspace(self, name: str) -> str:
        wid = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO workspaces (id, name, created_at, plan) VALUES (?, ?, ?, ?)",
                (wid, name.strip() or "workspace", _now(), "free"),
            )
            self._conn.commit()
        return wid

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_user(
        self, email: str, password_hash: str, workspace_id: str, role: str = "owner"
    ) -> str:
        uid = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (id, email, password_hash, workspace_id, created_at, role)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uid, normalize_email(email), password_hash, workspace_id, _now(), role),
            )
            self._conn.commit()
        return uid

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalize_email(email),),
            ).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, email, role, created_at FROM users
                WHERE workspace_id = ?
                ORDER BY created_at
                """,
                (workspace_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_users(self, workspace_id: str) -> int:
        with self._lock:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM users WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()[0]
        return int(n)

    def set_user_role(self, workspace_id: str, user_id: str, role: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE users SET role = ? WHERE id = ? AND workspace_id = ?",
                (role, user_id, workspace_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def count_ingests_since(self, workspace_id: str, since: str) -> int:
        with self._lock:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM ingests WHERE workspace_id = ? AND created_at >= ?",
                (workspace_id, since),
            ).fetchone()[0]
        return int(n)

    def count_diagnoses_since(self, workspace_id: str, since: str) -> int:
        with self._lock:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM diagnoses WHERE workspace_id = ? AND created_at >= ?",
                (workspace_id, since),
            ).fetchone()[0]
        return int(n)

    def add_usage(self, workspace_id: str, kind: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO usage_events (id, workspace_id, created_at, kind)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), workspace_id, _now(), kind),
            )
            self._conn.commit()

    def count_usage(self, workspace_id: str, kind: str, since: str | None = None) -> int:
        with self._lock:
            if since:
                n = self._conn.execute(
                    """
                    SELECT COUNT(*) FROM usage_events
                    WHERE workspace_id = ? AND kind = ? AND created_at >= ?
                    """,
                    (workspace_id, kind, since),
                ).fetchone()[0]
            else:
                n = self._conn.execute(
                    "SELECT COUNT(*) FROM usage_events WHERE workspace_id = ? AND kind = ?",
                    (workspace_id, kind),
                ).fetchone()[0]
        return int(n)

    def add_api_key(self, workspace_id: str) -> str:
        raw, digest, prefix = new_api_key()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO api_keys (id, workspace_id, token_hash, prefix, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), workspace_id, digest, prefix, _now()),
            )
            self._conn.commit()
        return raw

    def workspace_for_api_key(self, raw: str) -> dict[str, str] | None:
        digest = hash_token(raw)
        with self._lock:
            row = self._conn.execute(
                "SELECT workspace_id FROM api_keys WHERE token_hash = ?",
                (digest,),
            ).fetchone()
        if not row:
            return None
        return {"workspace_id": row["workspace_id"], "user_id": "", "role": "admin"}

    def create_session(self, user_id: str, workspace_id: str, days: int = 7) -> str:
        raw, digest = new_session_token()
        expires = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (id, token_hash, user_id, workspace_id, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), digest, user_id, workspace_id, expires),
            )
            self._conn.commit()
        return raw

    def workspace_for_session(self, raw: str) -> dict[str, str] | None:
        digest = hash_token(raw)
        now = _now()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT user_id, workspace_id, expires_at FROM sessions
                WHERE token_hash = ?
                """,
                (digest,),
            ).fetchone()
        if not row:
            return None
        if str(row["expires_at"]) < now:
            return None
        user = self.get_user(row["user_id"])
        role = (user or {}).get("role") or "owner"
        return {"user_id": row["user_id"], "workspace_id": row["workspace_id"], "role": str(role)}

    def delete_session(self, raw: str) -> None:
        digest = hash_token(raw)
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
            self._conn.commit()

    def update_alerts(
        self,
        workspace_id: str,
        *,
        webhook: str | None = None,
        email: str | None = None,
        min_pass_rate: float | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE workspaces
                SET alert_webhook = COALESCE(?, alert_webhook),
                    alert_email = COALESCE(?, alert_email),
                    alert_min_pass_rate = COALESCE(?, alert_min_pass_rate)
                WHERE id = ?
                """,
                (webhook, email, min_pass_rate, workspace_id),
            )
            self._conn.commit()

    def set_last_pass_rate(self, workspace_id: str, rate: float | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE workspaces SET last_pass_rate = ? WHERE id = ?",
                (rate, workspace_id),
            )
            self._conn.commit()

    def log_alert(self, workspace_id: str, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO alerts (id, workspace_id, created_at, kind, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), workspace_id, _now(), kind, json.dumps(payload)),
            )
            self._conn.commit()

    def recent_alerts(self, workspace_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, created_at, kind, payload_json FROM alerts
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (workspace_id, limit),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            out.append(item)
        return out

    def put_dataset(self, workspace_id: str, name: str, body: dict[str, Any]) -> str:
        did = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO datasets (id, workspace_id, name, body_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (did, workspace_id, name.strip() or "dataset", json.dumps(body), _now()),
            )
            self._conn.commit()
        return did

    def list_datasets(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, name, created_at FROM datasets
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_dataset(self, workspace_id: str, dataset_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, name, created_at, body_json FROM datasets
                WHERE id = ? AND workspace_id = ?
                """,
                (dataset_id, workspace_id),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["body"] = json.loads(data.pop("body_json"))
        return data

    def all_datasets(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, name, created_at, body_json FROM datasets
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["body"] = json.loads(item.pop("body_json"))
            out.append(item)
        return out

    def append_export(
        self,
        path: Path,
        *,
        diagnosis: dict[str, Any],
        ingest: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        trace = json.loads(ingest["trace_json"])
        expected = None
        if ingest.get("expected_tools_json"):
            expected = json.loads(ingest["expected_tools_json"])
        case_id = str(ingest.get("case_id") or diagnosis.get("run_id"))
        case: dict[str, Any] = {
            "id": case_id,
            "traces": [trace],
        }
        if expected:
            case["expected_tools"] = expected
        elif config.get("default_expected_tools"):
            case["expected_tools"] = list(config["default_expected_tools"])
        if path.is_file():
            dataset = json.loads(path.read_text(encoding="utf-8"))
        else:
            dataset = {
                "id": str(config.get("id") or "from-live"),
                "n_runs": 1,
                "budget": config.get("budget") or {},
                "policy": config.get("policy") or {},
                "tool_schemas": config.get("tool_schemas") or {},
                "cases": [],
            }
        dataset["n_runs"] = 1
        cases = list(dataset.get("cases") or [])
        cases.append(case)
        dataset["cases"] = cases
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
        return {"path": str(path), "case_id": case_id, "cases": len(cases)}

    def put_gold_pack(
        self,
        workspace_id: str,
        pack: dict[str, Any],
        *,
        align_observed: bool = True,
    ) -> dict[str, Any]:
        agent_id = str(pack["agent_id"])
        row_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "UPDATE gold_packs SET active = 0 WHERE workspace_id = ? AND agent_id = ?",
                (workspace_id, agent_id),
            )
            self._conn.execute(
                """
                INSERT INTO gold_packs (
                  id, workspace_id, agent_id, version, created_at, active, pack_json
                ) VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    row_id,
                    workspace_id,
                    agent_id,
                    pack["version"],
                    pack["created_at"],
                    json.dumps(pack),
                ),
            )
            if align_observed:
                hashes = pack.get("source_hashes") or {}
                self._conn.execute(
                    """
                    INSERT INTO gold_observed (
                      workspace_id, agent_id, tools_hash, policy_hash, sop_hash, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, agent_id) DO UPDATE SET
                      tools_hash = excluded.tools_hash,
                      policy_hash = excluded.policy_hash,
                      sop_hash = excluded.sop_hash,
                      updated_at = excluded.updated_at
                    """,
                    (
                        workspace_id,
                        agent_id,
                        hashes.get("tools"),
                        hashes.get("policy"),
                        hashes.get("sop"),
                        _now(),
                    ),
                )
            self._conn.commit()
        return pack

    def active_gold(self, workspace_id: str, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT pack_json FROM gold_packs
                WHERE workspace_id = ? AND agent_id = ? AND active = 1
                """,
                (workspace_id, agent_id),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["pack_json"])

    def gold_stale(self, workspace_id: str, agent_id: str) -> bool:
        pack = self.active_gold(workspace_id, agent_id)
        if not pack:
            return False
        hashes = pack.get("source_hashes") or {}
        with self._lock:
            row = self._conn.execute(
                """
                SELECT tools_hash, policy_hash, sop_hash FROM gold_observed
                WHERE workspace_id = ? AND agent_id = ?
                """,
                (workspace_id, agent_id),
            ).fetchone()
        if not row:
            return False
        return (
            str(row["tools_hash"] or "") != str(hashes.get("tools") or "")
            or str(row["policy_hash"] or "") != str(hashes.get("policy") or "")
            or str(row["sop_hash"] or "") != str(hashes.get("sop") or "")
        )

    def observe_gold_sources(
        self,
        workspace_id: str,
        agent_id: str,
        hashes: dict[str, str],
    ) -> bool:
        """Record currently observed hashes. Returns True if that makes gold stale."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO gold_observed (
                  workspace_id, agent_id, tools_hash, policy_hash, sop_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, agent_id) DO UPDATE SET
                  tools_hash = excluded.tools_hash,
                  policy_hash = excluded.policy_hash,
                  sop_hash = excluded.sop_hash,
                  updated_at = excluded.updated_at
                """,
                (
                    workspace_id,
                    agent_id,
                    hashes.get("tools"),
                    hashes.get("policy"),
                    hashes.get("sop"),
                    _now(),
                ),
            )
            self._conn.commit()
        return self.gold_stale(workspace_id, agent_id)

    def list_gold_stale(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT agent_id, version, pack_json FROM gold_packs
                WHERE workspace_id = ? AND active = 1
                """,
                (workspace_id,),
            ).fetchall()
        out = []
        for row in rows:
            agent_id = str(row["agent_id"])
            stale = self.gold_stale(workspace_id, agent_id)
            out.append(
                {
                    "agent_id": agent_id,
                    "version": row["version"],
                    "stale": stale,
                }
            )
        return out

    def put_candidate(
        self,
        workspace_id: str,
        *,
        agent_id: str,
        ingest_id: str,
        case: dict[str, Any],
        change_class: str | None,
    ) -> str | None:
        cid = str(uuid.uuid4())
        with self._lock:
            existing = self._conn.execute(
                """
                SELECT id FROM gold_candidates
                WHERE workspace_id = ? AND ingest_id = ?
                """,
                (workspace_id, ingest_id),
            ).fetchone()
            if existing:
                return None
            self._conn.execute(
                """
                INSERT INTO gold_candidates (
                  id, workspace_id, agent_id, ingest_id, status, created_at,
                  case_json, change_class
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    cid,
                    workspace_id,
                    agent_id,
                    ingest_id,
                    _now(),
                    json.dumps(case),
                    change_class,
                ),
            )
            self._conn.commit()
        return cid

    def list_candidates(
        self,
        workspace_id: str,
        agent_id: str,
        *,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, agent_id, ingest_id, status, created_at, case_json, change_class
                FROM gold_candidates
                WHERE workspace_id = ? AND agent_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (workspace_id, agent_id, status),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["case"] = json.loads(item.pop("case_json"))
            out.append(item)
        return out

    def get_candidate(self, workspace_id: str, candidate_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, agent_id, ingest_id, status, created_at, case_json, change_class
                FROM gold_candidates
                WHERE id = ? AND workspace_id = ?
                """,
                (candidate_id, workspace_id),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["case"] = json.loads(item.pop("case_json"))
        return item

    def set_candidate_status(self, workspace_id: str, candidate_id: str, status: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE gold_candidates SET status = ?
                WHERE id = ? AND workspace_id = ?
                """,
                (status, candidate_id, workspace_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

