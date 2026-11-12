#!/usr/bin/env python3
"""Validate and reaggregate the released 60-example evaluation records."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_MODELS = [
    "Claude-Opus-4.6 Thinking",
    "Claude-Opus-4.6",
    "Claude-Sonnet-4.6 Thinking",
    "Claude-Sonnet-4.6",
    "Gemini-3.1-Pro-Preview (High)",
    "GPT-5.2",
    "Doubao-Seed-2.0-pro",
    "Gemini-2.5-pro",
]
VALID_STATUSES = {
    "ok",
    "corrected",
    "inference_error",
    "judge_error",
}
ERROR_STATUSES = {"inference_error", "judge_error"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON at {path}:{line_number}: {error}"
                ) from error
            if not isinstance(row, dict):
                raise ValueError(
                    f"Expected object at {path}:{line_number}"
                )
            rows.append(row)
    return rows


def read_json_list(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(
        isinstance(row, dict) for row in value
    ):
        raise ValueError(f"Expected a JSON array of objects: {path}")
    return value


def load_public_tasks(cases_root: Path) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    case_ids: set[str] = set()
    for path in sorted(cases_root.rglob("case.json")):
        case_rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(case_rows, list) or not case_rows:
            raise ValueError(f"Invalid case list: {path}")
        for task in case_rows:
            metadata = task.get("metadata", {})
            case_id = str(metadata.get("context_id", ""))
            task_id = str(metadata.get("task_id", ""))
            turn = metadata.get("turn_index")
            if not task_id or task_id in tasks:
                raise ValueError(f"Missing or duplicate public task ID: {task_id}")
            if not case_id or not isinstance(turn, int):
                raise ValueError(f"Invalid metadata for {task_id}")
            if task_id != f"{case_id}_T{turn}":
                raise ValueError(f"Task ID/turn mismatch: {task_id}")
            rubrics = task.get("rubrics")
            if not isinstance(rubrics, list) or not rubrics:
                raise ValueError(f"Missing rubrics for {task_id}")
            tasks[task_id] = {
                "case_id": case_id,
                "turn_index": turn,
                "serialized_rubric_entry_count": len(rubrics),
            }
            case_ids.add(case_id)
    if len(case_ids) != 60:
        raise ValueError(
            f"Expected 60 cases, found {len(case_ids)} "
            f"with {len(tasks)} tasks"
        )
    return tasks


def record_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("task_id")), str(row.get("inference_model"))


def validate_predictions(
    rows: list[dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = record_key(row)
        if key in indexed:
            raise ValueError(f"Duplicate prediction: {key}")
        task = tasks.get(key[0])
        if task is None:
            raise ValueError(f"Unknown prediction task: {key[0]}")
        if row.get("case_id") != task["case_id"]:
            raise ValueError(f"Prediction case mismatch: {key}")
        if row.get("turn_index") != task["turn_index"]:
            raise ValueError(f"Prediction turn mismatch: {key}")
        if key[1] not in EXPECTED_MODELS:
            raise ValueError(f"Unexpected prediction model: {key[1]}")
        output = row.get("model_output")
        status = row.get("record_status")
        if not isinstance(output, str):
            raise ValueError(f"Non-string model output: {key}")
        if status not in {"ok", "inference_error"}:
            raise ValueError(f"Invalid prediction status: {key}")
        if (status == "ok") != bool(output.strip()):
            raise ValueError(f"Prediction status/output mismatch: {key}")
        indexed[key] = row
    return indexed


def validate_judgments(
    rows: list[dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    predictions: dict[tuple[str, str], dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = record_key(row)
        if key in indexed:
            raise ValueError(f"Duplicate judgment: {key}")
        task = tasks.get(key[0])
        if task is None or key not in predictions:
            raise ValueError(f"Unpaired or unknown judgment: {key}")
        if row.get("case_id") != task["case_id"]:
            raise ValueError(f"Judgment case mismatch: {key}")
        if row.get("judge_model") != "GPT-5.2":
            raise ValueError(f"Unexpected judge model: {key}")
        if key[1] not in EXPECTED_MODELS:
            raise ValueError(f"Unexpected inference model: {key[1]}")
        status = row.get("record_status")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid judgment status: {key}")
        if (
            predictions[key]["record_status"] == "inference_error"
            and status != "inference_error"
        ):
            raise ValueError(f"Inference error not preserved: {key}")
        if (
            predictions[key]["record_status"] == "ok"
            and status == "inference_error"
        ):
            raise ValueError(f"Spurious inference error: {key}")

        statuses = row.get("requirement_status")
        score = row.get("score")
        if not isinstance(statuses, list) or score not in {0, 1}:
            raise ValueError(f"Invalid judgment payload: {key}")
        stored_rubric_count = row.get("serialized_rubric_entry_count")
        public_rubric_count = task["serialized_rubric_entry_count"]
        # MCL-0317_T1 gained one explicit negative constraint in the public
        # example after the stored run. Every stored model score for this task
        # is already zero, so this addition cannot change the released binary
        # aggregate. Preserve the original judgment metadata instead of
        # rewriting a historical record.
        known_non_score_changing_extension = (
            key[0] == "MCL-0317_T1"
            and stored_rubric_count == 4
            and public_rubric_count == 5
            and row.get("score") == 0
        )
        if (
            stored_rubric_count != public_rubric_count
            and not known_non_score_changing_extension
        ):
            raise ValueError(f"Serialized rubric-count mismatch: {key}")

        if status in {"ok", "corrected"}:
            rationale = row.get("grading_rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"Missing grading rationale: {key}")
            if not statuses or any(value not in {"yes", "no"} for value in statuses):
                raise ValueError(f"Invalid logical rubric decisions: {key}")
            if row.get("logical_rubric_count_at_judging") != len(statuses):
                raise ValueError(f"Logical rubric-count mismatch: {key}")
            if score != int(all(value == "yes" for value in statuses)):
                raise ValueError(f"All-or-nothing score mismatch: {key}")
        else:
            if statuses or score != 0:
                raise ValueError(f"Error record must have empty status and score 0: {key}")
            if row.get("logical_rubric_count_at_judging") is not None:
                raise ValueError(f"Error record has a logical rubric count: {key}")
        indexed[key] = row
    return indexed


def validate_status_logs(
    error_rows: list[dict[str, Any]],
    correction_rows: list[dict[str, Any]],
    judgments: dict[tuple[str, str], dict[str, Any]],
) -> tuple[int, int]:
    expected_errors = {
        key: row
        for key, row in judgments.items()
        if row["record_status"] in ERROR_STATUSES
    }
    observed_errors: dict[tuple[str, str], dict[str, Any]] = {}
    for row in error_rows:
        key = record_key(row)
        if key in observed_errors:
            raise ValueError(f"Duplicate evaluation-error record: {key}")
        judgment = expected_errors.get(key)
        if judgment is None:
            raise ValueError(f"Unexpected evaluation-error record: {key}")
        if row.get("case_id") != judgment["case_id"]:
            raise ValueError(f"Evaluation-error case mismatch: {key}")
        if row.get("record_status") != judgment["record_status"]:
            raise ValueError(f"Evaluation-error status mismatch: {key}")
        policy = row.get("aggregation_policy")
        if not isinstance(policy, str) or not policy.strip():
            raise ValueError(f"Missing error aggregation policy: {key}")
        observed_errors[key] = row
    if set(observed_errors) != set(expected_errors):
        missing = sorted(set(expected_errors) - set(observed_errors))
        extra = sorted(set(observed_errors) - set(expected_errors))
        raise ValueError(
            "Evaluation-error log does not match judgment statuses; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )

    case_text_corrections = [
        row
        for row in correction_rows
        if row.get("correction_type") == "case_text"
    ]
    judgment_corrections = [
        row
        for row in correction_rows
        if row.get("correction_type") in {None, "judgment_normalization"}
    ]
    unknown_types = sorted(
        {
            str(row.get("correction_type"))
            for row in correction_rows
            if row.get("correction_type")
            not in {None, "case_text", "judgment_normalization"}
        }
    )
    if unknown_types:
        raise ValueError(f"Unknown correction types: {unknown_types}")
    for row in case_text_corrections:
        required = {
            "case_id",
            "task_id",
            "field",
            "stored_text",
            "corrected_text",
            "reason",
            "score_impact",
        }
        missing = sorted(required - set(row))
        if missing:
            raise ValueError(f"Incomplete case-text correction: {missing}")
        if row["task_id"] not in {key[0] for key in judgments}:
            raise ValueError(
                f"Unknown task in case-text correction: {row['task_id']}"
            )

    expected_corrections = {
        key: row
        for key, row in judgments.items()
        if row["record_status"] == "corrected"
    }
    observed_corrections: dict[tuple[str, str], dict[str, Any]] = {}
    for row in judgment_corrections:
        key = record_key(row)
        if key in observed_corrections:
            raise ValueError(f"Duplicate correction record: {key}")
        judgment = expected_corrections.get(key)
        if judgment is None:
            raise ValueError(f"Unexpected correction record: {key}")
        checks = {
            "case_id": judgment["case_id"],
            "stored_requirement_status": judgment.get(
                "stored_requirement_status"
            ),
            "normalized_requirement_status": judgment["requirement_status"],
            "stored_score": judgment.get("stored_score"),
            "normalized_score": judgment["score"],
        }
        for field, expected in checks.items():
            if row.get(field) != expected:
                raise ValueError(f"Correction {field} mismatch: {key}")
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Missing correction reason: {key}")
        observed_corrections[key] = row
    if set(observed_corrections) != set(expected_corrections):
        missing = sorted(set(expected_corrections) - set(observed_corrections))
        extra = sorted(set(observed_corrections) - set(expected_corrections))
        raise ValueError(
            "Correction log does not match corrected judgments; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )
    return len(observed_errors), len(correction_rows)


def validate_full_coverage(keys: set[tuple[str, str]], tasks: set[str]) -> None:
    expected = {
        (task_id, model) for task_id in tasks for model in EXPECTED_MODELS
    }
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing or extra:
        raise ValueError(
            f"Incomplete task-model coverage; missing={missing[:5]}, "
            f"extra={extra[:5]}"
        )
    if len(keys) != len(expected):
        raise ValueError(
            f"Expected {len(expected):,} task-model records, found {len(keys):,}"
        )


def make_summary(
    rows: list[dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    case_count = len({task["case_id"] for task in tasks.values()})
    task_count = len(tasks)
    serialized_rubric_entries = sum(
        task["serialized_rubric_entry_count"] for task in tasks.values()
    )
    expected_records = task_count * len(EXPECTED_MODELS)
    by_model: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_model[str(row["inference_model"])].append(int(row["score"]))
    models = []
    for model in EXPECTED_MODELS:
        scores = by_model[model]
        if len(scores) != task_count:
            raise ValueError(
                f"{model} has {len(scores)} tasks, expected {task_count}"
            )
        successes = sum(scores)
        models.append(
            {
                "model": model,
                "cases": case_count,
                "tasks": len(scores),
                "successes": successes,
                "failures": len(scores) - successes,
                "success_rate_percent": 100.0 * successes / len(scores),
            }
        )
    return {
        "scope": {
            "case_count": case_count,
            "task_count": task_count,
            "model_count": len(EXPECTED_MODELS),
            "prediction_count": expected_records,
            "judgment_count": expected_records,
            "judge_model": "GPT-5.2",
            "full_344_case_leaderboard_reproduced": False,
        },
        "score_rule": (
            "A task receives one only when every logical rubric decision is "
            "yes; inference or judge API errors are counted as end-to-end "
            "task failures."
        ),
        "rubric_serialization_note": (
            f"The released case JSON contains {serialized_rubric_entries:,} "
            "serialized rubric entries. "
            "Some multiline logical rubrics occupy more than one serialized "
            "entry; requirement_status follows the logical rubric units used "
            "by the judge."
        ),
        "record_status_counts": dict(
            sorted(Counter(row["record_status"] for row in rows).items())
        ),
        "models": models,
    }


def write_outputs(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fields = [
        "model",
        "cases",
        "tasks",
        "successes",
        "failures",
        "success_rate_percent",
    ]
    with (output_dir / "summary_by_model.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary["models"])


def main() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    released_root = repository_root / "evaluation/released_examples"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=repository_root / "examples",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=released_root / "predictions.jsonl",
    )
    parser.add_argument(
        "--judgments",
        type=Path,
        default=released_root / "judgments_gpt5.2.jsonl",
    )
    parser.add_argument(
        "--reference-summary",
        type=Path,
        default=released_root / "summary.json",
    )
    parser.add_argument(
        "--evaluation-errors",
        type=Path,
        default=released_root / "evaluation_errors.jsonl",
    )
    parser.add_argument(
        "--correction-log",
        type=Path,
        default=released_root / "correction_log.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "reproduced/released_examples",
    )
    parser.add_argument("--skip-reference-check", action="store_true")
    args = parser.parse_args()

    tasks = load_public_tasks(args.cases.resolve())
    predictions = validate_predictions(
        read_jsonl(args.predictions.resolve()), tasks
    )
    judgments = validate_judgments(
        read_jsonl(args.judgments.resolve()), tasks, predictions
    )
    validate_full_coverage(set(predictions), set(tasks))
    validate_full_coverage(set(judgments), set(tasks))
    if set(predictions) != set(judgments):
        raise ValueError("Prediction and judgment coverage differs")
    error_count, correction_count = validate_status_logs(
        read_jsonl(args.evaluation_errors.resolve()),
        read_json_list(args.correction_log.resolve()),
        judgments,
    )

    summary = make_summary(list(judgments.values()), tasks)
    if not args.skip_reference_check:
        reference = json.loads(
            args.reference_summary.read_text(encoding="utf-8")
        )
        if summary != reference:
            raise ValueError("Recomputed summary differs from reference summary")
    write_outputs(summary, args.output_dir.resolve())
    print(
        json.dumps(
            {
                "status": "PASS",
                "cases": len({task["case_id"] for task in tasks.values()}),
                "tasks": len(tasks),
                "models": len(EXPECTED_MODELS),
                "predictions": len(predictions),
                "judgments": len(judgments),
                "evaluation_errors": error_count,
                "corrections": correction_count,
                "reference_summary_match": not args.skip_reference_check,
                "output_dir": str(args.output_dir.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
