"""Turn this consumer's agent.json + cases.json into a dataset for phthos-eval.

Eval never reads agent.json. This script is the agent owner recording traces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def record_dataset(cases: dict[str, Any], agent: dict[str, Any]) -> dict[str, Any]:
    rename = dict(agent.get("rename_tools") or {})
    rename_args = dict(agent.get("rename_args") or {})
    out_cases: list[dict[str, Any]] = []
    for case in cases.get("cases") or []:
        traces = []
        for trace in case.get("traces") or []:
            spans = []
            for span in trace.get("spans") or []:
                item = dict(span)
                if item.get("type") == "tool" and item.get("name") in rename:
                    new_name = rename[item["name"]]
                    item["name"] = new_name
                    mapping = rename_args.get(new_name) or {}
                    args = item.get("args")
                    if isinstance(args, dict) and mapping:
                        item["args"] = {mapping.get(k, k): v for k, v in args.items()}
                spans.append(item)
            traces.append({**trace, "spans": spans})
        out_cases.append({**case, "traces": traces})
    return {**cases, "cases": out_cases}


def main() -> None:
    agent = json.loads((HERE / "agent.json").read_text(encoding="utf-8"))
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    dataset = record_dataset(cases, agent)
    dest = HERE / "dataset.json"
    dest.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
