from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any


def fire_score_drop(
    *,
    webhook_url: str | None,
    alert_email: str | None,
    smtp_host: str | None,
    smtp_port: int,
    smtp_user: str | None,
    smtp_password: str | None,
    smtp_from: str | None,
    payload: dict[str, Any],
) -> list[str]:
    """Best-effort webhook and/or email. Failures are returned, never raised."""
    sent: list[str] = []
    if webhook_url:
        err = _webhook(webhook_url, payload)
        if err:
            sent.append(f"webhook_error:{err}")
        else:
            sent.append("webhook")
    if alert_email and smtp_host:
        err = _email(
            to=alert_email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            smtp_from=smtp_from or smtp_user or "phthos-eval@localhost",
            payload=payload,
        )
        if err:
            sent.append(f"email_error:{err}")
        else:
            sent.append("email")
    return sent


def _webhook(url: str, payload: dict[str, Any]) -> str | None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "phthos-eval"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return str(exc)


def _email(
    *,
    to: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str | None,
    smtp_password: str | None,
    smtp_from: str,
    payload: dict[str, Any],
) -> str | None:
    msg = EmailMessage()
    msg["Subject"] = "[phthos-eval] pass rate dropped"
    msg["From"] = smtp_from
    msg["To"] = to
    prev = payload.get("previous_pass_rate")
    new = payload.get("pass_rate")
    msg.set_content(
        "Live eval pass rate dropped below the alert threshold.\n\n"
        f"previous: {prev}\n"
        f"current: {new}\n"
        f"threshold: {payload.get('threshold')}\n"
        f"scored runs: {payload.get('scored')}\n\n"
        "Eval does not apply a fix. Export the diagnosis and change the agent yourself.\n"
    )
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            if smtp_port != 25:
                smtp.starttls()
            if smtp_user and smtp_password:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
        return None
    except (OSError, smtplib.SMTPException) as exc:
        return str(exc)
