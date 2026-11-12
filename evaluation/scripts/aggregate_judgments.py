#!/usr/bin/env python3
"""Validate task-level judge outputs and aggregate strict binary scores."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_rubric_counts(cases_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in cases_root.glob("**/case.json"):
        tasks = json.loads(path.read_text(encoding="utf-8"))
        for task in tasks:
            task_id = task["metadata"]["task_id"]
            if task_id in counts:
                raise ValueError(f"Duplicate task ID in cases: {task_id}")
            counts[task_id] = len(task["rubrics"])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rubric_counts = load_rubric_counts(args.cases)
    seen: set[tuple[str, str, str]] = set()
    by_model: dict[str, list[int]] = defaultdict(list)
    records: list[dict[str, Any]] = []

    with args.judgments.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            task_id = record.get("task_id")
            inference_model = record.get("inference_model")
            judge_model = record.get("judge_model")
            key = (str(task_id), str(inference_model), str(judge_model))
            if key in seen:
                raise ValueError(f"Duplicate judgment at line {line_number}: {key}")
            seen.add(key)

            expected = rubric_counts.get(str(task_id))
            if expected is None:
                raise ValueError(f"Unknown task at line {line_number}: {task_id}")
            statuses = record.get("requirement_status")
            if (
                not isinstance(statuses, list)
                or len(statuses) != expected
                or any(value not in {"yes", "no"} for value in statuses)
            ):
                raise ValueError(
                    f"Invalid requirement status at line {line_number}"
                )
            derived = int(all(value == "yes" for value in statuses))
            if record.get("score") != derived:
                raise ValueError(
                    f"Inconsistent all-or-nothing score at line {line_number}"
                )
            by_model[str(inference_model)].append(derived)
            records.append(record)

    summary = {
        "analysis_unit": "saved model-task judgment",
        "aggregation": "task score is one only when all rubrics are yes",
        "judgment_count": len(records),
        "models": {
            model: {
                "tasks": len(scores),
                "successes": sum(scores),
                "success_rate_percent": (
                    100.0 * sum(scores) / len(scores) if scores else None
                ),
            }
            for model, scores in sorted(by_model.items())
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()

