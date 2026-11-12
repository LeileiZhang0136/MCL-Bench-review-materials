#!/usr/bin/env python3
"""Make image filename extensions agree with their decoded formats.

The source collection contains a small number of PNG files named ``*.jpg`` and
JPEG files named ``*.png``. This utility renames those files inside the
anonymous examples package and updates JSON references in the same case.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from PIL import Image


FORMAT_SUFFIX = {"JPEG": ".jpg", "PNG": ".png"}


def replace_text(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    updated = text.replace(old, new)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".updated", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--examples",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples",
    )
    args = parser.parse_args()

    changes: list[tuple[Path, Path]] = []
    for source in sorted(args.examples.glob("**/assets/*")):
        if not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        with Image.open(source) as image:
            expected_suffix = FORMAT_SUFFIX.get(str(image.format).upper())
        if expected_suffix is None or source.suffix.lower() == expected_suffix:
            continue
        target = source.with_suffix(expected_suffix)
        if target.exists():
            raise FileExistsError(f"Cannot rename {source}; target exists: {target}")
        changes.append((source, target))

    for source, target in changes:
        case_directory = source.parent.parent
        updated_references = 0
        for json_path in case_directory.rglob("*.json"):
            updated_references += replace_text(json_path, source.name, target.name)
        if updated_references == 0:
            raise ValueError(f"No JSON reference found for {source}")
        source.rename(target)
        print(f"{source.relative_to(args.examples)} -> {target.name}")

    print(f"normalized {len(changes)} image filename extensions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
