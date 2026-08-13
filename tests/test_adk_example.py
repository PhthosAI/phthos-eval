from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_google_adk_examples_are_wrap_only() -> None:
    adk = ROOT / "agent_integration_examples" / "google_adk"
    req = (adk / "requirements.txt").read_text(encoding="utf-8")
    assert "google-adk" in req and "ddgs" in req and "phthos-eval" in req
    lib = (adk / "lib" / "agent.py").read_text(encoding="utf-8")
    live = (adk / "live" / "agent.py").read_text(encoding="utf-8")
    for src in (lib, live):
        assert "sink.wrap(" in src
        assert "class EvalSink" not in src
        assert "tool_schemas" not in src
        assert "requirements.txt" in src
        assert src.count("\n") < 80

