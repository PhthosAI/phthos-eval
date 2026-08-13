from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
                  error TEXT
                );
                CREATE TABLE IF NOT EXISTS diagnoses (
                  id TEXT PRIMARY KEY,
                  ingest_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  passed INTEGER NOT NULL,
                  change_class TEXT,
                  cost REAL,
                  policy_hits INTEGER,
                  diagnosis_json TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

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
    ) -> None:
        status = "queued" if sampled else "skipped"
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO ingests (
                  id, created_at, agent_id, case_id, sampled, status,
                  trace_json, expected_tools_json, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    ingest_id,
                    _now(),
                    agent_id,
                    case_id,
                    int(sampled),
                    status,
                    json.dumps(trace),
                    json.dumps(expected_tools) if expected_tools is not None else None,
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
            self._conn.execute(
                """
                INSERT OR REPLACE INTO diagnoses (
                  id, ingest_id, created_at, passed, change_class, cost,
                  policy_hits, diagnosis_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            self._conn.execute(
                "UPDATE ingests SET status = 'scored', error = NULL WHERE id = ?",
                (ingest_id,),
            )
            self._conn.commit()

    def get_diagnosis(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT diagnosis_json FROM diagnoses WHERE id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["diagnosis_json"])

    def get_ingest(self, ingest_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM ingests WHERE id = ?",
                (ingest_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def counts(self) -> dict[str, int]:
        with self._lock:
            received = self._conn.execute("SELECT COUNT(*) FROM ingests").fetchone()[0]
            sampled = self._conn.execute(
                "SELECT COUNT(*) FROM ingests WHERE sampled = 1"
            ).fetchone()[0]
            scored = self._conn.execute(
                "SELECT COUNT(*) FROM diagnoses"
            ).fetchone()[0]
        return {
            "received": int(received),
            "sampled": int(sampled),
            "scored": int(scored),
        }

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, created_at, passed, change_class, cost, policy_hits
                FROM diagnoses
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                  COUNT(*) AS n,
                  AVG(passed) AS pass_rate,
                  SUM(cost) AS cost,
                  SUM(policy_hits) AS policy_hits
                FROM diagnoses
                """
            ).fetchone()
        n = int(row["n"] or 0)
        return {
            "pass_rate": float(row["pass_rate"]) if n and row["pass_rate"] is not None else None,
            "cost": float(row["cost"]) if row["cost"] is not None else 0.0,
            "policy_hits": int(row["policy_hits"] or 0),
        }

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
