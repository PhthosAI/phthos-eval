from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_adk_lib_and_live_scripts_exist() -> None:
    assert (ROOT / "examples" / "adk" / "lib.py").is_file()
    assert (ROOT / "examples" / "adk" / "live.py").is_file()
