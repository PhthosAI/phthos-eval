from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_google_adk_lib_and_live_scripts_exist() -> None:
    adk = ROOT / "agent_integration_examples" / "google_adk"
    lib = (adk / "lib" / "agent.py").read_text(encoding="utf-8")
    live = (adk / "live" / "agent.py").read_text(encoding="utf-8")
    assert "sink.wrap(" in lib and "class EvalSink" not in lib
    assert "sink.wrap(" in live and "class EvalSink" not in live
