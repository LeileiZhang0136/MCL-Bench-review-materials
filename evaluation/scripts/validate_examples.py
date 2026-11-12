#!/usr/bin/env python3
"""Validate public example cases, rubrics, IDs, and local media references."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PLACEHOLDER = "[WAITING_FOR_FILL]"


def media_path(item: dict[str, Any]) -> str | None:
    if item.get("type") == "image_url":
        value = item.get("image_url")
        if isinstance(value, dict):
            return value.get("url")
        if isinstance(value, str):
            return value
    if item.get("type") in {"video", "video_url", "input_video"}:
        for key in ("video", "video_url", "url", "path"):
            value = item.get(key)
            if isinstance(value, dict):
                value = value.get("url") or value.get("path")
            if isinstance(value, str):
                return value
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument(
        "--allow-external-video",
        action="store_true",
        help="Allow missing video paths documented in the external asset archive.",
    )
    args = parser.parse_args()

    case_files = sorted(args.examples.glob("**/case.json"))
    if len(case_files) != 60:
        raise ValueError(f"Expected 60 case files, found {len(case_files)}")

    case_ids: list[str] = []
    task_count = 0
    rubric_count = 0
    missing_media: list[str] = []
    subcategories = Counter()

    for case_file in case_files:
        case_dir = case_file.parent
        metadata_path = case_dir / "case_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        case_id = metadata["case_id"]
        case_ids.append(case_id)
        subcategories[metadata["subcategory"]] += 1

        tasks = json.loads(case_file.read_text(encoding="utf-8"))
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"Invalid task list: {case_file}")
        for expected_turn, task in enumerate(tasks, start=1):
            task_count += 1
            rubrics = task.get("rubrics")
            if not isinstance(rubrics, list) or not all(
                isinstance(value, str) and value.strip() for value in rubrics
            ):
                raise ValueError(f"Invalid rubrics: {case_file}")
            rubric_count += len(rubrics)
            metadata_task = task.get("metadata", {})
            if metadata_task.get("context_id") != case_id:
                raise ValueError(f"Case ID mismatch: {case_file}")
            if metadata_task.get("turn_index") != expected_turn:
                raise ValueError(f"Turn order mismatch: {case_file}")
            if metadata_task.get("task_id") != f"{case_id}_T{expected_turn}":
                raise ValueError(f"Task ID mismatch: {case_file}")

            assistant_index = 0
            for message in task.get("messages", []):
                if message.get("role") == "assistant":
                    assistant_index += 1
                    content = message.get("content", [])
                    texts = [
                        item.get("text")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    if texts != [PLACEHOLDER]:
                        raise ValueError(
                            f"Non-placeholder assistant output: {case_file}"
                        )
                for item in message.get("content", []):
                    reference = media_path(item)
                    if not reference or reference.startswith(
                        ("http://", "https://", "data:")
                    ):
                        continue
                    local = case_dir / reference
                    if local.exists():
                        continue
                    suffix = Path(reference).suffix.lower()
                    if args.allow_external_video and suffix in {
                        ".mp4",
                        ".mov",
                        ".avi",
                    }:
                        continue
                    missing_media.append(f"{case_id}:{reference}")
            if assistant_index != expected_turn - 1:
                raise ValueError(f"History placeholder mismatch: {case_file}")

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Duplicate public case IDs")
    if len(subcategories) != 20 or set(subcategories.values()) != {3}:
        raise ValueError(f"Unexpected subcategory coverage: {subcategories}")
    if missing_media:
        raise ValueError(
            "Missing media references:\n" + "\n".join(missing_media[:20])
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "cases": len(case_files),
                "tasks": task_count,
                "serialized_rubric_entries": rubric_count,
                "subcategories": len(subcategories),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
