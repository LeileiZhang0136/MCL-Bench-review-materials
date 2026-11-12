#!/usr/bin/env python3
"""Run publication-oriented integrity and anonymity checks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from PIL import Image


TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi"}
MAX_GIT_FILE_BYTES = 95 * 1024 * 1024
LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:"
    r"/Users/(?![<{\[])[A-Za-z0-9._-]+/|"
    r"/home/(?![<{\[])[A-Za-z0-9._-]+/|"
    r"[A-Z]:\\\\Users\\\\(?![<{\[])[A-Za-z0-9._-]+\\\\"
    r")"
)
SECRET_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"hf_[A-Za-z0-9]{20,}"
    r")"
)
LEGACY_CONTRIBUTOR_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"(?:zll|hzg|lml|lwt|psp[0-9]*|slsq|zyp|zjh|gnb|qcy|tml|slr)"
    r"(?![A-Za-z0-9])"
)
UPSTREAM_SAMPLE_MANIFEST = Path("synthetic_generation/manifests/source_filter_v1")
DISALLOWED_EXAMPLE_KEYS = {
    "api_key",
    "context_category",
    "judge_rationale",
    "judge_score",
    "model_output",
    "original_contributor",
    "response_id",
    "sub_category",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def walk_json_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from walk_json_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk_json_keys(nested)


def media_reference(item: dict[str, Any]) -> str | None:
    if item.get("type") == "image_url":
        value = item.get("image_url")
        if isinstance(value, dict):
            value = value.get("url")
        return value if isinstance(value, str) else None
    if item.get("type") in {"video", "video_url", "input_video"}:
        for key in ("video", "video_url", "url", "path"):
            value = item.get(key)
            if isinstance(value, dict):
                value = value.get("url") or value.get("path")
            if isinstance(value, str):
                return value
    return None


def case_media_references(tasks: list[dict[str, Any]]) -> list[str]:
    references: list[str] = []
    for task in tasks:
        for message in task.get("messages", []):
            for item in message.get("content", []):
                reference = media_reference(item)
                if reference:
                    references.append(reference)
    return references


def repository_files(root: Path) -> list[Path]:
    excluded = {
        root / "REPOSITORY_VALIDATION.json",
        root / "SHA256SUMS",
    }
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(root).parts
        and ".venv" not in path.relative_to(root).parts
        and "__pycache__" not in path.relative_to(root).parts
        and "reproduced" not in path.relative_to(root).parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
        and path not in excluded
    )


def validate_examples(root: Path, errors: list[str]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(root / "evaluation/scripts/validate_examples.py"),
        "--examples",
        str(root / "examples"),
        "--allow-external-video",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        errors.append(f"example validator failed: {result.stderr.strip()}")
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        errors.append("example validator did not emit valid JSON")
        return {}


def validate_json_keys(root: Path, errors: list[str]) -> None:
    for path in sorted((root / "examples").rglob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            errors.append(f"invalid JSON {path.relative_to(root)}: {error}")
            continue
        bad = sorted(
            {
                key
                for key in walk_json_keys(value)
                if key.lower() in DISALLOWED_EXAMPLE_KEYS
            }
        )
        if bad:
            errors.append(
                f"disallowed keys in {path.relative_to(root)}: {', '.join(bad)}"
            )


def validate_example_metadata(
    root: Path,
    example_summary: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    manifest_path = root / "examples/manifest_public.csv"
    summary_path = root / "examples/examples_summary.json"
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    try:
        saved = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"invalid examples summary: {error}")
        return {}

    source_counts = Counter(row["source_track"] for row in rows)
    category_counts = Counter(row["category"] for row in rows)
    subcategory_counts = Counter(row["subcategory"] for row in rows)
    if [int(row["example_order"]) for row in rows] != list(
        range(1, len(rows) + 1)
    ):
        errors.append("manifest example_order is not continuous from 1")

    examples_root = root / "examples"
    case_files = {
        path.relative_to(examples_root).as_posix(): path
        for path in examples_root.glob("**/case.json")
    }
    manifest_paths = [row["relative_case_path"] for row in rows]
    if len(manifest_paths) != len(set(manifest_paths)):
        errors.append("manifest contains duplicate relative_case_path values")
    if set(manifest_paths) != set(case_files):
        missing = sorted(set(case_files) - set(manifest_paths))
        extra = sorted(set(manifest_paths) - set(case_files))
        errors.append(
            "manifest case paths do not match released case files; "
            f"unlisted={missing[:5]}, missing={extra[:5]}"
        )

    expected_index_groups: dict[
        tuple[str, str, str], dict[str, dict[str, str]]
    ] = {}
    for row in rows:
        case_path = case_files.get(row["relative_case_path"])
        if case_path is None:
            continue
        try:
            metadata = json.loads(
                (case_path.parent / "case_metadata.json").read_text(
                    encoding="utf-8"
                )
            )
            tasks = json.loads(case_path.read_text(encoding="utf-8"))
        except Exception as error:
            errors.append(
                f"cannot inspect manifest case {row['relative_case_path']}: "
                f"{error}"
            )
            continue
        references = case_media_references(tasks)
        unique_references = set(references)
        actual = {
            "case_id": str(metadata.get("case_id", "")),
            "source_track": str(metadata.get("source_track", "")),
            "category": str(metadata.get("category", "")),
            "subcategory": str(metadata.get("subcategory", "")),
            "expert_contributor_code": str(
                metadata.get("expert_contributor_code") or ""
            ),
            "task_count": str(len(tasks)),
            "media_reference_count": str(len(references)),
            "media_file_count": str(len(unique_references)),
        }
        if metadata.get("task_count") != len(tasks):
            errors.append(
                f"case_metadata task_count mismatch for {row['case_id']}"
            )
        for field, value in actual.items():
            if row.get(field, "") != value:
                errors.append(
                    f"manifest {field} mismatch for {row['case_id']}: "
                    f"declared={row.get(field)!r}, actual={value!r}"
                )
        if case_path.parent.name != (
            f"{row['case_id']}_{row['source_track']}"
            + (
                f"_{row['expert_contributor_code']}"
                if row["expert_contributor_code"]
                else ""
            )
        ):
            errors.append(f"case directory name mismatch for {row['case_id']}")
        if row.get("release_status") != "ready":
            errors.append(f"case is not release-ready: {row['case_id']}")
        group = (
            row["source_track"],
            row["category"],
            row["subcategory"],
        )
        expected_index_groups.setdefault(group, {})[row["case_id"]] = {
            "case_id": row["case_id"],
            "directory": case_path.parent.name,
            "task_count": row["task_count"],
            "source_track": row["source_track"],
            "release_status": row["release_status"],
        }

    observed_index_groups: set[tuple[str, str, str]] = set()
    for index_path in sorted(examples_root.glob("**/index.json")):
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as error:
            errors.append(
                f"invalid example index {index_path.relative_to(root)}: {error}"
            )
            continue
        group = (
            str(index.get("source_track", "")),
            str(index.get("category", "")),
            str(index.get("subcategory", "")),
        )
        if group in observed_index_groups:
            errors.append(f"duplicate example index group: {group}")
            continue
        observed_index_groups.add(group)
        entries = index.get("cases")
        if not isinstance(entries, list):
            errors.append(
                f"invalid cases list in {index_path.relative_to(root)}"
            )
            continue
        if index.get("count") != len(entries):
            errors.append(
                f"index count mismatch in {index_path.relative_to(root)}"
            )
        observed_entries = {
            str(entry.get("case_id", "")): {
                "case_id": str(entry.get("case_id", "")),
                "directory": str(entry.get("directory", "")),
                "task_count": str(entry.get("task_count", "")),
                "source_track": str(entry.get("source_track", "")),
                "release_status": str(entry.get("release_status", "")),
            }
            for entry in entries
        }
        if len(observed_entries) != len(entries):
            errors.append(
                f"duplicate case ID in {index_path.relative_to(root)}"
            )
        expected_entries = expected_index_groups.get(group, {})
        if observed_entries != expected_entries:
            errors.append(
                f"index membership mismatch in {index_path.relative_to(root)}"
            )
        for entry in observed_entries.values():
            indexed_case = index_path.parent / entry["directory"] / "case.json"
            if not indexed_case.is_file():
                errors.append(
                    f"indexed case file missing: {indexed_case.relative_to(root)}"
                )
    if observed_index_groups != set(expected_index_groups):
        missing = sorted(set(expected_index_groups) - observed_index_groups)
        extra = sorted(observed_index_groups - set(expected_index_groups))
        errors.append(
            "example index groups do not match manifest; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )

    computed = {
        "release_scope": "representative_examples",
        "case_count": len(rows),
        "task_count": sum(int(row["task_count"]) for row in rows),
        "serialized_rubric_entry_count": example_summary.get(
            "serialized_rubric_entries"
        ),
        "source_track_counts": dict(sorted(source_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "subcategory_count": len(subcategory_counts),
        "subcategory_counts": dict(sorted(subcategory_counts.items())),
    }
    if saved != computed:
        errors.append(
            "examples_summary.json does not match manifest_public.csv "
            "and case JSON"
        )
    if computed["case_count"] != example_summary.get("cases"):
        errors.append("manifest case count does not match case JSON")
    if computed["task_count"] != example_summary.get("tasks"):
        errors.append("manifest task count does not match case JSON")
    return computed


def validate_released_results(
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    script = root / "evaluation/scripts/reproduce_released_examples.py"
    with tempfile.TemporaryDirectory(prefix="mcl-released-results-") as temp_dir:
        command = [
            sys.executable,
            str(script),
            "--output-dir",
            temp_dir,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        errors.append(
            "released-result validator failed: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        errors.append("released-result validator did not emit valid JSON")
        return {}
    return {
        "status": payload.get("status"),
        "cases": payload.get("cases"),
        "tasks": payload.get("tasks"),
        "models": payload.get("models"),
        "predictions": payload.get("predictions"),
        "judgments": payload.get("judgments"),
        "evaluation_errors": payload.get("evaluation_errors"),
        "corrections": payload.get("corrections"),
        "reference_summary_match": payload.get("reference_summary_match"),
    }


def validate_text_anonymity(root: Path, errors: list[str]) -> None:
    for path in repository_files(root):
        if path == Path(__file__).resolve():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        # Case text can legitimately quote generic paths from a public manual
        # (for example C:\Users\ME\Desktop). Media-reference paths are checked
        # structurally by validate_examples.py, so generic prose paths inside
        # case content are not treated as author-machine leakage.
        local_match = LOCAL_PATH_PATTERN.search(text)
        if local_match and relative.parts[0] != "examples":
            errors.append(f"local path or username in {relative}")
        if SECRET_PATTERN.search(text):
            errors.append(f"possible credential in {relative}")
        # Upstream sample IDs are public dataset identifiers and can
        # coincidentally contain a contributor-code substring.
        if (
            UPSTREAM_SAMPLE_MANIFEST not in relative.parents
            and relative.parts[:2] != ("evaluation", "released_examples")
            and LEGACY_CONTRIBUTOR_PATTERN.search(text)
        ):
            errors.append(f"legacy contributor code in {relative}")


def validate_paths_and_sizes(root: Path, errors: list[str]) -> None:
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        parts_lower = [part.lower() for part in relative.parts]
        if (
            ".git" in parts_lower
            or ".venv" in parts_lower
            or "__pycache__" in parts_lower
            or "reproduced" in parts_lower
        ):
            continue
        if path.name == ".DS_Store":
            errors.append(f"Finder metadata present: {relative}")
        if any(
            part in {"private", "manifest_private.csv", "results"}
            or part.endswith(("_result", "_results"))
            for part in parts_lower
        ):
            errors.append(f"private/result path present: {relative}")
        if path.is_file() and path.stat().st_size > MAX_GIT_FILE_BYTES:
            errors.append(
                f"file exceeds 95 MiB Git safety threshold: {relative} "
                f"({path.stat().st_size} bytes)"
            )


def validate_images(root: Path, errors: list[str]) -> dict[str, Any]:
    images = [
        path
        for path in (root / "examples").rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    formats = Counter()
    for path in sorted(images):
        try:
            with Image.open(path) as image:
                image_format = str(image.format).upper()
                formats[image_format] += 1
                if image.getexif():
                    errors.append(f"EXIF remains in {path.relative_to(root)}")
                risky_info = {
                    str(key).lower()
                    for key in image.info
                    if any(
                        marker in str(key).lower()
                        for marker in (
                            "author",
                            "comment",
                            "description",
                            "exif",
                            "software",
                            "xml",
                            "xmp",
                        )
                    )
                }
                if risky_info:
                    errors.append(
                        f"risky image metadata in {path.relative_to(root)}: "
                        f"{sorted(risky_info)}"
                    )
                expected_suffix = ".jpg" if image_format == "JPEG" else ".png"
                if image_format not in {"JPEG", "PNG"}:
                    errors.append(
                        f"unsupported image format {image_format}: "
                        f"{path.relative_to(root)}"
                    )
                elif path.suffix.lower() != expected_suffix:
                    errors.append(
                        f"image extension mismatch: {path.relative_to(root)} "
                        f"is {image_format}"
                    )
        except Exception as error:
            errors.append(f"unreadable image {path.relative_to(root)}: {error}")
    return {"count": len(images), "formats": dict(formats)}


def load_asset_manifest(root: Path) -> list[dict[str, str]]:
    path = root / "assets/asset_manifest.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_assets(
    root: Path,
    video_archive: Path | None,
    errors: list[str],
) -> dict[str, Any]:
    rows = load_asset_manifest(root)
    paths = [row["repository_path"] for row in rows]
    if len(paths) != len(set(paths)):
        errors.append("asset manifest contains duplicate repository paths")

    referenced_paths: set[str] = set()
    for case_path in sorted((root / "examples").glob("**/case.json")):
        try:
            tasks = json.loads(case_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for reference in case_media_references(tasks):
            if reference.startswith(("http://", "https://", "data:")):
                continue
            reference_path = Path(reference)
            if reference_path.is_absolute():
                errors.append(
                    f"absolute media reference in {case_path.relative_to(root)}: "
                    f"{reference}"
                )
                continue
            resolved = (case_path.parent / reference_path).resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                errors.append(
                    f"media reference escapes repository in "
                    f"{case_path.relative_to(root)}: {reference}"
                )
                continue
            referenced_paths.add(relative)
    declared_paths = set(paths)
    if referenced_paths != declared_paths:
        missing = sorted(referenced_paths - declared_paths)
        extra = sorted(declared_paths - referenced_paths)
        errors.append(
            "asset manifest does not match case media references; "
            f"unlisted={missing[:5]}, unreferenced={extra[:5]}"
        )

    actual_bundled_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "examples").glob("**/assets/*")
        if path.is_file() and path.name != ".DS_Store"
    }
    declared_bundled_paths = {
        row["repository_path"]
        for row in rows
        if row["bundled_in_git_tree"] == "yes"
    }
    if actual_bundled_paths != declared_bundled_paths:
        missing = sorted(actual_bundled_paths - declared_bundled_paths)
        extra = sorted(declared_bundled_paths - actual_bundled_paths)
        errors.append(
            "asset manifest does not match bundled case assets; "
            f"unlisted={missing[:5]}, missing={extra[:5]}"
        )

    external_rows: dict[str, dict[str, str]] = {}
    pending = 0
    for row in rows:
        released_path = root / row["repository_path"]
        pending += row["redistribution_status"].startswith("pending")
        if row["bundled_in_git_tree"] == "yes":
            if not released_path.is_file():
                errors.append(f"bundled asset missing: {row['repository_path']}")
                continue
            if str(released_path.stat().st_size) != row["bytes"]:
                errors.append(f"asset size mismatch: {row['repository_path']}")
            if sha256_file(released_path) != row["sha256"]:
                errors.append(f"asset hash mismatch: {row['repository_path']}")
        else:
            if released_path.exists():
                errors.append(
                    f"external asset unexpectedly bundled: {row['repository_path']}"
                )
            if Path(row["repository_path"]).suffix.lower() not in VIDEO_SUFFIXES:
                errors.append(
                    f"non-video external asset: {row['repository_path']}"
                )
            external_rows[row["repository_path"]] = row

    archive_checked = False
    if video_archive is not None:
        archive_checked = True
        if not video_archive.is_file():
            errors.append(f"video archive missing: {video_archive}")
        else:
            with tarfile.open(video_archive, mode="r") as archive:
                members = {
                    member.name: member
                    for member in archive.getmembers()
                    if member.isfile()
                }
                if set(members) != set(external_rows):
                    missing = sorted(set(external_rows) - set(members))
                    extra = sorted(set(members) - set(external_rows))
                    errors.append(
                        "video archive membership mismatch; "
                        f"missing={missing[:5]}, extra={extra[:5]}"
                    )
                for name, row in external_rows.items():
                    member = members.get(name)
                    if member is None:
                        continue
                    if str(member.size) != row["bytes"]:
                        errors.append(f"archived video size mismatch: {name}")
                    extracted = archive.extractfile(member)
                    if extracted is None or sha256_stream(extracted) != row["sha256"]:
                        errors.append(f"archived video hash mismatch: {name}")

    return {
        "manifest_rows": len(rows),
        "bundled_assets": sum(
            row["bundled_in_git_tree"] == "yes" for row in rows
        ),
        "external_videos": len(external_rows),
        "archive_checked": archive_checked,
        "pending_redistribution_decisions": pending,
    }


def write_checksums(root: Path) -> int:
    files = repository_files(root)
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in files
    ]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(files)


def validate_checksums(root: Path, errors: list[str]) -> int:
    checksum_path = root / "SHA256SUMS"
    if not checksum_path.is_file():
        errors.append("missing SHA256SUMS")
        return 0

    declared: dict[str, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            errors.append(f"invalid SHA256SUMS line {line_number}")
            continue
        digest, relative_path = parts
        if relative_path in declared:
            errors.append(f"duplicate SHA256SUMS path: {relative_path}")
            continue
        declared[relative_path] = digest

    expected_files = repository_files(root)
    expected_paths = {
        path.relative_to(root).as_posix(): path for path in expected_files
    }
    if set(declared) != set(expected_paths):
        missing = sorted(set(expected_paths) - set(declared))
        extra = sorted(set(declared) - set(expected_paths))
        errors.append(
            "SHA256SUMS path set mismatch; "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )
    for relative_path in sorted(set(declared) & set(expected_paths)):
        if sha256_file(expected_paths[relative_path]) != declared[relative_path]:
            errors.append(f"SHA-256 mismatch: {relative_path}")
    return len(declared)


def validate_reconciliation(root: Path, errors: list[str]) -> dict[str, Any]:
    folder = root / "evidence/evaluation_reconciliation"
    with tempfile.TemporaryDirectory(prefix="mcl-reconciliation-") as output:
        result = subprocess.run(
            [sys.executable, str(folder / "reproduce.py"), "--output-dir", output],
            capture_output=True, text=True,
        )
        if result.returncode:
            errors.append("full-task reconciliation failed: " + result.stderr[-400:])
            return {}
        for name in ["summary.json", "SUMMARY.md"]:
            if (Path(output) / name).read_bytes() != (folder / name).read_bytes():
                errors.append("full-task reconciliation differs: " + name)
    summary = json.loads((folder / "summary.json").read_text())
    return {"models": len(summary["models"]), "cases": 344,
            "tasks_per_model": 1080, "task_model_rows": 8640,
            "missing_scores": sum(m["score_missing_tasks"] for m in summary["models"]),
            "score_status_conflicts": len(summary["score_status_conflicts"]),
            "reference_summary_match": not any("reconciliation" in e for e in errors)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--video-archive", type=Path)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Run all checks without rewriting the report or SHA256SUMS.",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    errors: list[str] = []
    example_summary = validate_examples(root, errors)
    example_metadata = validate_example_metadata(root, example_summary, errors)
    released_result_summary = validate_released_results(root, errors)
    reconciliation_summary = validate_reconciliation(root, errors)
    validate_json_keys(root, errors)
    validate_text_anonymity(root, errors)
    validate_paths_and_sizes(root, errors)
    image_summary = validate_images(root, errors)
    asset_summary = validate_assets(root, args.video_archive, errors)

    checksum_files = 0
    if args.check_only:
        checksum_files = validate_checksums(root, errors)
    elif not errors:
        checksum_files = write_checksums(root)

    report = {
        "technical_status": "PASS" if not errors else "FAIL",
        "publication_status": "READY" if not errors else "NOT_READY",
        "examples": example_summary,
        "example_metadata": example_metadata,
        "released_example_results": released_result_summary,
        "full_task_reconciliation": reconciliation_summary,
        "images": image_summary,
        "assets": asset_summary,
        "checksummed_repository_files": checksum_files,
        "errors": errors,
    }
    if not args.check_only:
        (root / "REPOSITORY_VALIDATION.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
