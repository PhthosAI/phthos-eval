from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phthos_eval.compare import compare_diagnoses
from phthos_eval.finetune_export import labeled_trajectories
from phthos_eval.live.config import LiveSettings, clamp_rate
from phthos_eval.live.demo import run_demo
from phthos_eval.live.server import serve
from phthos_eval.runner import run_dataset, write_diagnosis
from phthos_eval.schema import validate_diagnosis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phthos-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Score a fixture dataset; write diagnosis JSON")
    run_p.add_argument("--dataset", "-d", required=True, type=Path)
    run_p.add_argument("--out", "-o", type=Path, default=Path("diagnosis.json"))
    run_p.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 1 if the diagnosis has any failures (CI gate).",
    )

    check_p = sub.add_parser("check", help="Validate a diagnosis JSON file")
    check_p.add_argument("file", type=Path)

    live_p = sub.add_parser("live", help="Self-host sampled live engine (does not block agents)")
    live_p.add_argument("--host", default=None)
    live_p.add_argument("--port", type=int, default=None)
    live_p.add_argument("--config", "-c", type=Path, default=None)
    live_p.add_argument("--data-dir", type=Path, default=None)
    live_p.add_argument("--sample-rate", type=float, default=None)
    live_p.add_argument(
        "--live-judge",
        action="store_true",
        help="Opt in to BYOK LLM judge on sampled traces (off by default).",
    )
    live_p.add_argument(
        "--hosted",
        action="store_true",
        help="Require sign-up/API keys and isolate tenants (same engine; we operate this in cloud).",
    )

    demo_p = sub.add_parser("live-demo", help="POST example traces at a running live engine")
    demo_p.add_argument("--url", default="http://127.0.0.1:8765")
    demo_p.add_argument("--api-key", default=None, help="Bearer key when the engine is in hosted mode")

    cmp_p = sub.add_parser(
        "compare",
        help="Same-case before/after scores. Eval does not apply the change.",
    )
    cmp_p.add_argument("--before", required=True, type=Path, help="Diagnosis JSON before the change")
    cmp_p.add_argument("--after", required=True, type=Path, help="Diagnosis JSON after the change")
    cmp_p.add_argument("--out", "-o", type=Path, default=None)

    ft_p = sub.add_parser(
        "export-finetune",
        help="Labeled trajectories for *their* fine-tune stack. This product does not train.",
    )
    ft_p.add_argument("--dataset", "-d", required=True, type=Path)
    ft_p.add_argument("--diagnosis", required=True, type=Path)
    ft_p.add_argument("--out", "-o", type=Path, default=Path("finetune.json"))

    args = parser.parse_args(argv)
    if args.cmd == "run":
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        diagnosis = run_dataset(dataset)
        write_diagnosis(diagnosis, args.out)
        print(args.out)
        if args.fail_on_findings and diagnosis.get("failures"):
            return 1
        return 0
    if args.cmd == "check":
        errors = validate_diagnosis(json.loads(args.file.read_text(encoding="utf-8")))
        if errors:
            print("invalid:", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
            return 1
        print("ok")
        return 0
    if args.cmd == "live":
        settings = LiveSettings.from_env()
        if args.host is not None:
            settings.host = args.host
        if args.port is not None:
            settings.port = args.port
        if args.config is not None:
            settings.config_path = args.config
        if args.data_dir is not None:
            settings.data_dir = args.data_dir
        if args.sample_rate is not None:
            settings.sample_rate = clamp_rate(args.sample_rate)
        if args.live_judge:
            settings.live_judge = True
        if args.hosted:
            settings.hosted = True
        serve(settings)
        return 0
    if args.cmd == "compare":
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        doc = compare_diagnoses(before, after)
        text = json.dumps(doc, indent=2) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(args.out)
        else:
            print(text, end="")
        return 0
    if args.cmd == "export-finetune":
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        diagnosis = json.loads(args.diagnosis.read_text(encoding="utf-8"))
        doc = labeled_trajectories(dataset, diagnosis)
        args.out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(args.out)
        return 0
    return run_demo(args.url, api_key=args.api_key)


if __name__ == "__main__":
    raise SystemExit(main())
