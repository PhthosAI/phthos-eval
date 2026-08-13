from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOURS = ROOT / "examples" / "adk" / "hours.py"
HAS_ADK = importlib.util.find_spec("google.adk") is not None


@pytest.mark.skipif(not HAS_ADK, reason="google-adk extra not installed")
def test_adk_hours_offline_lib() -> None:
    proc = subprocess.run(
        [sys.executable, str(HOURS)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "hours-ok" in proc.stdout
    assert "hours-lookup" in proc.stdout
    assert "task_success=" in proc.stdout
