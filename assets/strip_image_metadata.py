#!/usr/bin/env python3
"""Strip image metadata from the anonymous release without changing its visuals.

JPEG files are rewritten losslessly with jpegtran. EXIF orientation is applied
as a lossless JPEG transform before the EXIF block is removed. PNG files are
decoded and saved without ancillary text/XMP/EXIF chunks. The script verifies
the displayed pixels before replacing each source file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat


JPEGTRAN = Path("/opt/anaconda3/bin/jpegtran")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
ORIENTATION_ARGS = {
    1: [],
    2: ["-flip", "horizontal"],
    3: ["-rotate", "180"],
    4: ["-flip", "vertical"],
    5: ["-transpose"],
    6: ["-rotate", "90"],
    7: ["-transverse"],
    8: ["-rotate", "270"],
}


def displayed_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        if getattr(image, "is_animated", False):
            raise ValueError(f"Animated image is not supported: {path}")
        return ImageOps.exif_transpose(image).convert("RGB")


def sanitize_jpeg(source: Path, output: Path) -> None:
    if not JPEGTRAN.is_file():
        raise FileNotFoundError(f"jpegtran was not found at {JPEGTRAN}")

    with Image.open(source) as image:
        orientation = int(image.getexif().get(274, 1))
    transform = ORIENTATION_ARGS.get(orientation)
    if transform is None:
        raise ValueError(f"Unsupported EXIF orientation {orientation}: {source}")

    command = [
        str(JPEGTRAN),
        "-copy",
        "none",
    ]
    if transform:
        command.append("-perfect")
        command.extend(transform)
    command.extend(["-outfile", str(output), str(source)])
    subprocess.run(command, check=True, capture_output=True)


def sanitize_png(source: Path, output: Path) -> None:
    with Image.open(source) as image:
        if getattr(image, "is_animated", False):
            raise ValueError(f"Animated PNG is not supported: {source}")
        image.load()
        image.save(output, format="PNG", optimize=False)


def verify_visual_equivalence(source: Path, output: Path, image_format: str) -> None:
    expected = displayed_rgb(source)
    actual = displayed_rgb(output)
    if expected.size != actual.size:
        raise ValueError(
            f"Displayed size changed for {source}: {expected.size} -> {actual.size}"
        )

    difference = ImageChops.difference(expected, actual)
    extrema = difference.getextrema()
    maximum = max(channel[1] for channel in extrema)
    rms = max(ImageStat.Stat(difference).rms)

    # PNG rewriting is exact. Lossless JPEG coefficient transforms can produce
    # decode-rounding differences of a few intensity levels after rotation.
    if image_format == "PNG":
        if maximum != 0:
            raise ValueError(f"PNG pixels changed for {source}; max delta={maximum}")
    elif maximum > 4 or rms > 1.0:
        raise ValueError(
            f"JPEG visual changed unexpectedly for {source}; "
            f"max delta={maximum}, rms={rms:.4f}"
        )


def sanitize_file(source: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{source.name}.", suffix=".sanitized", dir=source.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with Image.open(source) as image:
            image_format = str(image.format).upper()
        if image_format == "JPEG":
            sanitize_jpeg(source, temporary)
        elif image_format == "PNG":
            sanitize_png(source, temporary)
        else:
            raise ValueError(f"Unsupported image format {image_format}: {source}")
        verify_visual_equivalence(source, temporary, image_format)
        shutil.copymode(source, temporary)
        os.replace(temporary, source)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--examples",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples",
        help="Examples directory in the anonymous repository.",
    )
    args = parser.parse_args()

    images = sorted(
        path
        for path in args.examples.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        raise SystemExit(f"No images found under {args.examples}")

    for index, image in enumerate(images, start=1):
        sanitize_file(image)
        if index % 100 == 0 or index == len(images):
            print(f"sanitized {index}/{len(images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
