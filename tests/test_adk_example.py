from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_google_adk_lib_and_live_scripts_exist() -> None:
    adk = ROOT / "agent_integration_examples" / "google_adk"
    assert (adk / "lib" / "agent.py").is_file()
    assert (adk / "live" / "agent.py").is_file()
