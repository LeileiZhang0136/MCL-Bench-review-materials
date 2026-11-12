#!/usr/bin/env python3
"""Reproduce the anonymized Kimi supplementary-evaluation statistics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path


BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 23_049
Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    proportion = successes / total
    denominator = 1 + Z_95**2 / total
    center = (proportion + Z_95**2 / (2 * total)) / denominator
    half_width = (
        Z_95
        * math.sqrt(
            proportion * (1 - proportion) / total
            + Z_95**2 / (4 * total**2)
        )
        / denominator
    )
    return center - half_width, center + half_width


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def exact_mcnemar_p_value(k2_only: int, k3_only: int) -> float:
    discordant = k2_only + k3_only
    smaller = min(k2_only, k3_only)
    lower_tail = sum(
        math.comb(discordant, index) for index in range(smaller + 1)
    ) / (2**discordant)
    return min(1.0, 2 * lower_tail)


def load_rows(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for row in rows:
        row["turn_index"] = int(row["turn_index"])
        row["kimi_k2_6_score"] = int(row["kimi_k2_6_score"])
        row["kimi_k3_score"] = int(row["kimi_k3_score"])
    return rows


def aggregate_group(rows: list[dict]) -> dict:
    k2_successes = sum(row["kimi_k2_6_score"] for row in rows)
    k3_successes = sum(row["kimi_k3_score"] for row in rows)
    total = len(rows)
    return {
        "case_count": len({row["case_id"] for row in rows}),
        "task_count": total,
        "kimi_k2_6": {
            "successes": k2_successes,
            "rate": k2_successes / total,
        },
        "kimi_k3": {
            "successes": k3_successes,
            "rate": k3_successes / total,
        },
        "difference_k3_minus_k2_6": (k3_successes - k2_successes) / total,
    }


def compute(rows: list[dict]) -> dict:
    if len(rows) != 1_080:
        raise ValueError(f"Expected 1,080 task rows, found {len(rows)}")
    if len({row["task_id"] for row in rows}) != len(rows):
        raise ValueError("Task IDs are not unique")
    if len({row["case_id"] for row in rows}) != 344:
        raise ValueError("Expected 344 unique case IDs")
    if any(
        row[model] not in (0, 1)
        for row in rows
        for model in ("kimi_k2_6_score", "kimi_k3_score")
    ):
        raise ValueError("All model scores must be binary")

    model_results = {}
    for label, column in (
        ("Kimi K2.6", "kimi_k2_6_score"),
        ("Kimi K3", "kimi_k3_score"),
    ):
        successes = sum(row[column] for row in rows)
        lower, upper = wilson_interval(successes, len(rows))
        model_results[label] = {
            "successes": successes,
            "failures": len(rows) - successes,
            "tasks": len(rows),
            "cases": 344,
            "success_rate": successes / len(rows),
            "wilson_95": [lower, upper],
        }

    both_pass = sum(
        row["kimi_k2_6_score"] == 1 and row["kimi_k3_score"] == 1
        for row in rows
    )
    k2_only = sum(
        row["kimi_k2_6_score"] == 1 and row["kimi_k3_score"] == 0
        for row in rows
    )
    k3_only = sum(
        row["kimi_k2_6_score"] == 0 and row["kimi_k3_score"] == 1
        for row in rows
    )
    both_fail = len(rows) - both_pass - k2_only - k3_only

    rows_by_case: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        rows_by_case[row["case_id"]].append(row)
    case_ids = sorted(rows_by_case)
    random_generator = random.Random(BOOTSTRAP_SEED)
    bootstrap_differences = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled_cases = [
            random_generator.choice(case_ids) for _ in range(len(case_ids))
        ]
        k2_successes = 0
        k3_successes = 0
        task_count = 0
        for case_id in sampled_cases:
            for row in rows_by_case[case_id]:
                k2_successes += row["kimi_k2_6_score"]
                k3_successes += row["kimi_k3_score"]
                task_count += 1
        bootstrap_differences.append((k3_successes - k2_successes) / task_count)

    source_groups = {}
    for source_track in ("synthetic", "expert"):
        source_groups[source_track] = aggregate_group(
            [row for row in rows if row["source_track"] == source_track]
        )

    turn_groups = {}
    for turn_index in sorted({row["turn_index"] for row in rows}):
        turn_groups[str(turn_index)] = aggregate_group(
            [row for row in rows if row["turn_index"] == turn_index]
        )

    return {
        "benchmark": {
            "cases": 344,
            "tasks": 1_080,
            "score_unit": "task",
            "score_rule": "all task-level rubrics must be satisfied",
        },
        "model_results": model_results,
        "paired_comparison": {
            "both_pass": both_pass,
            "kimi_k2_6_only": k2_only,
            "kimi_k3_only": k3_only,
            "both_fail": both_fail,
            "difference_k3_minus_k2_6": (
                model_results["Kimi K3"]["success_rate"]
                - model_results["Kimi K2.6"]["success_rate"]
            ),
            "case_cluster_bootstrap_95": [
                percentile(bootstrap_differences, 0.025),
                percentile(bootstrap_differences, 0.975),
            ],
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "mcnemar_exact_two_sided_p": exact_mcnemar_p_value(k2_only, k3_only),
        },
        "source_track_results": source_groups,
        "turn_results": turn_groups,
        "interpretation": (
            "The paired gain supports benchmark sensitivity to capability differences "
            "and argues against a uniform floor effect. It is not a causal estimate of "
            "the effect of general intelligence."
        ),
    }


def write_outputs(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "open_model_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    with (output_dir / "open_model_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "model",
                "cases",
                "tasks",
                "successes",
                "failures",
                "success_rate",
                "wilson_95_lower",
                "wilson_95_upper",
            ]
        )
        for model, values in result["model_results"].items():
            writer.writerow(
                [
                    model,
                    values["cases"],
                    values["tasks"],
                    values["successes"],
                    values["failures"],
                    values["success_rate"],
                    values["wilson_95"][0],
                    values["wilson_95"][1],
                ]
            )

    paired = result["paired_comparison"]
    (output_dir / "paired_comparison.json").write_text(
        json.dumps(
            {
                "paired_comparison": paired,
                "source_track_results": result["source_track_results"],
                "turn_results": result["turn_results"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (output_dir / "paired_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["section", "metric", "value"])
        for key, value in paired.items():
            if isinstance(value, list):
                writer.writerow(["overall", f"{key}_lower", value[0]])
                writer.writerow(["overall", f"{key}_upper", value[1]])
            else:
                writer.writerow(["overall", key, value])
        for source, values in result["source_track_results"].items():
            writer.writerow([source, "case_count", values["case_count"]])
            writer.writerow([source, "task_count", values["task_count"]])
            writer.writerow(
                [source, "kimi_k2_6_rate", values["kimi_k2_6"]["rate"]]
            )
            writer.writerow([source, "kimi_k3_rate", values["kimi_k3"]["rate"]])
            writer.writerow(
                [
                    source,
                    "difference_k3_minus_k2_6",
                    values["difference_k3_minus_k2_6"],
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scores",
        type=Path,
        default=Path(__file__).with_name("open_model_task_scores.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    result = compute(load_rows(args.scores))
    if not args.no_write:
        write_outputs(result, args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
