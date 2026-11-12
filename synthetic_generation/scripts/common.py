from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_template(path: Path, replacements: dict[str, str]) -> str:
    rendered = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        marker = "{{" + key + "}}"
        if marker not in rendered:
            raise ValueError(f"Template marker missing: {marker} in {path}")
        rendered = rendered.replace(marker, value)
    return rendered


def image_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        raise ValueError(
            f"Unsupported visual asset {path}; render PDFs to PNG/JPEG first"
        )
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def normalize_dataset(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    aliases = {
        "slide-vqa": "slidevqa",
        "slidevqa": "slidevqa",
        "mmlongbenchdoc": "mmlongbench-doc",
        "mmlongbench-doc": "mmlongbench-doc",
    }
    return aliases.get(normalized, normalized)

