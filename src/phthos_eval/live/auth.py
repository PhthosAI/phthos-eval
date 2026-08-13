from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

COOKIE_NAME = "phthos_eval_session"
LOCAL_WORKSPACE = "local"
_PBKDF2_ROUNDS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, hx = stored.split("$", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS)
    return hmac.compare_digest(dk.hex(), hx)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    raw = "pk_" + secrets.token_urlsafe(24)
    return raw, hash_token(raw), raw[:10]


def new_session_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def parse_bearer(authorization: str | None, x_key: str | None) -> str | None:
    if x_key and x_key.strip():
        return x_key.strip()
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def parse_cookie(header: str | None, name: str = COOKIE_NAME) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if key == name:
            return value
    return None


def session_cookie(token: str, *, secure: bool = False, max_age: int = 604800) -> str:
    bits = [
        f"{COOKIE_NAME}={token}",
        "HttpOnly",
        "Path=/",
        "SameSite=Lax",
        f"Max-Age={max_age}",
    ]
    if secure:
        bits.append("Secure")
    return "; ".join(bits)


def clear_session_cookie(*, secure: bool = False) -> str:
    return session_cookie("", secure=secure, max_age=0)


def valid_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1] and " " not in email


def identity_from_headers(store: Any, *, authorization: str | None, x_key: str | None, cookie: str | None) -> dict[str, str] | None:
    raw_key = parse_bearer(authorization, x_key)
    if raw_key:
        row = store.workspace_for_api_key(raw_key)
        if row:
            return {"workspace_id": row["workspace_id"], "user_id": row.get("user_id") or "", "via": "key"}
    raw_sess = parse_cookie(cookie)
    if raw_sess:
        row = store.workspace_for_session(raw_sess)
        if row:
            return {"workspace_id": row["workspace_id"], "user_id": row["user_id"], "via": "session"}
    return None
