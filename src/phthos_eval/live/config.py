from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SAMPLE_RATE = 0.05
DEFAULT_PORT = 8765
DEFAULT_RETENTION_DAYS = 30
DEFAULT_ALERT_MIN_PASS_RATE = 0.8


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_sample(key: str, rate: float) -> bool:
    """Stable hash sample. rate=0 never; rate>=1 always. Default live rate is 5%."""
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    return bucket < rate


def clamp_rate(rate: float) -> float:
    return max(0.0, min(1.0, float(rate)))


@dataclass
class LiveSettings:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    sample_rate: float = DEFAULT_SAMPLE_RATE
    data_dir: Path = Path("phthos-eval-data")
    config_path: Path | None = None
    live_judge: bool = False
    hosted: bool = False
    retention_days: int = DEFAULT_RETENTION_DAYS
    alert_min_pass_rate: float = DEFAULT_ALERT_MIN_PASS_RATE
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    public_base_url: str | None = None
    ops_secret: str | None = None
    sso_secret: str | None = None
    hosted_judge_api_key: str | None = None
    hosted_judge_base_url: str | None = None
    hosted_judge_model: str | None = None

    @classmethod
    def from_env(cls) -> LiveSettings:
        rate_raw = os.environ.get("PHTHOS_EVAL_SAMPLE_RATE")
        port_raw = os.environ.get("PHTHOS_EVAL_LIVE_PORT")
        data = os.environ.get("PHTHOS_EVAL_DATA_DIR")
        config = os.environ.get("PHTHOS_EVAL_LIVE_CONFIG")
        host = os.environ.get("PHTHOS_EVAL_LIVE_HOST") or "127.0.0.1"
        retention = os.environ.get("PHTHOS_EVAL_RETENTION_DAYS")
        alert = os.environ.get("PHTHOS_EVAL_ALERT_MIN_PASS_RATE")
        smtp_port = os.environ.get("PHTHOS_EVAL_SMTP_PORT")
        return cls(
            host=host,
            port=int(port_raw) if port_raw else DEFAULT_PORT,
            sample_rate=clamp_rate(float(rate_raw)) if rate_raw else DEFAULT_SAMPLE_RATE,
            data_dir=Path(data) if data else Path("phthos-eval-data"),
            config_path=Path(config) if config else None,
            live_judge=_truthy(os.environ.get("PHTHOS_EVAL_LIVE_JUDGE")),
            hosted=_truthy(os.environ.get("PHTHOS_EVAL_HOSTED")),
            retention_days=int(retention) if retention else DEFAULT_RETENTION_DAYS,
            alert_min_pass_rate=float(alert) if alert else DEFAULT_ALERT_MIN_PASS_RATE,
            smtp_host=os.environ.get("PHTHOS_EVAL_SMTP_HOST") or None,
            smtp_port=int(smtp_port) if smtp_port else 587,
            smtp_user=os.environ.get("PHTHOS_EVAL_SMTP_USER") or None,
            smtp_password=os.environ.get("PHTHOS_EVAL_SMTP_PASSWORD") or None,
            smtp_from=os.environ.get("PHTHOS_EVAL_SMTP_FROM") or None,
            public_base_url=os.environ.get("PHTHOS_EVAL_PUBLIC_URL") or None,
            ops_secret=os.environ.get("PHTHOS_EVAL_OPS_SECRET") or None,
            sso_secret=os.environ.get("PHTHOS_EVAL_SSO_SECRET") or None,
            hosted_judge_api_key=os.environ.get("PHTHOS_EVAL_HOSTED_JUDGE_API_KEY") or None,
            hosted_judge_base_url=os.environ.get("PHTHOS_EVAL_HOSTED_JUDGE_BASE_URL") or None,
            hosted_judge_model=os.environ.get("PHTHOS_EVAL_HOSTED_JUDGE_MODEL") or None,
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "live.sqlite"

    @property
    def export_path(self) -> Path:
        return self.data_dir / "from-live.json"

    @property
    def cookie_secure(self) -> bool:
        url = (self.public_base_url or "").lower()
        return url.startswith("https://")

    def dataset_config(self) -> dict[str, Any]:
        if self.config_path and self.config_path.is_file():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"id": "live"}
