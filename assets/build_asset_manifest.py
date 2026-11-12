#!/usr/bin/env python3
"""Inventory case-local assets and optionally build an external video archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import tarfile
from pathlib import Path


VIDEO_SUFFIXES = {".mp4", ".mov", ".avi"}
FIELDS = [
    "repository_path",
    "case_id",
    "suffix",
    "bytes",
    "sha256",
    "bundled_in_git_tree",
    "hosting_route",
    "redistribution_status",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def case_id_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("MCL-") and "_" in part:
            return part.split("_", 1)[0]
    raise ValueError(f"Cannot find public case ID in {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-examples", type=Path, required=True)
    parser.add_argument("--repository-examples", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--video-archive", type=Path)
    args = parser.parse_args()

    rows = []
    videos: list[tuple[Path, Path]] = []
    for released_copy in sorted(args.repository_examples.glob("**/assets/*")):
        if not released_copy.is_file() or released_copy.name == ".DS_Store":
            continue
        relative = released_copy.relative_to(args.repository_examples)
        repository_path = Path("examples") / relative
        rows.append(
            {
                "repository_path": repository_path.as_posix(),
                "case_id": case_id_from_path(relative),
                "suffix": released_copy.suffix.lower(),
                "bytes": released_copy.stat().st_size,
                "sha256": sha256(released_copy),
                "bundled_in_git_tree": "yes",
                "hosting_route": "git_tree",
                "redistribution_status": "pending_case_level_review",
            }
        )

    for source in sorted(args.source_examples.glob("**/assets/*")):
        if (
            not source.is_file()
            or source.name == ".DS_Store"
            or source.suffix.lower() not in VIDEO_SUFFIXES
        ):
            continue
        relative = source.relative_to(args.source_examples)
        repository_path = Path("examples") / relative
        videos.append((source, repository_path))
        rows.append(
            {
                "repository_path": repository_path.as_posix(),
                "case_id": case_id_from_path(relative),
                "suffix": source.suffix.lower(),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
                "bundled_in_git_tree": "no",
                "hosting_route": "external_release_attachment",
                "redistribution_status": "pending_case_level_review",
            }
        )

    rows.sort(key=lambda row: row["repository_path"])
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    if args.video_archive:
        args.video_archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.video_archive, mode="w") as archive:
            for source, repository_path in videos:
                archive.add(source, arcname=repository_path.as_posix())
        checksum_path = args.video_archive.with_suffix(
            args.video_archive.suffix + ".sha256"
        )
        checksum_path.write_text(
            f"{sha256(args.video_archive)}  {args.video_archive.name}\n",
            encoding="utf-8",
        )

    print(
        f"Assets: {len(rows)}; videos: {len(videos)}; "
        f"bundled: {sum(row['bundled_in_git_tree'] == 'yes' for row in rows)}"
    )


if __name__ == "__main__":
    main()
