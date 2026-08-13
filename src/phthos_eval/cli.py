from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phthos_eval.runner import run_dataset, write_diagnosis
from phthos_eval.schema import validate_diagnosis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phthos-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Score a fixture dataset; write diagnosis JSON")
    run_p.add_argument("--dataset", "-d", required=True, type=Path)
    run_p.add_argument("--out", "-o", type=Path, default=Path("diagnosis.json"))

    check_p = sub.add_parser("check", help="Validate a diagnosis JSON file")
    check_p.add_argument("file", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "run":
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        diagnosis = run_dataset(dataset)
        write_diagnosis(diagnosis, args.out)
        print(args.out)
        return 0
    errors = validate_diagnosis(json.loads(args.file.read_text(encoding="utf-8")))
    if errors:
        print("invalid:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
