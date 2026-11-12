#!/usr/bin/env python3
"""Single entry point for the public, offline reproduction workflows."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], capture_output: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=capture_output,
        text=capture_output,
    )
    return result.stdout if capture_output else ""


def assert_same_files(
    generated_dir: Path,
    reference_dir: Path,
    filenames: list[str],
) -> None:
    for filename in filenames:
        generated = generated_dir / filename
        reference = reference_dir / filename
        if not generated.is_file():
            raise FileNotFoundError(f"Missing reproduced file: {generated}")
        if not reference.is_file():
            raise FileNotFoundError(f"Missing reference file: {reference}")
        if generated.read_bytes() != reference.read_bytes():
            raise ValueError(
                f"Reproduced file differs from committed reference: {filename}"
            )


def reproduce_released_examples(output_root: Path) -> None:
    print("[1/5] Reaggregating the released 60-example results", flush=True)
    run(
        [
            sys.executable,
            "evaluation/scripts/reproduce_released_examples.py",
            "--output-dir",
            str(output_root / "released_examples"),
        ]
    )


def reproduce_uncertainty(output_root: Path) -> None:
    print("[2/5] Recomputing full-task and historical-media Wilson intervals", flush=True)
    output_dir = output_root / "uncertainty"
    run(
        [
            sys.executable,
            "evidence/uncertainty/reproduce_wilson_ci.py",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert_same_files(
        output_dir,
        ROOT / "evidence/uncertainty",
        [
            "paper_results_wilson_ci.json",
            "paper_main_wilson_ci.csv",
            "paper_media_wilson_ci.csv",
            "paper_results_wilson_ci.md",
        ],
    )


def reproduce_open_weight(output_root: Path) -> None:
    print("[3/5] Recomputing the Kimi K2.6/K3 supplementary results", flush=True)
    output_dir = output_root / "open_weight_models"
    run(
        [
            sys.executable,
            "evidence/open_weight_models/reproduce_open_model_results.py",
            "--scores",
            "evidence/open_weight_models/open_model_task_scores.csv",
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
    )
    assert_same_files(
        output_dir,
        ROOT / "evidence/open_weight_models",
        [
            "open_model_summary.json",
            "open_model_summary.csv",
            "paired_comparison.json",
            "paired_comparison.csv",
        ],
    )
    print(
        "Kimi supplement: 344 cases, 1,080 paired tasks; "
        "reference outputs match.",
        flush=True,
    )


def reproduce_reconciliation(output_root: Path) -> None:
    print("[4/5] Reproducing full-task evaluation reconciliation", flush=True)
    output_dir = output_root / "evaluation_reconciliation"
    run([sys.executable, "evidence/evaluation_reconciliation/reproduce.py",
         "--output-dir", str(output_dir)])
    assert_same_files(output_dir, ROOT / "evidence/evaluation_reconciliation",
                      ["summary.json", "SUMMARY.md"])
    run([sys.executable,
         "evidence/evaluation_reconciliation/reproduce_rubric_diagnostics.py",
         "--output-dir", str(output_dir)])
    assert_same_files(output_dir, ROOT / "evidence/evaluation_reconciliation",
                      ["rubric_satisfaction.csv", "success_by_rubric_count.csv",
                       "RUBRIC_DIAGNOSTICS.md"])
    run([sys.executable,
         "evidence/evaluation_reconciliation/reproduce_single_failure.py",
         "--output-dir", str(output_dir)])
    assert_same_files(output_dir, ROOT / "evidence/evaluation_reconciliation",
                      ["single_failure_records.csv", "single_failure_examples.jsonl",
                       "SINGLE_FAILURE_REVIEW.md"])


def validate_repository(
    video_archive: Path | None,
    write_validation: bool,
) -> None:
    print("[5/5] Running repository-wide integrity checks", flush=True)
    command = [sys.executable, "tools/validate_repository.py"]
    if video_archive is not None:
        command.extend(["--video-archive", str(video_archive.resolve())])
    if not write_validation:
        command.append("--check-only")
    run(command)


def api_dry_run() -> None:
    case_json = (
        ROOT
        / "examples/synthetic/03_Evidence/04_Layouts_and_Maps"
        / "MCL-0143_synthetic/case.json"
    )
    asset_dir = case_json.parent / "assets"
    run(
        [
            sys.executable,
            "evaluation/runtime/run_backend.py",
            str(case_json),
            str(asset_dir),
            "--dry-run",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce the public MCL-Bench artifact results. "
            "The default offline workflow never calls a model API."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="offline",
        choices=[
            "offline",
            "released-examples",
            "uncertainty",
            "open-weight",
            "reconciliation",
            "validate",
            "api-dry-run",
        ],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reproduced",
    )
    parser.add_argument("--video-archive", type=Path)
    parser.add_argument(
        "--write-validation",
        action="store_true",
        help=(
            "With the validate command, rewrite REPOSITORY_VALIDATION.json "
            "and SHA256SUMS. Omit this flag for a read-only check."
        ),
    )
    args = parser.parse_args()
    output_root = args.output_dir.resolve()

    if args.command in {"offline", "released-examples"}:
        reproduce_released_examples(output_root)
    if args.command in {"offline", "uncertainty"}:
        reproduce_uncertainty(output_root)
    if args.command in {"offline", "open-weight"}:
        reproduce_open_weight(output_root)
    if args.command in {"offline", "reconciliation"}:
        reproduce_reconciliation(output_root)
    if args.command in {"offline", "validate"}:
        validate_repository(
            args.video_archive,
            write_validation=(
                args.command == "validate" and args.write_validation
            ),
        )
    if args.command == "api-dry-run":
        api_dry_run()

    print(
        "PASS: requested reproduction workflow completed successfully.",
        flush=True,
    )


if __name__ == "__main__":
    main()
