#!/usr/bin/env python3
"""Materialize ordered MCL-Bench task inputs with same-model history."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


PLACEHOLDER = "[WAITING_FOR_FILL]"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def replace_history(
    messages: list[dict[str, Any]],
    prior_task_ids: list[str],
    history: dict[str, str],
    allow_placeholders: bool,
) -> list[dict[str, Any]]:
    materialized = copy.deepcopy(messages)
    assistant_messages = [
        message for message in materialized if message.get("role") == "assistant"
    ]
    if len(assistant_messages) != len(prior_task_ids):
        raise ValueError(
            "Assistant-placeholder count does not match preceding task count"
        )

    for message, task_id in zip(assistant_messages, prior_task_ids):
        output = history.get(task_id)
        if output is None:
            if allow_placeholders:
                continue
            raise ValueError(f"Missing same-model history for {task_id}")
        content = message.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise ValueError(f"Unexpected assistant content for {task_id}")
        item = content[0]
        if item.get("type") != "text" or item.get("text") != PLACEHOLDER:
            raise ValueError(f"Non-placeholder assistant message for {task_id}")
        item["text"] = output
    return materialized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-placeholders", action="store_true")
    args = parser.parse_args()

    tasks = load_json(args.case)
    history = load_json(args.history)
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("case.json must contain a non-empty task list")
    if not isinstance(history, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in history.items()
    ):
        raise ValueError("History must be a JSON object mapping task IDs to text")

    task_ids: list[str] = []
    records = []
    for expected_turn, task in enumerate(tasks, start=1):
        metadata = task.get("metadata", {})
        task_id = metadata.get("task_id")
        case_id = metadata.get("context_id")
        turn_index = metadata.get("turn_index")
        if turn_index != expected_turn:
            raise ValueError(f"Unexpected turn index for {task_id}")
        if not isinstance(task_id, str) or not isinstance(case_id, str):
            raise ValueError("Missing public task or case ID")
        messages = replace_history(
            task.get("messages", []),
            task_ids,
            history,
            args.allow_placeholders,
        )
        records.append(
            {
                "case_id": case_id,
                "task_id": task_id,
                "turn_index": turn_index,
                "messages": messages,
                "rubrics": task.get("rubrics", []),
            }
        )
        task_ids.append(task_id)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

