from __future__ import annotations

import json
from pathlib import Path

from phthos_eval.cli import main
from phthos_eval.finetune_export import FINETUNE_FORMAT, labeled_trajectories


def test_labeled_trajectories_include_evidence_not_train() -> None:
    dataset = {
        "id": "ds",
        "cases": [
            {
                "id": "c1",
                "traces": [{"spans": [{"id": "s1", "type": "tool", "name": "lookup"}]}],
            }
        ],
    }
    diagnosis = {
        "schema_version": "0.2.0",
        "run_id": "r1",
        "dataset_id": "ds",
        "change_class": "tool",
        "cases": [
            {
                "case_id": "c1",
                "passed": False,
                "failures": [{"type": "wrong_tool", "evidence": {"span_id": "s1"}}],
            }
        ],
    }
    doc = labeled_trajectories(dataset, diagnosis)
    assert doc["format"] == FINETUNE_FORMAT
    assert "does not train" in doc["note"]
    assert doc["rows"][0]["passed"] is False
    assert doc["rows"][0]["traces"][0]["spans"][0]["name"] == "lookup"
    assert doc["rows"][0]["change_class"] == "tool"


def test_cli_export_finetune(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.json"
    diagnosis = tmp_path / "diagnosis.json"
    out = tmp_path / "ft.json"
    dataset.write_text(
        json.dumps({"id": "ds", "cases": [{"id": "c", "traces": []}]}),
        encoding="utf-8",
    )
    diagnosis.write_text(
        json.dumps(
            {
                "run_id": "r",
                "schema_version": "0.2.0",
                "change_class": "none",
                "cases": [{"case_id": "c", "passed": True, "failures": []}],
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "export-finetune",
            "-d",
            str(dataset),
            "--diagnosis",
            str(diagnosis),
            "-o",
            str(out),
        ]
    ) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["format"] == FINETUNE_FORMAT
    assert doc["rows"][0]["passed"] is True
