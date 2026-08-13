"""Read a diagnosis and change *this* agent's config.

phthos-eval does not call this. Branch on change_class; write agent.json only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def apply_diagnosis(agent: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    change = diagnosis.get("change_class")
    out = dict(agent)
    out["last_change_class"] = change
    if change == "tool":
        rename = dict(out.get("rename_tools") or {})
        rename["lookup"] = "search"
        out["rename_tools"] = rename
        args = dict(out.get("rename_args") or {})
        args["search"] = {"q": "query"}
        out["rename_args"] = args
    elif change == "policy":
        out["policy_note"] = "consumer would edit deny-list / allow-list outside eval"
    elif change == "prompt":
        out["prompt_note"] = "consumer would edit the prompt outside eval"
    elif change == "model":
        out["model_note"] = "consumer would switch model or budget outside eval"
    elif change == "finetune_data":
        out["finetune_note"] = (
            "consumer would train on export-finetune output; eval does not train"
        )
    return out


def main() -> None:
    diagnosis_path = HERE / "diagnosis.json"
    agent_path = HERE / "agent.json"
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    agent = json.loads(agent_path.read_text(encoding="utf-8"))
    updated = apply_diagnosis(agent, diagnosis)
    agent_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    print(agent_path)


if __name__ == "__main__":
    main()
