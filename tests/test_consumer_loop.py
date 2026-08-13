from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

from phthos_eval.compare import compare_diagnoses
from phthos_eval.runner import run_dataset

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "examples" / "consumer"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_consumer_loop_improves_without_eval_writing_agent(tmp_path: Path) -> None:
    shutil.copy(CONSUMER / "agent.json", tmp_path / "agent.json")
    shutil.copy(CONSUMER / "cases.json", tmp_path / "cases.json")
    record = _load("consumer_record", CONSUMER / "record.py")
    apply = _load("consumer_apply", CONSUMER / "apply.py")

    cases = json.loads((tmp_path / "cases.json").read_text(encoding="utf-8"))
    agent = json.loads((tmp_path / "agent.json").read_text(encoding="utf-8"))
    before = run_dataset(record.record_dataset(cases, agent), judge=False)
    assert before["change_class"] == "tool"
    assert before["scores"]["task_success"] < 1.0

    updated = apply.apply_diagnosis(agent, before)
    (tmp_path / "agent.json").write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    assert updated["rename_tools"]["lookup"] == "search"

    after = run_dataset(record.record_dataset(cases, updated), judge=False)
    cmp = compare_diagnoses(before, after)
    assert cmp["task_success_delta"] > 0
    assert after["change_class"] == "none"
    assert json.loads((tmp_path / "agent.json").read_text(encoding="utf-8"))["rename_tools"]["lookup"] == "search"
    src = CONSUMER / "agent.json"
    committed = json.loads(src.read_text(encoding="utf-8"))
    assert committed.get("rename_tools") == {}
