from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def maybe_judge(
    diagnosis: dict[str, Any],
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Optional LLM judge. No key → skipped. Never blocks deterministic diagnosis."""
    key = api_key or os.environ.get("PHTHOS_EVAL_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"skipped": True, "reason": "no_key", "score": None, "error": None}

    base = (
        base_url
        or os.environ.get("PHTHOS_EVAL_JUDGE_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = model or os.environ.get("PHTHOS_EVAL_JUDGE_MODEL") or "gpt-4o-mini"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "Reply with a single number from 0 to 1. No other text.",
            },
            {
                "role": "user",
                "content": (
                    "Rate whether this agent eval looks healthy (1) or broken (0). "
                    f"change_class={diagnosis.get('change_class')} "
                    f"failures={len(diagnosis.get('failures') or [])}"
                ),
            },
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"].strip()
        score = float(text.split()[0])
        return {"skipped": False, "reason": None, "score": score, "error": None}
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError, IndexError) as exc:
        return {"skipped": False, "reason": None, "score": None, "error": str(exc)}
