"""Record → eval → apply (this repo) → record → eval → compare.

Eval never writes agent.json. Re-eval proves the consumer's change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from apply import apply_diagnosis
from record import record_dataset

from phthos_eval.compare import compare_diagnoses
from phthos_eval.runner import run_dataset, write_diagnosis

HERE = Path(__file__).resolve().parent


def run_loop(root: Path) -> dict:
    cases = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    agent_path = root / "agent.json"
    agent = json.loads(agent_path.read_text(encoding="utf-8"))

    before = run_dataset(record_dataset(cases, agent), judge=False)
    write_diagnosis(before, root / "diagnosis.before.json")

    updated = apply_diagnosis(agent, before)
    agent_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")

    after = run_dataset(record_dataset(cases, updated), judge=False)
    write_diagnosis(after, root / "diagnosis.after.json")

    return compare_diagnoses(before, after)


def main() -> int:
    doc = run_loop(HERE)
    dest = HERE / "compare.json"
    dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(dest)
    delta = doc.get("task_success_delta")
    print(f"task_success_delta={delta}")
    print("eval did not apply the fix; apply.py wrote agent.json")
    if delta is None or float(delta) <= 0:
        print("change did not improve task_success", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
