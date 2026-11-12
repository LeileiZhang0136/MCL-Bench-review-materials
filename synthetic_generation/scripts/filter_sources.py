from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from PIL import Image


DATASETS = ("slideVQA", "mmlongbench-doc")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically filter SlideVQA and MMLongBench-Doc samples."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-dimension", type=int, default=640)
    parser.add_argument("--formal-min-images", type=int, default=4)
    parser.add_argument("--blueprint-min-images", type=int, default=3)
    parser.add_argument("--min-readable-ratio", type=float, default=0.9)
    return parser.parse_args()


def natural_key(value: str) -> list[object]:
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    ]


def sample_dirs(dataset_root: Path) -> list[Path]:
    result = []
    for directory in sorted(
        (path for path in dataset_root.rglob("*") if path.is_dir()),
        key=lambda path: natural_key(str(path.relative_to(dataset_root))),
    ):
        if any(
            child.is_file() and child.suffix.lower() in IMAGE_SUFFIXES
            for child in directory.iterdir()
        ):
            result.append(directory)
    return result


def inspect_sample(
    source_root: Path,
    dataset_name: str,
    directory: Path,
    min_dimension: int,
    formal_min_images: int,
    blueprint_min_images: int,
    min_readable_ratio: float,
) -> dict[str, object]:
    paths = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=lambda path: natural_key(path.name),
    )
    readable: list[tuple[Path, int, int, int]] = []
    unreadable: list[str] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
            readable.append((path, width, height, path.stat().st_size))
        except Exception:
            unreadable.append(path.name)

    readable_ratio = len(readable) / len(paths) if paths else 0.0
    min_width = min((item[1] for item in readable), default=0)
    min_height = min((item[2] for item in readable), default=0)
    all_large_enough = min_width >= min_dimension and min_height >= min_dimension
    reasons = []
    if len(readable) < formal_min_images:
        reasons.append("too_few_readable_images_for_formal")
    if readable_ratio < min_readable_ratio:
        reasons.append("low_readable_ratio")
    if not all_large_enough:
        reasons.append("low_resolution_images")

    if (
        len(readable) >= formal_min_images
        and readable_ratio >= min_readable_ratio
        and all_large_enough
    ):
        level = "formal"
        reasons = ["meets_formal_thresholds"]
    elif len(readable) >= blueprint_min_images:
        level = "blueprint"
    else:
        level = "rejected"

    relative_dir = directory.relative_to(source_root)
    dataset = "slideVQA" if dataset_name == "slideVQA" else "mmlongbench-doc"
    return {
        "dataset": dataset,
        "sample_id": str(directory.relative_to(source_root / dataset_name)),
        "sample_dir": str(relative_dir),
        "image_count": len(paths),
        "image_paths": [
            str(path.relative_to(source_root)) for path, _, _, _ in readable
        ],
        "valid_image_count": len(readable),
        "unreadable_images": unreadable,
        "readable_ratio": round(readable_ratio, 4),
        "min_width": min_width,
        "min_height": min_height,
        "avg_file_size_kb": round(
            sum(item[3] for item in readable) / max(len(readable), 1) / 1024, 2
        ),
        "text_support_status": "embedded_text_likely",
        "data_quality_score": (
            5 if level == "formal" and min(min_width, min_height) >= 768 else 3
        ),
        "caseability_score": 5 if len(readable) >= 6 else 3,
        "candidate_level": level,
        "reasons": reasons,
    }


def main() -> int:
    args = parse_args()
    source_root = args.source_root.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: dict[str, list[dict[str, object]]] = {
        "formal": [],
        "blueprint": [],
        "rejected": [],
    }
    for dataset_name in DATASETS:
        dataset_root = source_root / dataset_name
        if not dataset_root.is_dir():
            raise FileNotFoundError(dataset_root)
        for directory in sample_dirs(dataset_root):
            record = inspect_sample(
                source_root,
                dataset_name,
                directory,
                args.min_dimension,
                args.formal_min_images,
                args.blueprint_min_images,
                args.min_readable_ratio,
            )
            records[str(record["candidate_level"])].append(record)

    filenames = {
        "formal": "formal_candidates.jsonl",
        "blueprint": "blueprint_candidates.jsonl",
        "rejected": "rejected_candidates.jsonl",
    }
    for level, items in records.items():
        path = args.output_dir / filenames[level]
        with path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    counts = Counter(
        (item["dataset"], level)
        for level, items in records.items()
        for item in items
    )
    summary = {
        "thresholds": {
            "min_dimension": args.min_dimension,
            "formal_min_images": args.formal_min_images,
            "blueprint_min_images": args.blueprint_min_images,
            "min_readable_ratio": args.min_readable_ratio,
        },
        "counts": {
            dataset: {
                level: counts[(dataset, level)]
                for level in ("formal", "blueprint", "rejected")
            }
            for dataset in ("slideVQA", "mmlongbench-doc")
        },
    }
    (args.output_dir / "filter_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

