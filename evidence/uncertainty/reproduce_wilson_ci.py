#!/usr/bin/env python3
"""Reproduce task-level Wilson intervals from paper-reported counts.

Main counts are observed full-task counts in evaluation_reconciliation,
superseding earlier counts inferred from rounded first-turn rates. Media
counts are retained as separately identified historical figure inputs.
The Gemini-2.5-pro row preserves stored scores; see the reconciliation note
for the 78/1,080 status-normalized sensitivity result.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


Z_95 = 1.959963984540054

MAIN_ROWS = [
    ("Claude-Opus-4.6 Thinking", 135, 1080, 12.50),
    ("Claude-Opus-4.6", 114, 1080, 10.56),
    ("Claude-Sonnet-4.6 Thinking", 141, 1080, 13.06),
    ("Claude-Sonnet-4.6", 140, 1080, 12.96),
    ("Gemini-3.1-Pro-Preview (High)", 104, 1080, 9.63),
    ("GPT-5.2", 116, 1080, 10.74),
    ("Doubao-Seed-2.0-pro", 82, 1080, 7.59),
    ("Gemini-2.5-pro", 79, 1080, 7.31),
]

MEDIA_ROWS = [
    ("Single-video", 17, 38, 46, 304, 15.1),
    ("Multi-video", 12, 37, 27, 296, 9.1),
    ("Image+video", 12, 34, 21, 272, 7.8),
]


def wilson(successes: int, total: int) -> tuple[float, float, float]:
    proportion = successes / total
    denominator = 1.0 + Z_95**2 / total
    center = (proportion + Z_95**2 / (2.0 * total)) / denominator
    half_width = (
        Z_95
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + Z_95**2 / (4.0 * total**2)
        )
        / denominator
    )
    return (
        100.0 * proportion,
        100.0 * (center - half_width),
        100.0 * (center + half_width),
    )


def validate_reported_rate(successes: int, total: int, reported: float) -> None:
    exact = 100.0 * successes / total
    # The analysis freezes the integer counts and the one-decimal values
    # printed in the paper. Allow a sub-0.1-point display difference
    # because the paper values may have been averaged before rounding.
    if abs(exact - reported) >= 0.1:
        raise ValueError(
            f"{successes}/{total} gives {exact:.4f}%, not reported {reported:.1f}%"
        )


def main_records() -> list[dict[str, object]]:
    records = []
    for model, successes, total, reported in MAIN_ROWS:
        validate_reported_rate(successes, total, reported)
        exact, lower, upper = wilson(successes, total)
        records.append(
            {
                "model": model,
                "successes": successes,
                "task_evaluations": total,
                "reported_rate_percent": reported,
                "exact_rate_percent": exact,
                "wilson_95_ci_lower": lower,
                "wilson_95_ci_upper": upper,
            }
        )
    return records


def media_records() -> list[dict[str, object]]:
    records = []
    for (
        configuration,
        cases,
        tasks_per_model,
        successes,
        total,
        reported,
    ) in MEDIA_ROWS:
        validate_reported_rate(successes, total, reported)
        if tasks_per_model * 8 != total:
            raise ValueError(f"Unexpected denominator for {configuration}")
        exact, lower, upper = wilson(successes, total)
        records.append(
            {
                "media_configuration": configuration,
                "cases": cases,
                "tasks_per_model": tasks_per_model,
                "models": 8,
                "successes": successes,
                "model_task_evaluations": total,
                "reported_rate_percent": reported,
                "exact_rate_percent": exact,
                "wilson_95_ci_lower": lower,
                "wilson_95_ci_upper": upper,
            }
        )
    return records


def write_csv(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def markdown(main: list[dict[str, object]], media: list[dict[str, object]]) -> str:
    lines = [
        "# Full-task and historical-media Wilson intervals",
        "",
        "## Analysis contract",
        "",
        "- Main authority: released full-task score rows in evaluation_reconciliation; media: historical figure counts.",
        "- Interval: two-sided 95% Wilson score interval.",
        "- Unit: saved model-task evaluation.",
        "- Main-table inferred counts have been superseded by observed full-task counts; see evaluation_reconciliation.",
        "- These intervals do not estimate run-to-run generation variability or "
        "case-cluster uncertainty.",
        "",
        "## Main model results",
        "",
        "| Model | Successes/tasks | Full-task rate | 95% Wilson CI |",
        "|---|---:|---:|---:|",
    ]
    for row in main:
        lines.append(
            f"| {row['model']} | {row['successes']}/{row['task_evaluations']} | "
            f"{row['exact_rate_percent']:.2f}% | "
            f"[{row['wilson_95_ci_lower']:.2f}, "
            f"{row['wilson_95_ci_upper']:.2f}] |"
        )
    lines.extend(
        [
            "",
            "## Media-configuration results",
            "",
            "| Configuration | Cases | Tasks/model | Successes/evaluations | "
            "Paper rate | 95% Wilson CI |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in media:
        lines.append(
            f"| {row['media_configuration']} | {row['cases']} | "
            f"{row['tasks_per_model']} | {row['successes']}/"
            f"{row['model_task_evaluations']} | "
            f"{row['reported_rate_percent']:.1f}% | "
            f"[{row['wilson_95_ci_lower']:.2f}, "
            f"{row['wilson_95_ci_upper']:.2f}] |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The media groups differ in case composition and difficulty. Their "
            "intervals support a descriptive comparison only; they do not identify "
            "a causal effect of media configuration. The model intervals quantify "
            "task-level uncertainty and are not pairwise significance tests.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "paper_results_wilson_ci.json"
    main_csv = output_dir / "paper_main_wilson_ci.csv"
    media_csv = output_dir / "paper_media_wilson_ci.csv"
    md_path = output_dir / "paper_results_wilson_ci.md"

    main_rows = main_records()
    media_rows = media_records()
    payload = {
        "analysis_contract": {
            "authority": (
                "observed full-task score rows; historical media-configuration counts"
            ),
            "interval": "two-sided 95% Wilson score interval",
            "unit": "model-task evaluation",
            "local_result_directory_used": False,
            "limitations": [
                "does not estimate run-to-run generation variability",
                "does not account for clustering within benchmark cases",
                "media comparison is observational and composition-confounded",
            ],
        },
        "main_models": main_rows,
        "media_configurations": media_rows,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(main_csv, main_rows)
    write_csv(media_csv, media_rows)
    md_path.write_text(markdown(main_rows, media_rows), encoding="utf-8")
    print(md_path)


if __name__ == "__main__":
    main()
