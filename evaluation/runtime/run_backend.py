#!/usr/bin/env python3
"""Standalone MCL-Bench backend runner.

This script extracts the non-UI backend flow from ``app.py`` so it can be run
from the command line without Gradio:

1. Load a JSON/JSONL dataset.
2. Resolve relative image/video paths.
3. Run model inference.
4. Run rubric-based evaluation.
5. Export JSONL results.

It intentionally keeps the same data format and most of the same model calling
logic as ``app.py``.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import mimetypes
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable

import requests as _requests
from openai import OpenAI


def load_env_file(path: str) -> None:
    """Load a simple KEY=VALUE env file into os.environ."""
    if not path or not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_env_mb_bytes(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(float(raw) * 1024 * 1024)
    except ValueError:
        return default


APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_env_file(os.path.join(APP_DIR, "app_config.env"))

DEFAULT_BASE_URL = os.getenv("CLBENCH_OPENAI_BASE_URL", "")
CLAUDE_API_URL = os.getenv("CLBENCH_CLAUDE_API_URL", "")
DEFAULT_API_KEY = os.getenv("CLBENCH_OPENAI_API_KEY", "")
GEMINI_API_URL = os.getenv("CLBENCH_GEMINI_API_URL", "")
GPT_BASE_URL = os.getenv("CLBENCH_GPT_BASE_URL", "")
DOUBAO_BASE_URL = os.getenv("CLBENCH_DOUBAO_BASE_URL", "")
DEFAULT_MAX_RETRIES = 20
DEFAULT_API_TIMEOUT = _get_env_int("CLBENCH_API_TIMEOUT", 1800)
DEFAULT_CLAUDE_TIMEOUT = _get_env_int("CLBENCH_CLAUDE_TIMEOUT", DEFAULT_API_TIMEOUT)
DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES = _get_env_int("CLBENCH_CLAUDE_EMPTY_TEXT_RETRIES", 3)
DEFAULT_API_TIMEOUT_RETRIES = _get_env_int("CLBENCH_API_TIMEOUT_RETRIES", 10)
DEFAULT_CLAUDE_TIMEOUT_RETRIES = _get_env_int(
    "CLBENCH_CLAUDE_TIMEOUT_RETRIES",
    DEFAULT_API_TIMEOUT_RETRIES,
)
DEFAULT_IMAGE_MAX_SIDE = 2000
DEFAULT_IMAGE_MIN_SIDE = 16
DEFAULT_IMAGE_JPEG_QUALITY = 90
DEFAULT_IMAGE_MAX_BYTES = int(4.5 * 1024 * 1024)
DEFAULT_APPROX_PAYLOAD_LIMIT_BYTES = _get_env_mb_bytes(
    "CLBENCH_PAYLOAD_SOFT_LIMIT_MB",
    18 * 1024 * 1024,
)
DEFAULT_GPT_APPROX_PAYLOAD_LIMIT_BYTES = _get_env_mb_bytes(
    "CLBENCH_GPT_PAYLOAD_SOFT_LIMIT_MB",
    DEFAULT_APPROX_PAYLOAD_LIMIT_BYTES,
)
DEFAULT_DOUBAO_APPROX_PAYLOAD_LIMIT_BYTES = _get_env_mb_bytes(
    "CLBENCH_DOUBAO_PAYLOAD_SOFT_LIMIT_MB",
    DEFAULT_APPROX_PAYLOAD_LIMIT_BYTES,
)
DEFAULT_JUDGE_PARSE_RETRIES = 2
DEFAULT_DOUBAO_VIDEO_LIMIT = 10
DEFAULT_DOUBAO_IMAGE_MERGE_LIMITS = (160, 120, 90, 60, 40, 30, 24, 16, 12, 8, 4)
DEFAULT_OPENAI_IMAGE_MERGE_LIMITS = (50, 50, 40, 32, 24, 16, 12, 8, 4)
DEFAULT_HISTORY_MEDIA_POLICY = os.getenv(
    "CLBENCH_HISTORY_MEDIA_POLICY",
    "full",
).strip() or "full"
DEFAULT_TEXT_COMPACT_MIN_CHARS = _get_env_int("CLBENCH_TEXT_COMPACT_MIN_CHARS", 300000)
DEFAULT_HISTORY_TEXT_PREVIEW_CHARS = _get_env_int("CLBENCH_HISTORY_TEXT_PREVIEW_CHARS", 1200)

LOG_DIR = os.path.join(APP_DIR, "logs")
OUTPUT_DIR = os.path.join(APP_DIR, "output")
GRADE_LOG_DIR = os.path.join(APP_DIR, "grade_logs")
GRADE_DIR = os.path.join(APP_DIR, "grade")

_MEDIA_SEARCH_CACHE: dict[tuple[str, str], str] = {}
AttemptLogger = Callable[[str], None]


class NonRetryableClaudeError(RuntimeError):
    """Raised when a Claude response should not be retried."""


class NonRetryableAPIError(RuntimeError):
    """Raised when an API request failed in a way that retrying cannot fix."""


def _truncate_for_log(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    omitted = len(value) - limit
    return f"{value[:limit]}...<truncated {omitted} chars>"


def _format_claude_debug_value(value: Any, limit: int = 4000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except Exception:
        rendered = repr(value)
    return _truncate_for_log(rendered, limit)


def _build_claude_empty_text_error(resp_json: dict[str, Any]) -> str:
    return (
        "Claude returned empty text, "
        f"stop_reason={resp_json.get('stop_reason')!r}, "
        f"content={_format_claude_debug_value(resp_json.get('content', []))}, "
        f"resp keys={list(resp_json.keys())}"
    )


def _extract_claude_text(resp_json: dict[str, Any]) -> str:
    text_parts = [
        block.get("text", "")
        for block in resp_json.get("content", [])
        if block.get("type") == "text"
    ]
    return "\n".join(text_parts).strip()


def _is_claude_empty_text_max_tokens(resp_json: dict[str, Any]) -> bool:
    return resp_json.get("stop_reason") == "max_tokens" and not _extract_claude_text(resp_json)


def _is_claude_empty_text_error(error: Any) -> bool:
    return "claude returned empty text" in str(error).lower()


def _log_attempt_event(attempt_logger: AttemptLogger | None, message: str) -> None:
    if attempt_logger is None:
        return
    attempt_logger(_truncate_for_log(message, 2000))


def _build_attempt_logger(
    log_path: str,
    stage: str,
    idx: int,
    task_id: str,
    model: str,
) -> AttemptLogger:
    prefix = f"[{stage}][attempt] idx={idx} task={task_id} model={model}"

    def _logger(message: str) -> None:
        log_and_print(log_path, f"{prefix} {message}")

    return _logger


def _is_remote_or_absolute_src(src: str) -> bool:
    return bool(src) and src.startswith(("/", "file://", "http", "data:"))


def _find_media_by_basename(media_root: str, src: str) -> str | None:
    """Recursively search a media root by basename as a fallback."""
    media_root_abs = os.path.abspath(media_root)
    basename = os.path.basename(src)
    if not basename:
        return None

    cache_key = (media_root_abs, basename)
    if cache_key in _MEDIA_SEARCH_CACHE:
        cached = _MEDIA_SEARCH_CACHE[cache_key]
        return cached or None

    for walk_root, _dirs, files in os.walk(media_root_abs):
        if basename in files:
            found = os.path.join(walk_root, basename)
            _MEDIA_SEARCH_CACHE[cache_key] = found
            return found

    _MEDIA_SEARCH_CACHE[cache_key] = ""
    return None


def _resolve_media_path(src: str, base_dir: str, media_path: str = "") -> str:
    """Resolve a relative media path against media_path first, then JSON dir."""
    if not src or _is_remote_or_absolute_src(src):
        return src

    candidates: list[str] = []
    media_path = (media_path or "").strip()
    if media_path:
        media_abs = os.path.abspath(media_path)
        if os.path.isdir(media_abs):
            candidates.append(os.path.join(media_abs, src))
            candidates.append(os.path.join(media_abs, os.path.basename(src)))
            recursive_hit = _find_media_by_basename(media_abs, src)
            if recursive_hit:
                candidates.append(recursive_hit)
        elif os.path.isfile(media_abs):
            if os.path.basename(src) == os.path.basename(media_abs):
                candidates.append(media_abs)

    candidates.append(os.path.join(base_dir, src))

    seen = set()
    deduped_candidates = []
    for candidate in candidates:
        abs_candidate = os.path.abspath(candidate)
        if abs_candidate not in seen:
            seen.add(abs_candidate)
            deduped_candidates.append(abs_candidate)

    for candidate in deduped_candidates:
        if os.path.exists(candidate):
            return candidate

    return deduped_candidates[0] if deduped_candidates else os.path.abspath(os.path.join(base_dir, src))


def resolve_relative_paths(
    data: list[dict[str, Any]],
    base_dir: str,
    media_path: str = "",
) -> list[dict[str, Any]]:
    """Resolve relative image/video paths in message content to absolute paths."""
    for item in data:
        for msg in item.get("messages", []):
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                part_type = part.get("type", "")
                if part_type == "image_url":
                    url_obj = part.get("image_url", {})
                    if isinstance(url_obj, dict):
                        src = url_obj.get("url", "")
                        if src and not _is_remote_or_absolute_src(src):
                            url_obj["url"] = _resolve_media_path(src, base_dir, media_path)
                elif part_type == "video":
                    video_obj = part.get("video", {})
                    if isinstance(video_obj, dict):
                        src = video_obj.get("url", "")
                        if src and not _is_remote_or_absolute_src(src):
                            video_obj["url"] = _resolve_media_path(src, base_dir, media_path)
                    elif isinstance(video_obj, str):
                        src = video_obj
                        if src and not _is_remote_or_absolute_src(src):
                            part["video"] = _resolve_media_path(src, base_dir, media_path)
    return data


def load_data_file(path: str, media_path: str = "") -> list[dict[str, Any]]:
    """Load JSON or JSONL file and always return a list."""
    file_path = path.strip()
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    base_dir = os.path.dirname(os.path.abspath(file_path))
    with open(file_path, "r", encoding="utf-8") as f:
        if file_path.endswith(".jsonl"):
            data = [json.loads(line) for line in f if line.strip()]
        else:
            obj = json.load(f)
            data = obj if isinstance(obj, list) else [obj]
    return resolve_relative_paths(data, base_dir, media_path)


def save_data_file(data: list[dict[str, Any]], path: str) -> str:
    """Save data as JSON or JSONL based on output file suffix."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if path.endswith(".json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def save_jsonl(data: list[dict[str, Any]], path: str) -> str:
    """Backward-compatible wrapper; also supports .json outputs."""
    return save_data_file(data, path)


def sanitize_filename_part(value: str, default: str = "unknown_model") -> str:
    cleaned = "".join(
        c if c.isalnum() or c in {"-", "_", "."} else "_"
        for c in (value or "").strip()
    )
    cleaned = cleaned.strip("._")
    return cleaned or default


def get_source_filename(path_or_name: str) -> str:
    base = os.path.basename((path_or_name or "").strip())
    return base or "unknown_input.json"


def get_source_file_tag(path_or_name: str) -> str:
    source_name = get_source_filename(path_or_name)
    stem, _ = os.path.splitext(source_name)
    return sanitize_filename_part(stem or source_name, default="unknown_input")


def build_output_jsonl_path(output_dir: str, prefix: str, model: str, source_name: str) -> str:
    model_tag = sanitize_filename_part(model)
    source_tag = get_source_file_tag(source_name)
    return os.path.join(
        output_dir,
        f"{prefix}_{source_tag}_{model_tag}_{datetime.now():%Y%m%d_%H%M%S}.jsonl",
    )


def create_log_file(prefix: str, log_dir: str | None = None) -> str:
    directory = log_dir or LOG_DIR
    os.makedirs(directory, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(directory, f"{prefix}_{ts}.log")


def write_log(log_path: str, message: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_task_id(item: dict[str, Any]) -> str:
    return str(item.get("metadata", {}).get("task_id", item.get("idx", "N/A")))


def _image_format_to_mime(fmt: str | None) -> str | None:
    normalized = (fmt or "").upper()
    return {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
        "BMP": "image/bmp",
    }.get(normalized)


def _guess_file_mime(path: str) -> str:
    try:
        from PIL import Image

        with Image.open(path) as img:
            detected = _image_format_to_mime(img.format)
            if detected:
                return detected
    except Exception:
        pass

    mime, _ = mimetypes.guess_type(path)
    if mime:
        return mime
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
    }.get(ext, "application/octet-stream")


def _file_to_data_uri(file_path: str) -> str:
    """Read a local file and return a base64 data URI."""
    path = file_path.replace("file://", "")
    mime = _guess_file_mime(path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_doubao_model(model: str) -> bool:
    return "doubao" in model.lower() or "seed" in model.lower()


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _gemini_api_url(base_url: str) -> str:
    if GEMINI_API_URL:
        return GEMINI_API_URL.rstrip("/")
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/gemini") or cleaned.endswith("/responses"):
        return cleaned
    return _join_url(cleaned, "responses")


def _openai_base_url_for_model(model: str) -> str:
    if _is_doubao_model(model):
        return (DOUBAO_BASE_URL or DEFAULT_BASE_URL).rstrip("/")
    return (GPT_BASE_URL or DEFAULT_BASE_URL).rstrip("/")


def _is_gemini_native_model(model: str) -> bool:
    model_lower = model.lower()
    return "gemini 3" in model_lower or "gemini-3" in model_lower


def _get_gemini_api_model(model: str) -> str:
    if model.endswith(" (High)"):
        return model[: -len(" (High)")]
    return model


def _get_gemini_generation_config(model: str) -> dict[str, Any] | None:
    model_lower = model.lower()
    if "(high)" in model_lower:
        return {"thinkingConfig": {"thinkingLevel": "HIGH"}}
    if model_lower.strip() == "gemini 3-pro-preview":
        return {"thinkingConfig": {"includeThoughts": True}}
    return None


def _is_claude_model(model: str) -> bool:
    return "claude" in model.lower()


def _get_claude_thinking_config(model: str) -> dict[str, Any] | None:
    model_lower = model.lower()
    if "thinking" not in model_lower:
        return None
    budget_tokens = 12000 if "opus" in model_lower else 10000
    return {"type": "enabled", "budget_tokens": budget_tokens}


def _get_claude_thinking_budgets(model: str) -> list[int]:
    model_lower = model.lower()
    if "thinking" not in model_lower:
        return []
    if "opus" in model_lower:
        return [12000, 8000, 6000, 4000, 2000, 1024]
    return [10000, 8000, 6000, 4000, 2000, 1024]


def _get_claude_api_model(model: str) -> str:
    if model.endswith(" Thinking"):
        return model[: -len(" Thinking")]
    return model


def _messages_to_claude_format(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Convert OpenAI-style messages to Claude messages format."""
    claude_msgs = []
    system_text = None
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if role == "system":
            if isinstance(content, str):
                system_text = content
            elif isinstance(content, list):
                system_text = " ".join(
                    part.get("text", "")
                    for part in content
                    if part.get("type") == "text"
                )
            continue

        if isinstance(content, str):
            claude_msgs.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            claude_parts = []
            for part in content:
                part_type = part.get("type", "")
                if part_type == "text":
                    claude_parts.append({"type": "text", "text": part.get("text", "")})
                elif part_type == "image_url":
                    url_obj = part.get("image_url", {})
                    src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                    if src.startswith("data:"):
                        header, b64data = src.split(",", 1)
                        mime = header.split(":")[1].split(";")[0]
                        if mime.startswith("video/"):
                            claude_parts.append({"type": "text", "text": "[Video content]"})
                        else:
                            claude_parts.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime,
                                        "data": b64data,
                                    },
                                }
                            )
                    elif src.startswith("http"):
                        claude_parts.append(
                            {"type": "image", "source": {"type": "url", "url": src}}
                        )
                    else:
                        claude_parts.append({"type": "text", "text": f"[Image: {src}]"})
                else:
                    claude_parts.append(
                        {"type": "text", "text": json.dumps(part, ensure_ascii=False)}
                    )
            if claude_parts:
                claude_msgs.append({"role": role, "content": claude_parts})
            continue

        claude_msgs.append({"role": role, "content": str(content)})
    return claude_msgs, system_text


def _messages_to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-style messages to Gemini contents format."""
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "assistant":
            role = "model"
        elif role == "system":
            role = "user"

        content = msg.get("content")
        parts = []

        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for part in content:
                part_type = part.get("type", "")
                if part_type == "text":
                    parts.append({"text": part.get("text", "")})
                elif part_type == "image_url":
                    url_obj = part.get("image_url", {})
                    src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                    if src.startswith("data:"):
                        header, b64data = src.split(",", 1)
                        mime = header.split(":")[1].split(";")[0]
                        parts.append({"inline_data": {"mime_type": mime, "data": b64data}})
                    elif src.startswith("http"):
                        parts.append(
                            {"file_data": {"file_uri": src, "mime_type": "image/jpeg"}}
                        )
                    else:
                        parts.append({"text": f"[Image: {src}]"})
                elif part_type in {"video", "video_url"}:
                    if part_type == "video_url":
                        url_obj = part.get("video_url", {})
                        src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                    else:
                        video_obj = part.get("video", {})
                        src = video_obj.get("url", "") if isinstance(video_obj, dict) else str(video_obj)
                    if src.startswith("data:"):
                        header, b64data = src.split(",", 1)
                        mime = header.split(":")[1].split(";")[0]
                        parts.append({"inline_data": {"mime_type": mime, "data": b64data}})
                    elif src.startswith("http"):
                        parts.append(
                            {"file_data": {"file_uri": src, "mime_type": "video/mp4"}}
                        )
                    else:
                        parts.append({"text": f"[Video: {src}]"})
                else:
                    parts.append({"text": json.dumps(part, ensure_ascii=False)})

        if parts:
            contents.append({"role": role, "parts": parts})
    return contents


def _compress_video_with_av(src_path: str, target_mb: float = 10) -> str:
    """Compress a video with PyAV and return a temp file path."""
    import math
    import tempfile

    path = src_path.replace("file://", "")
    try:
        import av
    except Exception:
        return src_path

    try:
        container = av.open(path)
    except Exception:
        return src_path

    video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
    if video_stream is None:
        container.close()
        return src_path

    orig_w = int(video_stream.codec_context.width or 0)
    orig_h = int(video_stream.codec_context.height or 0)
    if orig_w <= 0 or orig_h <= 0:
        container.close()
        return src_path

    duration = None
    if video_stream.duration:
        duration = float(video_stream.duration * video_stream.time_base)
    if not duration and container.duration:
        duration = container.duration / 1_000_000
    duration = max(float(duration or 60), 1.0)

    target_bytes = max(float(target_mb), 0.1) * 1024 * 1024
    target_bps = max(16_000, int(target_bytes * 8 * 0.8 / duration))
    if target_mb <= 0.5:
        out_fps = 1
    elif target_mb <= 1:
        out_fps = 2
    elif target_mb <= 2:
        out_fps = 4
    else:
        out_fps = 8

    pixels_per_frame = max(1, target_bps / (out_fps * 0.06))
    scale = math.sqrt(pixels_per_frame / max(orig_w * orig_h, 1))
    scale = max(min(scale, 1.0), 0.08)
    new_w = max(int(orig_w * scale), 64)
    new_h = max(int(orig_h * scale), 64)
    new_w -= new_w % 2
    new_h -= new_h % 2

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        output = av.open(tmp_path, "w")
        try:
            out_stream = output.add_stream("libx264", rate=out_fps)
        except Exception:
            out_stream = output.add_stream("mpeg4", rate=out_fps)
        out_stream.width = new_w
        out_stream.height = new_h
        out_stream.pix_fmt = "yuv420p"
        out_stream.bit_rate = target_bps

        last_time = -1e9
        interval = 1.0 / out_fps
        for frame in container.decode(video_stream):
            if frame.pts is not None:
                timestamp = float(frame.pts * frame.time_base)
                if timestamp < last_time + interval:
                    continue
                last_time = timestamp
            frame = frame.reformat(width=new_w, height=new_h, format="yuv420p")
            for packet in out_stream.encode(frame):
                output.mux(packet)
        for packet in out_stream.encode():
            output.mux(packet)
        output.close()
    except Exception:
        try:
            output.close()
        except Exception:
            pass
        container.close()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return src_path

    container.close()
    if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return src_path
    return tmp_path


def _compress_video(src_path: str, target_mb: float = 10) -> str:
    """Compress a video and return a temp file path."""
    import math
    import tempfile

    try:
        import cv2
    except Exception:
        return _compress_video_with_av(src_path, target_mb)

    path = src_path.replace("file://", "")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return _compress_video_with_av(src_path, target_mb)

    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / orig_fps if orig_fps else 60

    sample_n = min(30, total_frames)
    sample_w = min(480, orig_w)
    sample_scale = sample_w / orig_w
    sample_h = int(orig_h * sample_scale)
    sample_w -= sample_w % 2
    sample_h -= sample_h % 2

    temp_sample = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    temp_sample_path = temp_sample.name
    temp_sample.close()

    sample_writer = cv2.VideoWriter(
        temp_sample_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        8,
        (sample_w, sample_h),
    )
    if sample_writer.isOpened():
        interval = max(1, total_frames // sample_n)
        written = 0
        for frame_idx in range(0, total_frames, interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            sample_writer.write(cv2.resize(frame, (sample_w, sample_h)))
            written += 1
            if written >= sample_n:
                break
        sample_writer.release()
        sample_bytes = os.path.getsize(temp_sample_path)
        sample_pixels = sample_w * sample_h * written
        bpp = sample_bytes / sample_pixels if sample_pixels > 0 else 0.08
        bpp *= 1.3
    else:
        bpp = 0.08

    os.unlink(temp_sample_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    target_bytes = target_mb * 1024 * 1024
    for out_fps in [8, 4, 2, 1]:
        pixel_budget = orig_w * orig_h * out_fps * duration * bpp
        if pixel_budget <= 0:
            continue
        scale = math.sqrt(target_bytes / pixel_budget)
        scale = min(scale, 1.0)
        if scale >= 0.15:
            break
    else:
        out_fps = 1
        scale = 0.15

    new_w = max(int(orig_w * scale), 64)
    new_h = max(int(orig_h * scale), 64)
    new_w -= new_w % 2
    new_h -= new_h % 2

    frame_interval = max(1, int(orig_fps / out_fps))

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_path = tmp.name
    tmp.close()

    writer = cv2.VideoWriter(
        tmp_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        out_fps,
        (new_w, new_h),
    )
    if not writer.isOpened():
        cap.release()
        os.unlink(tmp_path)
        return _compress_video_with_av(src_path, target_mb)

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            writer.write(cv2.resize(frame, (new_w, new_h)))
        frame_idx += 1

    writer.release()
    cap.release()

    if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return _compress_video_with_av(src_path, target_mb)
    if os.path.getsize(tmp_path) > max(target_mb * 1024 * 1024 * 1.5, 1024 * 1024):
        fallback_path = _compress_video_with_av(src_path, target_mb)
        if fallback_path != src_path:
            os.unlink(tmp_path)
            return fallback_path
    return tmp_path


def _extract_video_frames(
    video_path: str,
    fps: float = 2,
    max_frames: int = 50,
    max_size: int = 1024,
) -> list[str]:
    """Extract frames from a video at the given fps as base64 JPEG strings."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return _extract_video_frames_with_av(video_path, fps, max_frames, max_size)

    path = video_path.replace("file://", "")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return _extract_video_frames_with_av(video_path, fps, max_frames, max_size)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    if total <= 0:
        cap.release()
        return _extract_video_frames_with_av(video_path, fps, max_frames, max_size)

    duration = total / video_fps
    n_frames = max(1, int(duration * fps))
    n_frames = min(n_frames, total, max_frames)
    indices = np.linspace(0, total - 1, n_frames, dtype=int)

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue
        height, width = frame.shape[:2]
        if max(height, width) > max_size:
            scale = max_size / max(height, width)
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frames.append(base64.b64encode(buf).decode("utf-8"))

    cap.release()
    return frames or _extract_video_frames_with_av(video_path, fps, max_frames, max_size)


def _extract_video_frames_with_av(
    video_path: str,
    fps: float = 2,
    max_frames: int = 50,
    max_size: int = 1024,
) -> list[str]:
    """Fallback frame extraction for videos OpenCV cannot decode."""
    try:
        import av
        import io
    except Exception:
        return []

    path = video_path.replace("file://", "")
    try:
        container = av.open(path)
    except Exception:
        return []

    frames: list[str] = []
    try:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            return []

        interval = 1.0 / max(float(fps), 0.001)
        next_time = 0.0
        max_frames = max(1, int(max_frames))
        for frame in container.decode(stream):
            frame_time = frame.time
            if frame_time is None and frame.pts is not None and stream.time_base is not None:
                frame_time = float(frame.pts * stream.time_base)
            if frame_time is None:
                frame_time = next_time
            frame_time = float(frame_time)
            if frame_time + 1e-6 < next_time:
                continue

            image = frame.to_image()
            if image.mode != "RGB":
                image = image.convert("RGB")
            width, height = image.size
            if max_size > 0 and max(width, height) > max_size:
                scale = max_size / max(width, height)
                image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))

            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=80, optimize=True)
            frames.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
            if len(frames) >= max_frames:
                break
            next_time += interval
    except Exception:
        return frames
    finally:
        try:
            container.close()
        except Exception:
            pass
    return frames


def _encode_image_to_data_uri(
    img: Any,
    mime: str,
    jpeg_quality: int,
    force_jpeg: bool,
    max_bytes: int = DEFAULT_IMAGE_MAX_BYTES,
) -> str:
    import io
    import math

    out_fmt = "JPEG"
    out_mime = "image/jpeg"
    rendered = img
    if not force_jpeg:
        if mime == "image/png":
            out_fmt, out_mime = "PNG", "image/png"
        elif mime == "image/webp":
            out_fmt, out_mime = "WEBP", "image/webp"
        elif mime in {"image/jpeg", "image/jpg"}:
            out_fmt, out_mime = "JPEG", "image/jpeg"

    if out_fmt == "JPEG" and rendered.mode != "RGB":
        rendered = rendered.convert("RGB")

    def render_bytes(image: Any, fmt: str, quality: int) -> bytes:
        buf = io.BytesIO()
        save_kwargs: dict[str, Any] = {}
        if fmt == "JPEG":
            save_kwargs = {"quality": quality, "optimize": True}
        image.save(buf, format=fmt, **save_kwargs)
        return buf.getvalue()

    quality = max(20, min(int(jpeg_quality), 95))
    raw = render_bytes(rendered, out_fmt, quality)
    if max_bytes > 0 and len(raw) > max_bytes and out_fmt != "JPEG":
        out_fmt, out_mime = "JPEG", "image/jpeg"
        if rendered.mode != "RGB":
            rendered = rendered.convert("RGB")
        raw = render_bytes(rendered, out_fmt, quality)

    quality_steps = [quality, 82, 72, 62, 52, 45, 38, 32, 26]
    seen_qualities: set[int] = set()
    if out_fmt == "JPEG" and max_bytes > 0:
        for candidate_quality in quality_steps:
            if candidate_quality in seen_qualities or candidate_quality > quality:
                continue
            seen_qualities.add(candidate_quality)
            raw = render_bytes(rendered, out_fmt, candidate_quality)
            if len(raw) <= max_bytes:
                break
        while len(raw) > max_bytes and min(rendered.size) > 64:
            scale = max(0.5, min(0.9, math.sqrt(max_bytes / len(raw)) * 0.92))
            new_size = (
                max(1, int(rendered.size[0] * scale)),
                max(1, int(rendered.size[1] * scale)),
            )
            rendered = rendered.resize(new_size)
            raw = render_bytes(rendered, out_fmt, min(seen_qualities or {quality}))

    new_b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{out_mime};base64,{new_b64}"


def _resize_image_for_limits(
    img: Any,
    max_side: int = DEFAULT_IMAGE_MAX_SIDE,
    min_side: int = DEFAULT_IMAGE_MIN_SIDE,
) -> Any:
    w, h = img.size
    scale = 1.0
    if max_side > 0 and max(w, h) > max_side:
        scale = min(scale, max_side / float(max(w, h)))
    if min_side > 0 and min(w, h) * scale < min_side:
        scale = max(scale, min_side / float(max(1, min(w, h))))
    if abs(scale - 1.0) < 0.001:
        return img.copy()
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.copy().resize(new_size)


def _downscale_data_uri_if_needed(
    data_uri: str,
    max_side: int = DEFAULT_IMAGE_MAX_SIDE,
    jpeg_quality: int = DEFAULT_IMAGE_JPEG_QUALITY,
    force_jpeg: bool = False,
) -> str:
    """Shrink a base64 data:image URI using the provided resize/quality budget."""
    try:
        header, b64data = data_uri.split(",", 1)
    except ValueError:
        return data_uri
    mime = header.split(":", 1)[-1].split(";", 1)[0] if ":" in header else ""
    if not mime.startswith("image/"):
        return data_uri

    try:
        import io
        from PIL import Image
    except Exception:
        return data_uri

    try:
        raw = base64.b64decode(b64data)
        with Image.open(io.BytesIO(raw)) as img:
            actual_mime = _image_format_to_mime(img.format) or mime
            w, h = img.size
            needs_resize = max(w, h) > max_side or min(w, h) < DEFAULT_IMAGE_MIN_SIDE
            needs_reencode = len(raw) > DEFAULT_IMAGE_MAX_BYTES or actual_mime != mime
            if (
                not needs_resize
                and not needs_reencode
                and jpeg_quality >= DEFAULT_IMAGE_JPEG_QUALITY
                and not force_jpeg
            ):
                return data_uri
            resized = _resize_image_for_limits(img, max_side=max_side)
            return _encode_image_to_data_uri(
                resized,
                actual_mime,
                jpeg_quality=jpeg_quality,
                force_jpeg=force_jpeg,
            )
    except Exception:
        return data_uri


def _downscale_image_if_needed(
    file_path: str,
    max_side: int = DEFAULT_IMAGE_MAX_SIDE,
    jpeg_quality: int = DEFAULT_IMAGE_JPEG_QUALITY,
    force_jpeg: bool = False,
) -> str:
    """Return a compressed image path under the given resize/quality budget."""
    path = file_path.replace("file://", "")
    try:
        from PIL import Image
    except Exception:
        return file_path

    try:
        with Image.open(path) as img:
            actual_mime = _image_format_to_mime(img.format) or _guess_file_mime(path)
            w, h = img.size
            needs_resize = max(w, h) > max_side or min(w, h) < DEFAULT_IMAGE_MIN_SIDE
            needs_reencode = os.path.getsize(path) > DEFAULT_IMAGE_MAX_BYTES
            guessed_mime = _guess_file_mime(path)
            if (
                not needs_resize
                and not needs_reencode
                and guessed_mime == actual_mime
                and jpeg_quality >= DEFAULT_IMAGE_JPEG_QUALITY
                and not force_jpeg
            ):
                return file_path
            resized = _resize_image_for_limits(img, max_side=max_side)

            import tempfile
            ext = os.path.splitext(path)[1].lower()
            if force_jpeg:
                suffix = ".jpg"
            else:
                suffix = ext if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"} else ".jpg"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp_path = tmp.name
            tmp.close()
            save_kwargs: dict[str, Any] = {}
            if suffix in {".jpg", ".jpeg"}:
                save_kwargs["quality"] = jpeg_quality
                save_kwargs["optimize"] = True
                if resized.mode != "RGB":
                    resized = resized.convert("RGB")
            resized.save(tmp_path, **save_kwargs)
            return tmp_path
    except Exception:
        return file_path


def _count_text_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "text":
                total += len(str(part.get("text", "")))
    return total


def _compact_text_value(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "\n\n[... text omitted to fit model context ...]\n\n"
    if max_chars <= len(marker) + 40:
        return text[:max_chars]
    head_chars = max(20, (max_chars - len(marker)) // 3)
    tail_chars = max_chars - len(marker) - head_chars
    return text[:head_chars] + marker + text[-tail_chars:]


def _compact_text_to_budget(
    messages: list[dict[str, Any]],
    max_text_chars: int,
) -> list[dict[str, Any]]:
    if max_text_chars <= 0:
        return messages

    copied: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    for msg_idx, msg in enumerate(messages):
        role = str(msg.get("role", ""))
        content = msg.get("content")
        if isinstance(content, list):
            new_content = []
            for part_idx, part in enumerate(content):
                new_part = dict(part)
                new_content.append(new_part)
                if new_part.get("type") == "text":
                    refs.append(
                        {
                            "msg_idx": msg_idx,
                            "part_idx": part_idx,
                            "role": role,
                            "text": str(new_part.get("text", "")),
                        }
                    )
            copied.append({**msg, "content": new_content})
        elif isinstance(content, str):
            refs.append(
                {
                    "msg_idx": msg_idx,
                    "part_idx": None,
                    "role": role,
                    "text": content,
                }
            )
            copied.append({**msg, "content": content})
        else:
            copied.append(msg)

    total = sum(len(ref["text"]) for ref in refs)
    if total <= max_text_chars:
        return messages

    latest_user_idx = max(
        (idx for idx, msg in enumerate(copied) if msg.get("role") == "user"),
        default=-1,
    )
    allocations: dict[int, int] = {}
    latest_refs: list[tuple[int, dict[str, Any]]] = []
    protected_total = 0

    for ref_idx, ref in enumerate(refs):
        text_len = len(ref["text"])
        role = ref["role"]
        if role == "user" and ref["msg_idx"] == latest_user_idx:
            latest_refs.append((ref_idx, ref))
            continue
        if role == "system":
            cap = min(text_len, 6000)
        elif role == "assistant":
            cap = min(text_len, 8000)
        elif role == "user":
            cap = min(text_len, DEFAULT_HISTORY_TEXT_PREVIEW_CHARS)
        else:
            cap = min(text_len, 1000)
        allocations[ref_idx] = cap
        protected_total += cap

    if protected_total > max_text_chars and protected_total > 0:
        scale = max_text_chars / float(protected_total)
        for ref_idx, cap in list(allocations.items()):
            allocations[ref_idx] = max(0, int(cap * scale))
    else:
        remaining = max(0, max_text_chars - protected_total)
        latest_total = sum(len(ref["text"]) for _ref_idx, ref in latest_refs)
        for ref_idx, ref in latest_refs:
            if latest_total <= 0:
                allocations[ref_idx] = 0
            else:
                allocations[ref_idx] = min(
                    len(ref["text"]),
                    int(remaining * (len(ref["text"]) / latest_total)),
                )

    # Hand any rounding slack to the largest current-user text part.
    allocated_total = sum(allocations.values())
    slack = max_text_chars - allocated_total
    if slack > 0 and latest_refs:
        largest_ref_idx = max(latest_refs, key=lambda item: len(item[1]["text"]))[0]
        allocations[largest_ref_idx] = allocations.get(largest_ref_idx, 0) + min(
            slack,
            len(refs[largest_ref_idx]["text"]),
        )

    for ref_idx, ref in enumerate(refs):
        new_text = _compact_text_value(ref["text"], allocations.get(ref_idx, 0))
        msg_idx = ref["msg_idx"]
        part_idx = ref["part_idx"]
        if part_idx is None:
            copied[msg_idx]["content"] = new_text
        else:
            copied[msg_idx]["content"][part_idx]["text"] = new_text

    return copied


def prepare_messages_for_api(
    messages: list[dict[str, Any]],
    model: str = "",
    compress_video_mb: float = 0,
    extract_video_fps: float = 0,
    max_total_images: int = 0,
    max_image_side: int = 0,
    image_jpeg_quality: int = DEFAULT_IMAGE_JPEG_QUALITY,
    force_jpeg: bool = False,
    max_text_chars: int = 0,
) -> list[dict[str, Any]]:
    """Deep-copy messages and inline local image/video files for API usage."""
    use_video_url = _is_doubao_model(model)
    image_count = 0
    video_url_count = 0
    out = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            out.append(msg)
            continue

        new_parts = []
        for part in content:
            part_type = part.get("type", "")
            if part_type == "image_url":
                url_obj = part.get("image_url", {})
                src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                if src and (src.startswith("/") or src.startswith("file://")):
                    local_path = src.replace("file://", "")
                    if os.path.isfile(local_path):
                        if max_image_side > 0:
                            local_path = _downscale_image_if_needed(
                                local_path,
                                max_side=max_image_side,
                                jpeg_quality=image_jpeg_quality,
                                force_jpeg=force_jpeg,
                            )
                        new_parts.append(
                            {"type": "image_url", "image_url": {"url": _file_to_data_uri(local_path)}}
                        )
                        image_count += 1
                        continue
                if max_image_side > 0 and isinstance(src, str) and src.startswith("data:image/"):
                    shrunk = _downscale_data_uri_if_needed(
                        src,
                        max_side=max_image_side,
                        jpeg_quality=image_jpeg_quality,
                        force_jpeg=force_jpeg,
                    )
                    new_parts.append({"type": "image_url", "image_url": {"url": shrunk}})
                    image_count += 1
                    continue
                new_parts.append(part)
                image_count += 1
            elif part_type == "video":
                src = part.get("video", {})
                if isinstance(src, dict):
                    src = src.get("url", "")

                if use_video_url:
                    if isinstance(src, str) and (src.startswith("/") or src.startswith("file://")):
                        local_path = src.replace("file://", "")
                        if os.path.isfile(local_path):
                            if video_url_count < DEFAULT_DOUBAO_VIDEO_LIMIT:
                                if compress_video_mb > 0:
                                    local_path = _compress_video(local_path, compress_video_mb)
                                new_parts.append(
                                    {"type": "video_url", "video_url": {"url": _file_to_data_uri(local_path)}}
                                )
                                video_url_count += 1
                                continue
                            frames = _extract_video_frames(
                                local_path,
                                max(extract_video_fps, 0.2),
                                max_frames=8,
                                max_size=max_image_side or DEFAULT_IMAGE_MAX_SIDE,
                            )
                            if not frames and compress_video_mb > 0:
                                local_path = _compress_video(local_path, compress_video_mb)
                                frames = _extract_video_frames(
                                    local_path,
                                    max(extract_video_fps, 0.2),
                                    max_frames=8,
                                    max_size=max_image_side or DEFAULT_IMAGE_MAX_SIDE,
                                )
                            if frames:
                                for frame_b64 in frames:
                                    new_parts.append(
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/jpeg;base64,{frame_b64}"
                                            },
                                        }
                                    )
                                image_count += len(frames)
                                continue
                            new_parts.append(
                                {"type": "text", "text": "[Video converted to frames failed]"}
                            )
                            continue
                    if (
                        isinstance(src, str)
                        and src.startswith("http")
                        and video_url_count < DEFAULT_DOUBAO_VIDEO_LIMIT
                    ):
                        new_parts.append({"type": "video_url", "video_url": {"url": src}})
                        video_url_count += 1
                    else:
                        new_parts.append(
                            {"type": "text", "text": "[Video omitted: Doubao video_url limit exceeded]"}
                        )
                else:
                    if isinstance(src, str) and (src.startswith("/") or src.startswith("file://")):
                        local_path = src.replace("file://", "")
                        if os.path.isfile(local_path):
                            if extract_video_fps > 0:
                                budget = 50
                                frames: list[str] = []
                                if budget > 0:
                                    frames = _extract_video_frames(
                                        local_path,
                                        extract_video_fps,
                                        max_frames=budget,
                                        max_size=max_image_side or DEFAULT_IMAGE_MAX_SIDE,
                                    )
                                if not frames and budget > 0 and compress_video_mb > 0:
                                    compressed_path = _compress_video(local_path, compress_video_mb)
                                    frames = _extract_video_frames(
                                        compressed_path,
                                        extract_video_fps,
                                        max_frames=budget,
                                        max_size=max_image_side or DEFAULT_IMAGE_MAX_SIDE,
                                    )
                                if frames:
                                    for frame_b64 in frames:
                                        new_parts.append(
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/jpeg;base64,{frame_b64}"
                                                },
                                            }
                                        )
                                    image_count += len(frames)
                                    continue
                            if compress_video_mb > 0:
                                compressed_path = _compress_video(local_path, compress_video_mb)
                                fallback_frames = _extract_video_frames(
                                    compressed_path,
                                    max(extract_video_fps, 0.2),
                                    max_frames=8,
                                    max_size=max_image_side or DEFAULT_IMAGE_MAX_SIDE,
                                )
                                if fallback_frames:
                                    for frame_b64 in fallback_frames:
                                        new_parts.append(
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/jpeg;base64,{frame_b64}"
                                                },
                                            }
                                        )
                                    image_count += len(fallback_frames)
                                    continue
                            new_parts.append({"type": "text", "text": "[Video omitted: frame extraction failed]"})
                            continue
                    new_parts.append(part)
            elif part_type == "video_url":
                new_parts.append(part)
            else:
                new_parts.append(part)

        out.append({**msg, "content": new_parts})
    if max_total_images > 0:
        out = _merge_images_to_limit(
            out,
            max_total_images=max_total_images,
            max_image_side=max_image_side or DEFAULT_IMAGE_MAX_SIDE,
            image_jpeg_quality=image_jpeg_quality,
        )
    if max_text_chars > 0:
        out = _compact_text_to_budget(out, max_text_chars)
    out = _normalize_gemini_system_messages(out, model)
    return out


def _get_image_part_src(part: dict[str, Any]) -> str:
    url_obj = part.get("image_url", {})
    return url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)


def _copy_messages_with_list_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            copied.append({**msg, "content": [dict(part) for part in content]})
        else:
            copied.append(msg)
    return copied


def _collect_image_slots(messages: list[dict[str, Any]]) -> list[tuple[int, int]]:
    slots: list[tuple[int, int]] = []
    for msg_idx, msg in enumerate(messages):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part_idx, part in enumerate(content):
            if part.get("type") == "image_url":
                slots.append((msg_idx, part_idx))
    return slots


def _image_part_to_image(part: dict[str, Any]) -> Any | None:
    src = _get_image_part_src(part)
    if not src.startswith("data:image/"):
        return None
    try:
        import io
        from PIL import Image

        _header, b64data = src.split(",", 1)
        raw = base64.b64decode(b64data)
        with Image.open(io.BytesIO(raw)) as img:
            return img.convert("RGB")
    except Exception:
        return None


def _merge_two_image_parts(
    first: dict[str, Any],
    second: dict[str, Any],
    max_image_side: int,
    image_jpeg_quality: int,
) -> dict[str, Any] | None:
    try:
        from PIL import Image
    except Exception:
        return None

    first_img = _image_part_to_image(first)
    second_img = _image_part_to_image(second)
    if first_img is None or second_img is None:
        return None

    gutter = max(4, min(max(first_img.size + second_img.size) // 100, 16))
    side_by_side_size = (
        first_img.width + second_img.width + gutter,
        max(first_img.height, second_img.height),
    )
    vertical_size = (
        max(first_img.width, second_img.width),
        first_img.height + second_img.height + gutter,
    )
    use_side_by_side = max(side_by_side_size) <= max(vertical_size)

    if use_side_by_side:
        canvas_size = side_by_side_size
        offsets = [(0, 0), (first_img.width + gutter, 0)]
    else:
        canvas_size = vertical_size
        offsets = [(0, 0), (0, first_img.height + gutter)]

    canvas = Image.new("RGB", canvas_size, "white")
    canvas.paste(first_img, offsets[0])
    canvas.paste(second_img, offsets[1])
    canvas = _resize_image_for_limits(canvas, max_side=max_image_side)
    data_uri = _encode_image_to_data_uri(
        canvas,
        "image/jpeg",
        jpeg_quality=image_jpeg_quality,
        force_jpeg=True,
    )
    return {"type": "image_url", "image_url": {"url": data_uri}}


def _merge_images_to_limit(
    messages: list[dict[str, Any]],
    max_total_images: int,
    max_image_side: int,
    image_jpeg_quality: int,
) -> list[dict[str, Any]]:
    if max_total_images <= 0:
        return messages

    merged_messages = _copy_messages_with_list_content(messages)
    while True:
        image_slots = _collect_image_slots(merged_messages)
        if len(image_slots) <= max_total_images:
            return merged_messages

        mergeable_slots = [
            slot
            for slot in image_slots
            if _get_image_part_src(merged_messages[slot[0]]["content"][slot[1]]).startswith("data:image/")
        ]
        pair_count = min(len(image_slots) - max_total_images, len(mergeable_slots) // 2)
        if pair_count <= 0:
            return merged_messages

        pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for pair_idx in range(pair_count):
            first_slot = mergeable_slots[pair_idx * 2]
            second_slot = mergeable_slots[pair_idx * 2 + 1]
            pairs.append((first_slot, second_slot))

        if not pairs:
            return merged_messages

        made_progress = False
        for first_slot, second_slot in sorted(
            pairs,
            key=lambda item: (item[1][0], item[1][1]),
            reverse=True,
        ):
            first_msg_idx, first_part_idx = first_slot
            second_msg_idx, second_part_idx = second_slot
            first_part = merged_messages[first_msg_idx]["content"][first_part_idx]
            second_part = merged_messages[second_msg_idx]["content"][second_part_idx]
            merged_part = _merge_two_image_parts(
                first_part,
                second_part,
                max_image_side=max_image_side,
                image_jpeg_quality=image_jpeg_quality,
            )
            if merged_part is None:
                continue
            merged_messages[first_msg_idx]["content"][first_part_idx] = merged_part
            del merged_messages[second_msg_idx]["content"][second_part_idx]
            made_progress = True
        if not made_progress:
            return merged_messages


def _normalize_gemini_system_messages(
    messages: list[dict[str, Any]],
    model: str,
) -> list[dict[str, Any]]:
    if "gemini" not in model.lower():
        return messages

    normalized: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "system" or not isinstance(msg.get("content"), list):
            normalized.append(msg)
            continue

        text_parts = [
            str(part.get("text", ""))
            for part in msg["content"]
            if part.get("type") == "text" and str(part.get("text", "")).strip()
        ]
        media_parts = [part for part in msg["content"] if part.get("type") != "text"]
        normalized.append({**msg, "content": "\n".join(text_parts)})
        if media_parts:
            normalized.append({"role": "user", "content": media_parts})
    return normalized


def _estimate_api_messages_size(messages: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    size_bytes = 0
    image_count = 0
    invalid_image_mimes: list[str] = []

    for msg in messages:
        role = str(msg.get("role", ""))
        size_bytes += len(role)
        content = msg.get("content")
        if isinstance(content, str):
            size_bytes += len(content)
            continue
        if not isinstance(content, list):
            size_bytes += len(str(content))
            continue

        for part in content:
            part_type = part.get("type", "")
            size_bytes += len(part_type)
            if part_type == "text":
                size_bytes += len(str(part.get("text", "")))
            elif part_type == "image_url":
                image_count += 1
                url_obj = part.get("image_url", {})
                src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                size_bytes += len(src)
                if src.startswith("data:"):
                    mime = src.split(",", 1)[0].split(":", 1)[-1].split(";", 1)[0]
                    if not mime.startswith("image/"):
                        invalid_image_mimes.append(mime or "unknown")
            elif part_type == "video_url":
                url_obj = part.get("video_url", {})
                src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                size_bytes += len(src)
            elif part_type == "video":
                video_obj = part.get("video", {})
                src = video_obj.get("url", "") if isinstance(video_obj, dict) else str(video_obj)
                size_bytes += len(src)
            else:
                try:
                    size_bytes += len(json.dumps(part, ensure_ascii=False))
                except Exception:
                    size_bytes += len(str(part))

    return size_bytes, image_count, invalid_image_mimes


def _get_model_image_limit(model: str) -> int | None:
    if _is_claude_model(model):
        return 100
    if _is_gemini_native_model(model) or _is_doubao_model(model):
        return None
    return 50


def _count_image_parts(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        total += sum(1 for part in content if part.get("type") == "image_url")
    return total


def _image_limit_for_profile(model: str, profile_idx: int, source_image_count: int) -> int:
    if _is_doubao_model(model):
        if source_image_count <= 0 or profile_idx <= 0:
            return 0
        limit = DEFAULT_DOUBAO_IMAGE_MERGE_LIMITS[
            min(profile_idx - 1, len(DEFAULT_DOUBAO_IMAGE_MERGE_LIMITS) - 1)
        ]
        return limit if source_image_count > limit else 0
    if not _is_gemini_native_model(model) and not _is_claude_model(model):
        limit = DEFAULT_OPENAI_IMAGE_MERGE_LIMITS[
            min(profile_idx, len(DEFAULT_OPENAI_IMAGE_MERGE_LIMITS) - 1)
        ]
        return limit
    return _get_model_image_limit(model) or 0


def _text_budget_levels_for_model(model: str, source_text_chars: int) -> list[int]:
    if source_text_chars <= DEFAULT_TEXT_COMPACT_MIN_CHARS:
        return []
    if _is_doubao_model(model):
        levels = (600000, 400000, 250000, 160000, 100000)
    elif not _is_gemini_native_model(model) and not _is_claude_model(model):
        levels = (1200000, 1000000, 800000, 600000, 450000, 320000, 240000)
    else:
        levels = (1200000, 900000, 700000, 500000, 350000)
    return [level for level in levels if source_text_chars > level]


def _has_history_user_turns(messages: list[dict[str, Any]]) -> bool:
    user_count = sum(
        1
        for msg in messages
        if isinstance(msg, dict) and msg.get("role") == "user"
    )
    return user_count > 1


def _append_text_compaction_profiles(
    profiles: list[dict[str, Any]],
    model: str,
    source_text_chars: int,
) -> list[dict[str, Any]]:
    if not profiles:
        return profiles
    for budget in _text_budget_levels_for_model(model, source_text_chars):
        profile = dict(profiles[-1])
        profile["max_text_chars"] = budget
        profiles.append(profile)
    return profiles


def _append_smart_history_profiles(
    profiles: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not profiles or not _has_history_user_turns(messages):
        return profiles
    profile = dict(profiles[-1])
    profile["history_media_policy"] = "smart"
    profile["degraded_fallback"] = "smart-history"
    profiles.append(profile)
    return profiles


def _build_media_profiles(model: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_video = _has_video_content(messages)
    use_frames = has_video and not _is_doubao_model(model)
    source_image_count = _count_image_parts(messages)
    source_text_chars = _count_text_chars(messages)

    image_profiles = [
        (DEFAULT_IMAGE_MAX_SIDE, DEFAULT_IMAGE_JPEG_QUALITY, False),
        (1600, 82, True),
        (1280, 72, True),
        (1024, 62, True),
        (768, 52, True),
        (512, 45, True),
        (384, 38, True),
        (256, 35, True),
        (192, 30, True),
        (160, 28, True),
        (128, 25, True),
        (96, 23, True),
    ]
    profiles: list[dict[str, Any]] = []

    if use_frames:
        fps_levels = [2.0, 1.0, 0.5, 0.25, 0.2]
        for idx, fps in enumerate(fps_levels):
            side, quality, force_jpeg = image_profiles[min(idx, len(image_profiles) - 1)]
            profiles.append(
                {
                    "_profile_base_index": idx,
                    "compress_video_mb": 0,
                    "extract_video_fps": fps,
                    "max_total_images": _image_limit_for_profile(model, idx, source_image_count),
                    "max_image_side": side,
                    "image_jpeg_quality": quality,
                    "force_jpeg": force_jpeg,
                }
            )
        for idx, (side, quality, force_jpeg) in enumerate(image_profiles[3:], start=len(fps_levels)):
            profiles.append(
                {
                    "_profile_base_index": idx,
                    "compress_video_mb": 10,
                    "extract_video_fps": 0.2,
                    "max_total_images": _image_limit_for_profile(model, idx, source_image_count),
                    "max_image_side": side,
                    "image_jpeg_quality": quality,
                    "force_jpeg": force_jpeg,
                }
            )
        profiles = _append_text_compaction_profiles(profiles, model, source_text_chars)
        return _append_smart_history_profiles(profiles, messages)

    compress_levels = [0, 10, 5, 2, 1, 0.5]
    for idx, mb in enumerate(compress_levels):
        side, quality, force_jpeg = image_profiles[min(idx, len(image_profiles) - 1)]
        profiles.append(
            {
                "_profile_base_index": idx,
                "compress_video_mb": mb if has_video else 0,
                "extract_video_fps": 0,
                "max_total_images": _image_limit_for_profile(model, idx, source_image_count),
                "max_image_side": side,
                "image_jpeg_quality": quality,
                "force_jpeg": force_jpeg,
            }
        )
    for idx, (side, quality, force_jpeg) in enumerate(
        image_profiles[len(compress_levels):],
        start=len(compress_levels),
    ):
        profiles.append(
            {
                "_profile_base_index": idx,
                "compress_video_mb": compress_levels[-1] if has_video else 0,
                "extract_video_fps": 0,
                "max_total_images": _image_limit_for_profile(model, idx, source_image_count),
                "max_image_side": side,
                "image_jpeg_quality": quality,
                "force_jpeg": force_jpeg,
            }
        )
    profiles = _append_text_compaction_profiles(profiles, model, source_text_chars)
    return _append_smart_history_profiles(profiles, messages)


def _messages_for_history_media_policy(
    messages: list[dict[str, Any]],
    policy: str,
) -> list[dict[str, Any]]:
    normalized = (policy or "full").strip().lower()
    if normalized == "full":
        return messages
    request_item = copy_item_for_history_media_policy({"messages": messages}, normalized)
    request_messages = request_item.get("messages", messages)
    return request_messages if isinstance(request_messages, list) else messages


def _prepare_messages_for_profile(
    messages: list[dict[str, Any]],
    model: str,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    profile_messages = _messages_for_history_media_policy(
        messages,
        str(profile.get("history_media_policy", "full")),
    )
    return prepare_messages_for_api(
        profile_messages,
        model,
        compress_video_mb=float(profile.get("compress_video_mb", 0)),
        extract_video_fps=float(profile.get("extract_video_fps", 0)),
        max_total_images=int(profile.get("max_total_images", 0)),
        max_image_side=int(profile.get("max_image_side", 0)),
        image_jpeg_quality=int(profile.get("image_jpeg_quality", DEFAULT_IMAGE_JPEG_QUALITY)),
        force_jpeg=bool(profile.get("force_jpeg", False)),
        max_text_chars=int(profile.get("max_text_chars", 0)),
    )


def _describe_media_profile(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    if profile.get("degraded_fallback"):
        parts.append(f"degraded={profile['degraded_fallback']}")
    history_policy = str(profile.get("history_media_policy", "full"))
    if history_policy and history_policy != "full":
        parts.append(f"history={history_policy}")
    if profile.get("extract_video_fps"):
        parts.append(f"video_frames={profile['extract_video_fps']}fps")
    if profile.get("compress_video_mb"):
        parts.append(f"video<={profile['compress_video_mb']}MB")
    if profile.get("max_image_side"):
        parts.append(f"image<={profile['max_image_side']}px")
    if profile.get("image_jpeg_quality"):
        parts.append(f"jpeg_q={profile['image_jpeg_quality']}")
    if profile.get("force_jpeg"):
        parts.append("force_jpeg")
    if profile.get("max_total_images"):
        parts.append(f"images<={profile['max_total_images']}")
    if profile.get("max_text_chars"):
        parts.append(f"text<={profile['max_text_chars']}chars")
    return ", ".join(parts) if parts else "default_media_profile"


def _payload_soft_limit_for_model(model: str) -> int:
    if _is_doubao_model(model):
        return DEFAULT_DOUBAO_APPROX_PAYLOAD_LIMIT_BYTES
    if not _is_gemini_native_model(model) and not _is_claude_model(model):
        return DEFAULT_GPT_APPROX_PAYLOAD_LIMIT_BYTES
    return DEFAULT_APPROX_PAYLOAD_LIMIT_BYTES


def _preflight_validate_api_messages(
    api_messages: list[dict[str, Any]],
    model: str,
    approx_payload_limit: int | None = None,
) -> tuple[str | None, bool]:
    if approx_payload_limit is None:
        approx_payload_limit = _payload_soft_limit_for_model(model)
    approx_size, image_count, invalid_image_mimes = _estimate_api_messages_size(api_messages)
    image_limit = _get_model_image_limit(model)

    if invalid_image_mimes:
        mimes = ", ".join(sorted(set(invalid_image_mimes)))
        return (
            f"Preflight failed: prepared image_url contains non-image mime type(s): {mimes}.",
            True,
        )
    if image_limit and image_count > image_limit:
        return (
            f"Preflight failed: prepared request contains {image_count} images, exceeding model limit {image_limit}.",
            False,
        )
    if approx_size > approx_payload_limit:
        return (
            f"Preflight failed: estimated payload {approx_size} bytes exceeds soft limit {approx_payload_limit}.",
            True,
        )
    return None, False


def _is_rate_limit_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        "too many requests" in text
        or "rate limit" in text
        or "request limit for seconds" in text
        or "request limit for minute" in text
        or "error code: 429" in text
        or '"code": 429' in text
        or "'code': 429" in text
        or "resource_exhausted" in text
    )


def _is_too_large_error(error: Any) -> bool:
    text = str(error).lower()
    keywords = (
        "too large",
        "entity too large",
        "payload too large",
        "request entity too large",
        "context_length_exceeded",
        "input tokens exceed",
        "input token count",
        "max message tokens",
        "image_too_large",
        "image exceeds 5 mb",
        "image exceeds",
    )
    return any(keyword in text for keyword in keywords)


def _is_context_length_error(error: Any) -> bool:
    text = str(error).lower()
    keywords = (
        "context_length_exceeded",
        "input tokens exceed",
        "input token count",
        "max message tokens",
        "maximum context length",
        "context length",
    )
    return any(keyword in text for keyword in keywords)


def _insert_next_text_compaction_profile(
    profiles: list[dict[str, Any]],
    profile_idx: int,
    model: str,
    messages: list[dict[str, Any]],
) -> int | None:
    budgets = _text_budget_levels_for_model(model, _count_text_chars(messages))
    if not budgets:
        return None

    current_budget = int(profiles[profile_idx].get("max_text_chars", 0))
    next_budget = None
    if current_budget <= 0:
        next_budget = budgets[0]
    else:
        for budget in budgets:
            if budget < current_budget:
                next_budget = budget
                break
    if next_budget is None:
        return None

    profile = dict(profiles[profile_idx])
    profile["max_text_chars"] = next_budget
    profiles.insert(profile_idx + 1, profile)
    return profile_idx + 1


def _insert_smart_history_profile(
    profiles: list[dict[str, Any]],
    profile_idx: int,
    messages: list[dict[str, Any]],
) -> int | None:
    if not _has_history_user_turns(messages):
        return None
    current_policy = str(profiles[profile_idx].get("history_media_policy", "full"))
    if current_policy == "smart":
        return None

    profile = dict(profiles[profile_idx])
    profile["history_media_policy"] = "smart"
    profile["degraded_fallback"] = "smart-history"
    profiles.insert(profile_idx + 1, profile)
    return profile_idx + 1


def _next_sequential_profile_index(
    profiles: list[dict[str, Any]],
    profile_idx: int,
) -> int | None:
    if profile_idx + 1 >= len(profiles):
        return None

    current = profiles[profile_idx]
    current_key = _profile_transform_key(current)
    current_base_index = int(current.get("_profile_base_index", profile_idx))

    for candidate_idx in range(profile_idx + 1, len(profiles)):
        candidate = profiles[candidate_idx]
        profile = _profile_with_preserved_reductions(current, candidate)
        profile_base_index = int(profile.get("_profile_base_index", candidate_idx))
        if profile_base_index < current_base_index:
            continue
        if _profile_transform_key(profile) == current_key:
            continue
        if _profile_transform_key(profile) == _profile_transform_key(candidate):
            return candidate_idx
        profiles.insert(profile_idx + 1, profile)
        return profile_idx + 1

    return None


def _profile_transform_key(profile: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(profile.get("history_media_policy", "full")),
        float(profile.get("compress_video_mb", 0)),
        float(profile.get("extract_video_fps", 0)),
        int(profile.get("max_total_images", 0)),
        int(profile.get("max_image_side", 0)),
        int(profile.get("image_jpeg_quality", DEFAULT_IMAGE_JPEG_QUALITY)),
        bool(profile.get("force_jpeg", False)),
        int(profile.get("max_text_chars", 0)),
    )


def _profile_with_preserved_reductions(
    current: dict[str, Any],
    next_profile: dict[str, Any],
) -> dict[str, Any]:
    current_text_budget = int(current.get("max_text_chars", 0))
    next_text_budget = int(next_profile.get("max_text_chars", 0))
    current_history_policy = str(current.get("history_media_policy", "full"))
    next_history_policy = str(next_profile.get("history_media_policy", "full"))

    needs_preserve = (
        (current_text_budget > 0 and (next_text_budget <= 0 or next_text_budget > current_text_budget))
        or (current_history_policy == "smart" and next_history_policy != "smart")
    )
    if not needs_preserve:
        return next_profile

    profile = dict(next_profile)
    if current_text_budget > 0:
        profile["max_text_chars"] = (
            current_text_budget
            if next_text_budget <= 0
            else min(current_text_budget, next_text_budget)
        )
    if current_history_policy == "smart":
        profile["history_media_policy"] = "smart"
        profile["degraded_fallback"] = "smart-history"
    return profile


def _next_reduction_profile_index(
    profiles: list[dict[str, Any]],
    profile_idx: int,
    model: str,
    messages: list[dict[str, Any]],
    error: Any,
) -> int | None:
    if _is_context_length_error(error):
        text_idx = _insert_next_text_compaction_profile(
            profiles,
            profile_idx,
            model,
            messages,
        )
        if text_idx is not None:
            return text_idx
        smart_idx = _insert_smart_history_profile(profiles, profile_idx, messages)
        if smart_idx is not None:
            return smart_idx
        return _next_sequential_profile_index(profiles, profile_idx)

    next_idx = _next_sequential_profile_index(profiles, profile_idx)
    if next_idx is not None:
        return next_idx
    return _insert_smart_history_profile(profiles, profile_idx, messages)


def _is_too_many_images_error(error: Any) -> bool:
    text = str(error).lower()
    return "too many images in request" in text or "too many images and documents" in text


def _is_invalid_image_media_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        ("invalid image url" in text and "unsupported mime type" in text)
        or (
            "image was specified using" in text
            and "appears to be" in text
        )
    )


def _is_sensitive_content_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        "input_text_sensitive_content_detected" in text
        or "sensitive_content_detected" in text
        or "input text may contain sensitive information" in text
    )


def _is_non_retryable_request_error(error: Any) -> bool:
    return (
        _is_too_many_images_error(error)
        or _is_invalid_image_media_error(error)
        or _is_sensitive_content_error(error)
    )


def _non_retryable_request_reason(error: Any) -> str:
    if _is_sensitive_content_error(error):
        return "sensitive_content"
    return "request_validation"




def _is_timeout_error(error: Any) -> bool:
    if isinstance(error, (_requests.exceptions.Timeout, TimeoutError)):
        return True
    text = str(error).lower()
    return (
        "read timed out" in text
        or "read timeout" in text
        or "connection timed out" in text
        or "timed out" in text and "timeout" in text
    )


def _timeout_retry_limit_for_model(model: str) -> int:
    if _is_claude_model(model):
        return max(1, DEFAULT_CLAUDE_TIMEOUT_RETRIES)
    return max(1, DEFAULT_API_TIMEOUT_RETRIES)


def _compute_retry_delay(base_delay: int, attempt_no: int) -> float:
    return min(base_delay * (2 ** max(attempt_no - 1, 0)), 60)


def _has_video_content(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "video":
                return True
    return False


def call_openai_api(
    client: OpenAI,
    messages: list[dict[str, Any]],
    model: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = 3,
    attempt_logger: AttemptLogger | None = None,
) -> tuple[str | None, str | None, str]:
    """Returns (response_text, error, compress_info)."""
    profiles = _build_media_profiles(model, messages)
    profile_idx = 0
    compress_info = ""
    retries = 0
    empty_text_retries = 0
    timeout_retries = 0
    timeout_limit = min(max(1, max_retries), _timeout_retry_limit_for_model(model))
    last_error = None

    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])

    while retries < max_retries:
        preflight_error, should_reduce_payload = _preflight_validate_api_messages(api_messages, model)
        if preflight_error:
            next_profile_idx = _next_reduction_profile_index(
                profiles,
                profile_idx,
                model,
                messages,
                preflight_error,
            )
            if should_reduce_payload and next_profile_idx is not None:
                profile_idx = next_profile_idx
                compress_info = _describe_media_profile(profiles[profile_idx])
                _log_attempt_event(
                    attempt_logger,
                    f"phase=preflight attempt={retries + 1}/{max_retries} "
                    f"error={preflight_error} action=retry fallback={compress_info}",
                )
                api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                continue
            _log_attempt_event(
                attempt_logger,
                f"phase=preflight attempt={retries + 1}/{max_retries} "
                f"error={preflight_error} action=give_up non_retryable=preflight",
            )
            return None, preflight_error, compress_info
        try:
            response = client.chat.completions.create(
                model=model,
                messages=api_messages,
                stream=True,
            )
            chunks = []
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    if isinstance(content, dict):
                        content = content.get("text", str(content))
                    chunks.append(content)
            return "".join(chunks), None, compress_info
        except Exception as exc:
            last_error = exc
            attempt_no = retries + 1
            if _is_timeout_error(exc):
                timeout_retries += 1
                if timeout_retries >= timeout_limit:
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=give_up non_retryable=timeout "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    return None, str(exc), compress_info
                next_profile_idx = _next_reduction_profile_index(
                    profiles,
                    profile_idx,
                    model,
                    messages,
                    exc,
                )
                if next_profile_idx is not None:
                    profile_idx = next_profile_idx
                    compress_info = _describe_media_profile(profiles[profile_idx])
                    retries += 1
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry fallback={compress_info} "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                    continue
                retries += 1
                sleep_seconds = retry_delay
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action={'retry' if retries < max_retries else 'give_up'} "
                    f"timeout_attempts={timeout_retries}/{timeout_limit}"
                    f"{f' backoff={sleep_seconds}s' if retries < max_retries else ''}",
                )
                if retries < max_retries:
                    time.sleep(sleep_seconds)
                continue
            if _is_too_large_error(exc) or _is_invalid_image_media_error(exc):
                next_profile_idx = _next_reduction_profile_index(
                    profiles,
                    profile_idx,
                    model,
                    messages,
                    exc,
                )
                if next_profile_idx is not None:
                    profile_idx = next_profile_idx
                    compress_info = _describe_media_profile(profiles[profile_idx])
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry fallback={compress_info}",
                    )
                    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                    continue
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable=payload",
                )
                return None, str(exc), compress_info
            if _is_non_retryable_request_error(exc):
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable=request_validation",
                )
                return None, str(exc), compress_info
            retries += 1
            sleep_seconds = _compute_retry_delay(retry_delay, attempt_no) if _is_rate_limit_error(exc) else retry_delay
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt_no}/{max_retries} "
                f"error={str(exc)} action={'retry' if retries < max_retries else 'give_up'}"
                f"{f' backoff={sleep_seconds}s' if retries < max_retries else ''}",
            )
            if retries < max_retries:
                time.sleep(sleep_seconds)

    return None, str(last_error) if last_error else "Unknown error", compress_info


def call_gemini_native_api(
    messages: list[dict[str, Any]],
    model: str,
    base_url: str,
    api_key: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = 3,
    attempt_logger: AttemptLogger | None = None,
) -> tuple[str | None, str | None, str]:
    """Call Gemini-native API and return (response_text, error, compress_info)."""
    profiles = _build_media_profiles(model, messages)
    profile_idx = 0
    compress_info = ""
    retries = 0
    timeout_retries = 0
    timeout_limit = min(max(1, max_retries), _timeout_retry_limit_for_model(model))
    last_error = None

    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])

    while retries < max_retries:
        preflight_error, should_reduce_payload = _preflight_validate_api_messages(api_messages, model)
        if preflight_error:
            next_profile_idx = _next_reduction_profile_index(
                profiles,
                profile_idx,
                model,
                messages,
                preflight_error,
            )
            if should_reduce_payload and next_profile_idx is not None:
                profile_idx = next_profile_idx
                compress_info = _describe_media_profile(profiles[profile_idx])
                _log_attempt_event(
                    attempt_logger,
                    f"phase=preflight attempt={retries + 1}/{max_retries} "
                    f"error={preflight_error} action=retry fallback={compress_info}",
                )
                api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                continue
            _log_attempt_event(
                attempt_logger,
                f"phase=preflight attempt={retries + 1}/{max_retries} "
                f"error={preflight_error} action=give_up non_retryable=preflight",
            )
            return None, preflight_error, compress_info
        try:
            contents = _messages_to_gemini_contents(api_messages)
            payload: dict[str, Any] = {
                "model": _get_gemini_api_model(model),
                "stream": False,
                "contents": contents,
            }
            generation_config = _get_gemini_generation_config(model)
            if generation_config:
                payload["generation_config"] = generation_config

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            resp = _requests.post(
                _gemini_api_url(base_url),
                headers=headers,
                json=payload,
                timeout=DEFAULT_API_TIMEOUT,
            )
            resp.raise_for_status()
            resp_json = resp.json()
            parts = resp_json["candidates"][0]["content"]["parts"]
            text_parts = [part["text"] for part in parts if "text" in part and not part.get("thought")]
            text = "\n".join(text_parts) if text_parts else parts[0].get("text", "")
            return text, None, compress_info
        except Exception as exc:
            last_error = exc
            attempt_no = retries + 1
            if _is_timeout_error(exc):
                timeout_retries += 1
                if timeout_retries >= timeout_limit:
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=give_up non_retryable=timeout "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    return None, str(exc), compress_info
                next_profile_idx = _next_reduction_profile_index(
                    profiles,
                    profile_idx,
                    model,
                    messages,
                    exc,
                )
                if next_profile_idx is not None:
                    profile_idx = next_profile_idx
                    compress_info = _describe_media_profile(profiles[profile_idx])
                    retries += 1
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry fallback={compress_info} "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                    continue
                retries += 1
                sleep_seconds = retry_delay
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action={'retry' if retries < max_retries else 'give_up'} "
                    f"timeout_attempts={timeout_retries}/{timeout_limit}"
                    f"{f' backoff={sleep_seconds}s' if retries < max_retries else ''}",
                )
                if retries < max_retries:
                    time.sleep(sleep_seconds)
                continue
            if _is_too_large_error(exc) or _is_invalid_image_media_error(exc):
                next_profile_idx = _next_reduction_profile_index(
                    profiles,
                    profile_idx,
                    model,
                    messages,
                    exc,
                )
                if next_profile_idx is not None:
                    profile_idx = next_profile_idx
                    compress_info = _describe_media_profile(profiles[profile_idx])
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry fallback={compress_info}",
                    )
                    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                    continue
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable=payload",
                )
                return None, str(exc), compress_info
            if _is_non_retryable_request_error(exc):
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable=request_validation",
                )
                return None, str(exc), compress_info
            retries += 1
            sleep_seconds = _compute_retry_delay(retry_delay, attempt_no) if _is_rate_limit_error(exc) else retry_delay
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt_no}/{max_retries} "
                f"error={str(exc)} action={'retry' if retries < max_retries else 'give_up'}"
                f"{f' backoff={sleep_seconds}s' if retries < max_retries else ''}",
            )
            if retries < max_retries:
                time.sleep(sleep_seconds)

    return None, str(last_error) if last_error else "Unknown error", compress_info


def call_gemini_native_judge_api(
    model: str,
    rubrics_text: str,
    model_output: str,
    base_url: str,
    api_key: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = 3,
    attempt_logger: AttemptLogger | None = None,
) -> str | None:
    """Judge API using Gemini-native format."""
    prompt = GRADING_PROMPT_TEMPLATE.format(
        rubrics_text=rubrics_text,
        model_output=model_output,
    )
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    timeout_retries = 0
    timeout_limit = min(max(1, max_retries), _timeout_retry_limit_for_model(model))

    for attempt in range(max_retries):
        try:
            payload: dict[str, Any] = {
                "model": _get_gemini_api_model(model),
                "stream": False,
                "contents": contents,
            }
            generation_config = _get_gemini_generation_config(model)
            if generation_config:
                payload["generation_config"] = generation_config

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            resp = _requests.post(
                _gemini_api_url(base_url),
                headers=headers,
                json=payload,
                timeout=DEFAULT_API_TIMEOUT,
            )
            resp.raise_for_status()
            resp_json = resp.json()
            parts = resp_json["candidates"][0]["content"]["parts"]
            text_parts = [part["text"] for part in parts if "text" in part and not part.get("thought")]
            text = ("\n".join(text_parts) if text_parts else parts[0].get("text", "")).strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return text.strip()
        except Exception as exc:
            if _is_timeout_error(exc):
                timeout_retries += 1
                should_retry = attempt < max_retries - 1 and timeout_retries < timeout_limit
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt + 1}/{max_retries} "
                    f"error={str(exc)} action={'retry' if should_retry else 'give_up'} "
                    f"{'non_retryable=timeout ' if not should_retry else ''}"
                    f"timeout_attempts={timeout_retries}/{timeout_limit}"
                    f"{f' backoff={retry_delay}s' if should_retry else ''}",
                )
                if should_retry:
                    time.sleep(retry_delay)
                    continue
                return None
            if _is_non_retryable_request_error(exc):
                reason = _non_retryable_request_reason(exc)
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt + 1}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable={reason}",
                )
                raise NonRetryableAPIError(str(exc))
            sleep_seconds = _compute_retry_delay(retry_delay, attempt + 1) if _is_rate_limit_error(exc) else retry_delay
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt + 1}/{max_retries} "
                f"error={str(exc)} action={'retry' if attempt < max_retries - 1 else 'give_up'}"
                f"{f' backoff={sleep_seconds}s' if attempt < max_retries - 1 else ''}",
            )
            if attempt < max_retries - 1:
                time.sleep(sleep_seconds)
            else:
                return None
    return None


def call_claude_api(
    messages: list[dict[str, Any]],
    model: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = 3,
    attempt_logger: AttemptLogger | None = None,
) -> tuple[str | None, str | None, str]:
    """Call Claude API and return (response_text, error, compress_info)."""
    profiles = _build_media_profiles(model, messages)
    profile_idx = 0
    thinking_budgets = _get_claude_thinking_budgets(model)
    thinking_idx = 0
    compress_info = ""
    retries = 0
    empty_text_retries = 0
    timeout_retries = 0
    timeout_limit = min(max(1, max_retries), _timeout_retry_limit_for_model(model))
    last_error = None

    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])

    while retries < max_retries:
        preflight_error, should_reduce_payload = _preflight_validate_api_messages(api_messages, model)
        if preflight_error:
            next_profile_idx = _next_reduction_profile_index(
                profiles,
                profile_idx,
                model,
                messages,
                preflight_error,
            )
            if should_reduce_payload and next_profile_idx is not None:
                profile_idx = next_profile_idx
                compress_info = _describe_media_profile(profiles[profile_idx])
                _log_attempt_event(
                    attempt_logger,
                    f"phase=preflight attempt={retries + 1}/{max_retries} "
                    f"error={preflight_error} action=retry fallback={compress_info}",
                )
                api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                continue
            _log_attempt_event(
                attempt_logger,
                f"phase=preflight attempt={retries + 1}/{max_retries} "
                f"error={preflight_error} action=give_up non_retryable=preflight",
            )
            return None, preflight_error, compress_info
        try:
            claude_msgs, system_text = _messages_to_claude_format(api_messages)
            thinking_config = None
            if thinking_budgets:
                thinking_config = {
                    "type": "enabled",
                    "budget_tokens": thinking_budgets[thinking_idx],
                }
            api_model = _get_claude_api_model(model)
            payload: dict[str, Any] = {
                "model": api_model,
                "max_tokens": 16000 if thinking_config else 8192,
                "messages": claude_msgs,
            }
            if system_text:
                payload["system"] = system_text
            if thinking_config:
                payload["thinking"] = thinking_config

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEFAULT_API_KEY}",
                "RawResponse": "1",
            }
            resp = _requests.post(
                CLAUDE_API_URL,
                headers=headers,
                json=payload,
                timeout=DEFAULT_CLAUDE_TIMEOUT,
            )
            if resp.status_code != 200:
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = resp.text[:500]
                raise RuntimeError(f"Claude API {resp.status_code}: {err_body}")

            resp_json = resp.json()
            if "error" in resp_json:
                err_msg = resp_json["error"]
                if isinstance(err_msg, dict):
                    err_msg = err_msg.get("message", str(err_msg))
                raise RuntimeError(f"Claude API error: {err_msg}")

            result_text = _extract_claude_text(resp_json)
            if not result_text:
                error_message = _build_claude_empty_text_error(resp_json)
                empty_text_retries += 1
                if _is_claude_empty_text_max_tokens(resp_json):
                    if empty_text_retries >= DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES:
                        _log_attempt_event(
                            attempt_logger,
                            f"phase=api attempt={retries + 1}/{max_retries} "
                            f"error={error_message} action=give_up "
                            f"non_retryable=empty_text empty_text_attempts={empty_text_retries}/{DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES}",
                        )
                        return None, error_message, compress_info
                    if thinking_budgets and thinking_idx + 1 < len(thinking_budgets):
                        thinking_idx += 1
                        retries += 1
                        next_budget = thinking_budgets[thinking_idx]
                        _log_attempt_event(
                            attempt_logger,
                            f"phase=api attempt={retries}/{max_retries} "
                            f"error={error_message} action=retry thinking_budget={next_budget}",
                        )
                        continue
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={retries + 1}/{max_retries} "
                        f"error={error_message} action=give_up non_retryable=max_tokens",
                    )
                    return None, error_message, compress_info
                should_retry = (
                    retries < max_retries - 1
                    and empty_text_retries < DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES
                )
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={retries + 1}/{max_retries} "
                    f"error={error_message} action={'retry' if should_retry else 'give_up'} "
                    f"empty_text_attempts={empty_text_retries}/{DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES}",
                )
                if should_retry:
                    retries += 1
                    time.sleep(retry_delay)
                    continue
                return None, error_message, compress_info
            return result_text, None, compress_info
        except Exception as exc:
            last_error = exc
            attempt_no = retries + 1
            if _is_timeout_error(exc):
                timeout_retries += 1
                if timeout_retries >= timeout_limit:
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=give_up non_retryable=timeout "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    return None, str(exc), compress_info
                if thinking_budgets and thinking_idx + 1 < len(thinking_budgets):
                    thinking_idx += 1
                    next_budget = thinking_budgets[thinking_idx]
                    retries += 1
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry thinking_budget={next_budget} "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    continue
                next_profile_idx = _next_reduction_profile_index(
                    profiles,
                    profile_idx,
                    model,
                    messages,
                    exc,
                )
                if next_profile_idx is not None:
                    profile_idx = next_profile_idx
                    compress_info = _describe_media_profile(profiles[profile_idx])
                    retries += 1
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry fallback={compress_info} "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                    continue
                retries += 1
                sleep_seconds = retry_delay
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action={'retry' if retries < max_retries else 'give_up'} "
                    f"timeout_attempts={timeout_retries}/{timeout_limit}"
                    f"{f' backoff={sleep_seconds}s' if retries < max_retries else ''}",
                )
                if retries < max_retries:
                    time.sleep(sleep_seconds)
                continue
            if _is_claude_empty_text_error(exc):
                empty_text_retries += 1
                should_retry = (
                    retries < max_retries - 1
                    and empty_text_retries < DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES
                )
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action={'retry' if should_retry else 'give_up'} "
                    f"empty_text_attempts={empty_text_retries}/{DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES}",
                )
                if should_retry:
                    retries += 1
                    time.sleep(retry_delay)
                    continue
                return None, str(exc), compress_info
            if _is_too_large_error(exc) or _is_invalid_image_media_error(exc):
                next_profile_idx = _next_reduction_profile_index(
                    profiles,
                    profile_idx,
                    model,
                    messages,
                    exc,
                )
                if next_profile_idx is not None:
                    profile_idx = next_profile_idx
                    compress_info = _describe_media_profile(profiles[profile_idx])
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt_no}/{max_retries} "
                        f"error={str(exc)} action=retry fallback={compress_info}",
                    )
                    api_messages = _prepare_messages_for_profile(messages, model, profiles[profile_idx])
                    continue
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable=payload",
                )
                return None, str(exc), compress_info
            if _is_non_retryable_request_error(exc):
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt_no}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable=request_validation",
                )
                return None, str(exc), compress_info
            retries += 1
            sleep_seconds = _compute_retry_delay(retry_delay, attempt_no) if _is_rate_limit_error(exc) else retry_delay
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt_no}/{max_retries} "
                f"error={str(exc)} action={'retry' if retries < max_retries else 'give_up'}"
                f"{f' backoff={sleep_seconds}s' if retries < max_retries else ''}",
            )
            if retries < max_retries:
                time.sleep(sleep_seconds)

    return None, str(last_error) if last_error else "Unknown error", compress_info


def _extract_json_object(text: str) -> str | None:
    """Extract a JSON object from text that may contain surrounding prose."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        json.loads(stripped)
        return stripped
    except (json.JSONDecodeError, ValueError):
        pass

    cleaned = stripped
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        json.loads(cleaned)
        return cleaned
    except (json.JSONDecodeError, ValueError):
        pass

    start = stripped.find("{")
    if start == -1:
        return None

    depth = 0
    for idx in range(start, len(stripped)):
        if stripped[idx] == "{":
            depth += 1
        elif stripped[idx] == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : idx + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except (json.JSONDecodeError, ValueError):
                    break
    return None


def call_claude_judge_api(
    model: str,
    rubrics_text: str,
    model_output: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = 3,
    attempt_logger: AttemptLogger | None = None,
) -> str | None:
    """Judge API using Claude format."""
    last_error: str | None = None
    prompt = GRADING_PROMPT_TEMPLATE.format(
        rubrics_text=rubrics_text,
        model_output=model_output,
    )
    thinking_budgets = _get_claude_thinking_budgets(model)
    thinking_idx = 0
    empty_text_retries = 0
    timeout_retries = 0
    timeout_limit = min(max(1, max_retries), _timeout_retry_limit_for_model(model))
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEFAULT_API_KEY}",
        "RawResponse": "1",
    }

    for attempt in range(max_retries):
        try:
            thinking_config = None
            if thinking_budgets:
                thinking_config = {
                    "type": "enabled",
                    "budget_tokens": thinking_budgets[thinking_idx],
                }
            payload: dict[str, Any] = {
                "model": _get_claude_api_model(model),
                "max_tokens": 16000 if thinking_config else 8192,
                "messages": [{"role": "user", "content": prompt}],
            }
            if thinking_config:
                payload["thinking"] = thinking_config

            resp = _requests.post(
                CLAUDE_API_URL,
                headers=headers,
                json=payload,
                timeout=DEFAULT_CLAUDE_TIMEOUT,
            )
            resp.raise_for_status()
            resp_json = resp.json()

            if "error" in resp_json:
                err_msg = resp_json["error"]
                if isinstance(err_msg, dict):
                    err_msg = err_msg.get("message", str(err_msg))
                raise RuntimeError(f"Claude API error: {err_msg}")

            text = _extract_claude_text(resp_json)
            if not text:
                last_error = _build_claude_empty_text_error(resp_json)
                empty_text_retries += 1
                non_retryable = _is_claude_empty_text_max_tokens(resp_json)
                empty_text_limit_reached = empty_text_retries >= DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES
                if non_retryable and thinking_budgets and thinking_idx + 1 < len(thinking_budgets):
                    if empty_text_limit_reached:
                        _log_attempt_event(
                            attempt_logger,
                            f"phase=api attempt={attempt + 1}/{max_retries} "
                            f"error={last_error} action=give_up non_retryable=empty_text "
                            f"empty_text_attempts={empty_text_retries}/{DEFAULT_CLAUDE_EMPTY_TEXT_RETRIES}",
                        )
                        raise NonRetryableClaudeError(last_error)
                    thinking_idx += 1
                    next_budget = thinking_budgets[thinking_idx]
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt + 1}/{max_retries} "
                        f"error={last_error} action=retry thinking_budget={next_budget}",
                    )
                    continue
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt + 1}/{max_retries} "
                    f"error={last_error} action={'give_up' if non_retryable or empty_text_limit_reached or attempt == max_retries - 1 else 'retry'}"
                    f"{' non_retryable=max_tokens' if non_retryable else ''}",
                )
                if non_retryable or empty_text_limit_reached:
                    raise NonRetryableClaudeError(last_error)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None

            extracted = _extract_json_object(text)
            if extracted:
                return extracted

            last_error = f"Claude judge returned non-JSON text: {_truncate_for_log(text, 600)}"
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt + 1}/{max_retries} "
                f"error={last_error} action={'retry' if attempt < max_retries - 1 else 'give_up'}",
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None
        except NonRetryableClaudeError:
            raise
        except Exception as exc:
            last_error = str(exc)
            if _is_timeout_error(exc):
                timeout_retries += 1
                if timeout_retries >= timeout_limit:
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt + 1}/{max_retries} "
                        f"error={last_error} action=give_up non_retryable=timeout "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    return None
                if thinking_budgets and thinking_idx + 1 < len(thinking_budgets):
                    thinking_idx += 1
                    next_budget = thinking_budgets[thinking_idx]
                    _log_attempt_event(
                        attempt_logger,
                        f"phase=api attempt={attempt + 1}/{max_retries} "
                        f"error={last_error} action=retry thinking_budget={next_budget} "
                        f"timeout_attempts={timeout_retries}/{timeout_limit}",
                    )
                    continue
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt + 1}/{max_retries} "
                    f"error={last_error} action=retry "
                    f"timeout_attempts={timeout_retries}/{timeout_limit} backoff={retry_delay}s",
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None
            sleep_seconds = _compute_retry_delay(retry_delay, attempt + 1) if _is_rate_limit_error(exc) else retry_delay
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt + 1}/{max_retries} "
                f"error={last_error} action={'retry' if attempt < max_retries - 1 else 'give_up'}"
                f"{f' backoff={sleep_seconds}s' if attempt < max_retries - 1 else ''}",
            )
            if attempt < max_retries - 1:
                time.sleep(sleep_seconds)
            else:
                return None
    return None


def build_rubrics_text(rubrics: list[Any]) -> str:
    if not rubrics:
        return "No specific rubrics provided."
    lines = []
    for idx, rubric in enumerate(rubrics, 1):
        if isinstance(rubric, dict):
            criteria = rubric.get("rubric_criteria", "").strip()
        else:
            criteria = str(rubric).strip()
        if criteria:
            lines.append(f"{idx}. {criteria}")
    return "\n".join(lines) if lines else "No specific rubrics provided."


GRADING_PROMPT_TEMPLATE = (
    "Starting now, you are a rigorous instruction-following grading teacher. "
    "Your task is to accurately grade and score student answers based only on the 【Rubrics】.\n\n"
    "Grading Criteria\n"
    "The final score is binary. A score of 1 means every rubric requirement is satisfied under the rules below; "
    "a score of 0 means at least one explicit core requirement is not satisfied.\n"
    "Hard constraints must be enforced strictly, but a constraint is hard only when the rubric clearly says so. "
    "Do not invent hidden exact-format, exact-wording, case, order, or field-name requirements that are not stated in the rubric.\n\n"
    "Grading Process\n"
    "Please strictly follow the steps below for analysis—no steps may be skipped:\n"
    "Step 1: Analyze the Rubrics and Constraint Types\n"
    "List all explicit requirements in the 【Rubrics】 item by item.\n"
    "For each requirement, first decide whether the rubric declares a hard constraint. Hard-constraint signals include, but are not limited to: "
    "\"must\", \"exactly\", \"only\", \"no extra text\", \"no text outside\", \"case-sensitive\", "
    "\"verbatim\", \"do not paraphrase\", \"must cite\", \"must include section number\", "
    "\"must preserve the original label/name/format\", \"must choose from the following labels\", "
    "\"JSON schema must be\", \"field name must be\", or any rubric wording that explicitly says a format, "
    "label, quote, identifier, or output structure is required.\n"
    "If a hard-constraint signal is present, enforce that constraint strictly. If no such signal is present, "
    "evaluate the requirement by semantic equivalence rather than by surface-form matching.\n"
    "Do not treat rubric wording itself as the only correct wording unless the rubric explicitly requires exact wording or specific terms.\n"
    "Step 2: Check Each Requirement Against the Student's Answer\n"
    "For every requirement in the 【Rubrics】, verify one by one whether the student's answer satisfies it under the appropriate constraint type.\n"
    "For semantic requirements, accept equivalent expressions, synonyms, reordered explanations, or split fields when they preserve the required meaning.\n"
    "For example, do not fail an answer merely because it says \"delay\" instead of \"latency\", "
    "\"system does not start normally\" instead of \"not entered normal operating state\", "
    "or presents title/edition/author as separate fields, unless the rubric explicitly requires exact terms or exact formatting.\n"
    "If the rubric requires reasoning or an intermediate process, check that the answer includes that process; "
    "do not accept a final answer alone when the intermediate process is an explicit requirement.\n"
    "If the rubric says the answer should be based on provided material and not rely on external knowledge, distinguish between "
    "external knowledge replacing or contradicting the material, which should fail, and harmless background context that does not change the document-based conclusion.\n"
    "Distinguish core answer errors from minor explanation inconsistencies. A key factual error or wrong conclusion fails the relevant requirement; "
    "a minor wording or local explanation issue should not fail the requirement if the core rubric requirement is still satisfied.\n"
    "Normalization Rules (apply ONLY when the rubric does not explicitly test the exact surface form):\n"
    "  - Letter case: treat case-insensitive matches as equivalent when the rubric is about meaning/content "
    "(e.g., \"Fixed\" vs \"fixed\" vs \"FIXED\" are all acceptable). Only enforce exact case when the rubric "
    "is explicitly about capitalization, casing style, or the exact surface form of a token.\n"
    "  - Numeric formatting: treat numerically-equal values as equivalent regardless of digit grouping, "
    "thousands separators, leading zeros, or trivial decimal notation (e.g., 10000 == 10,000 == 10 000 == "
    "10000.0; 0.5 == .5; 1e3 == 1000). Only enforce a specific numeric format when the rubric explicitly "
    "requires that format (e.g., \"must include thousands separator\", \"must be in scientific notation\"). "
    "Do not normalize numbers when they function as identifiers, labels, codes, device names, locker numbers, "
    "sample IDs, case IDs, or exact strings.\n"
    "  - Whitespace, punctuation, hyphen/dash variants, field order, field splitting, and common abbreviation/full-name variants "
    "that do not alter meaning should be tolerated unless the rubric explicitly tests them. "
    "Field splitting or reordering is acceptable only for semantic answers. It is not acceptable when the rubric requires "
    "a fixed JSON schema, table columns, field names, answer block, or machine-readable format.\n"
    "  - These normalization rules relax ONLY non-hard surface form; all explicit semantic/content requirements remain strict.\n"
    "Step 3: Self-Reflection\n"
    "Before giving the final score, you must conduct the following checks:\n"
    "  Completeness Check: Whether all requirements have been reviewed with no omissions.\n"
    "  Constraint Check: Whether hard constraints were enforced only when explicitly declared by the rubric.\n"
    "  Semantic Equivalence Check: Whether non-hard wording, formatting, order, case, whitespace, punctuation, or synonym differences "
    "were normalized instead of being treated as automatic failures.\n"
    "  Strictness Check: Whether explicit core semantic/content requirements were still evaluated strictly.\n"
    "  Consistency Check: Whether the grading rationale aligns logically with the per-requirement status and final score.\n"
    "  Before finalizing, verify that each requirement status is consistent with the written rationale.\n"
    "  Objectivity Check: Whether judgments are based on objective facts.\n"
    "Output Format Requirements\n"
    "Please strictly output ONLY the following JSON format (do not output any other content):\n"
    "{{\n"
    '  "Grading Rationale": "Your detailed grading rationale",\n'
    '  "List of Requirement Satisfaction Status": ["yes", "no", ...],\n'
    '  "Overall Score": 0 or 1\n'
    "}}\n\n"
    "Content to Be Graded\n"
    "【Rubrics】:\n{rubrics_text}\n"
    "【Student Response】:\n{model_output}\n"
)


def call_judge_api(
    client: OpenAI,
    model: str,
    rubrics_text: str,
    model_output: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = 3,
    attempt_logger: AttemptLogger | None = None,
) -> str | None:
    prompt = GRADING_PROMPT_TEMPLATE.format(
        rubrics_text=rubrics_text,
        model_output=model_output,
    )
    messages = [{"role": "user", "content": prompt}]
    timeout_retries = 0
    timeout_limit = min(max(1, max_retries), _timeout_retry_limit_for_model(model))
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(model=model, messages=messages)
            text = response.choices[0].message.content
            if isinstance(text, dict):
                text = text.get("text", str(text))
            stripped = text.strip()
            if stripped.startswith("```json"):
                stripped = stripped[7:]
            if stripped.startswith("```"):
                stripped = stripped[3:]
            if stripped.endswith("```"):
                stripped = stripped[:-3]
            return stripped.strip()
        except Exception as exc:
            if _is_timeout_error(exc):
                timeout_retries += 1
                should_retry = attempt < max_retries - 1 and timeout_retries < timeout_limit
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt + 1}/{max_retries} "
                    f"error={str(exc)} action={'retry' if should_retry else 'give_up'} "
                    f"{'non_retryable=timeout ' if not should_retry else ''}"
                    f"timeout_attempts={timeout_retries}/{timeout_limit}"
                    f"{f' backoff={retry_delay}s' if should_retry else ''}",
                )
                if should_retry:
                    time.sleep(retry_delay)
                    continue
                return None
            if _is_non_retryable_request_error(exc):
                reason = _non_retryable_request_reason(exc)
                _log_attempt_event(
                    attempt_logger,
                    f"phase=api attempt={attempt + 1}/{max_retries} "
                    f"error={str(exc)} action=give_up non_retryable={reason}",
                )
                raise NonRetryableAPIError(str(exc))
            sleep_seconds = _compute_retry_delay(retry_delay, attempt + 1) if _is_rate_limit_error(exc) else retry_delay
            _log_attempt_event(
                attempt_logger,
                f"phase=api attempt={attempt + 1}/{max_retries} "
                f"error={str(exc)} action={'retry' if attempt < max_retries - 1 else 'give_up'}"
                f"{f' backoff={sleep_seconds}s' if attempt < max_retries - 1 else ''}",
            )
            if attempt < max_retries - 1:
                time.sleep(sleep_seconds)
            else:
                return None
    return None


def parse_judge_result(raw_text: str) -> tuple[str, list[Any], int]:
    result = json.loads(raw_text)
    if "Overall Score" not in result:
        raise ValueError("Missing 'Overall Score'")
    return (
        result.get("Grading Rationale", ""),
        result.get("List of Requirement Satisfaction Status", []),
        result.get("Overall Score", 0),
    )


def compute_statistics(data_list: list[dict[str, Any]]) -> str:
    scored = [item for item in data_list if item.get("score") is not None]
    if not scored:
        return "No scored items."
    total = len(scored)
    score_1 = sum(1 for item in scored if item.get("score") == 1)
    rate = score_1 / total if total else 0
    return f"Overall: {score_1}/{total} = {rate:.4f}"


def infer_single_item(
    item: dict[str, Any],
    model: str,
    client: OpenAI | None,
    max_retries: int,
    attempt_logger: AttemptLogger | None = None,
) -> tuple[str | None, str | None, str]:
    messages = item.get("messages")
    if not messages:
        return None, "No messages", ""
    if _is_claude_model(model):
        return call_claude_api(
            messages,
            model,
            max_retries=max_retries,
            attempt_logger=attempt_logger,
        )
    if _is_gemini_native_model(model):
        return call_gemini_native_api(
            messages,
            model,
            DEFAULT_BASE_URL,
            DEFAULT_API_KEY,
            max_retries=max_retries,
            attempt_logger=attempt_logger,
        )
    if client is None:
        return None, "OpenAI client is not initialized", ""
    return call_openai_api(
        client,
        messages,
        model,
        max_retries=max_retries,
        attempt_logger=attempt_logger,
    )


def eval_single_item(
    item: dict[str, Any],
    model: str,
    client: OpenAI | None,
    max_retries: int,
    attempt_logger: AttemptLogger | None = None,
) -> tuple[str, list[Any], int, str | None]:
    model_output = str(item.get("model_output", "")).strip()
    if not model_output:
        return "", [], 0, "Missing model_output"

    rubrics_text = build_rubrics_text(item.get("rubrics", []))
    parse_retries = max(1, min(max_retries, DEFAULT_JUDGE_PARSE_RETRIES))
    for parse_attempt in range(parse_retries):
        try:
            if _is_claude_model(model):
                raw = call_claude_judge_api(
                    model,
                    rubrics_text,
                    model_output,
                    max_retries=max_retries,
                    attempt_logger=attempt_logger,
                )
            elif _is_gemini_native_model(model):
                raw = call_gemini_native_judge_api(
                    model,
                    rubrics_text,
                    model_output,
                    DEFAULT_BASE_URL,
                    DEFAULT_API_KEY,
                    max_retries=max_retries,
                    attempt_logger=attempt_logger,
                )
            else:
                if client is None:
                    return "API client is not initialized", [], 0, "API client is not initialized"
                raw = call_judge_api(
                    client,
                    model,
                    rubrics_text,
                    model_output,
                    max_retries=max_retries,
                    attempt_logger=attempt_logger,
                )
        except (NonRetryableClaudeError, NonRetryableAPIError) as exc:
            return "API call failed", [], 0, str(exc)

        if not raw:
            _log_attempt_event(
                attempt_logger,
                f"phase=parse attempt={parse_attempt + 1}/{parse_retries} "
                f"error=empty judge response after API retries "
                f"action={'retry' if parse_attempt < parse_retries - 1 else 'give_up'}",
            )
            if parse_attempt < parse_retries - 1:
                time.sleep(2)
                continue
            return "API call failed", [], 0, "API failed"

        try:
            rationale, status, score = parse_judge_result(raw)
            return rationale, status, score, None
        except (json.JSONDecodeError, ValueError) as exc:
            _log_attempt_event(
                attempt_logger,
                f"phase=parse attempt={parse_attempt + 1}/{parse_retries} "
                f"error={str(exc)} action={'retry' if parse_attempt < parse_retries - 1 else 'give_up'} "
                f"raw={_truncate_for_log(raw[:600], 600)}",
            )
            if parse_attempt < parse_retries - 1:
                time.sleep(2)
            else:
                return f"Parse failed: {raw[:300]}", [], 0, str(exc)
    return "Unknown error", [], 0, "Unknown"


def get_context_turn(item: dict[str, Any], idx: int) -> tuple[str | None, int | None]:
    metadata = item.get("metadata", {})
    context_id = metadata.get("context_id")
    turn_index = metadata.get("turn_index")
    if context_id not in {None, ""} and turn_index not in {None, ""}:
        try:
            return str(context_id), int(turn_index)
        except (TypeError, ValueError):
            pass

    task_id = str(metadata.get("task_id", ""))
    match = re.match(r"(.+)_T(\d+)$", task_id)
    if match:
        return match.group(1), int(match.group(2))
    return None, None


def apply_context_outputs_to_item(
    item: dict[str, Any],
    outputs_by_turn: dict[int, str],
) -> bool:
    """Replace assistant messages in a multi-turn sample with generated outputs."""
    if not outputs_by_turn:
        return False

    messages = item.get("messages", [])
    assistant_indices = [
        msg_idx
        for msg_idx, msg in enumerate(messages)
        if msg.get("role") == "assistant"
    ]
    updated = False

    for turn_step, msg_idx in enumerate(assistant_indices, start=1):
        if turn_step not in outputs_by_turn:
            continue
        replacement = outputs_by_turn[turn_step]
        content = messages[msg_idx].get("content", [])
        if isinstance(content, list):
            replaced_text = False
            for part in content:
                if part.get("type") == "text":
                    if part.get("text") != replacement:
                        part["text"] = replacement
                        updated = True
                    replaced_text = True
                    break
            if not replaced_text:
                content.insert(0, {"type": "text", "text": replacement})
                updated = True
        elif isinstance(content, str):
            if content != replacement:
                messages[msg_idx]["content"] = replacement
                updated = True
        else:
            messages[msg_idx]["content"] = replacement
            updated = True
    return updated


_MEDIA_PART_TYPES = {"image_url", "video", "video_url"}


def _media_part_src(part: dict[str, Any]) -> str:
    part_type = part.get("type")
    if part_type == "image_url":
        obj = part.get("image_url", {})
    elif part_type == "video":
        obj = part.get("video", {})
    elif part_type == "video_url":
        obj = part.get("video_url", {})
    else:
        return ""
    return obj.get("url", "") if isinstance(obj, dict) else str(obj)


def _strip_media_parts_from_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    kept = [part for part in content if part.get("type") not in _MEDIA_PART_TYPES]
    if kept:
        return kept
    return [{"type": "text", "text": "[Previous user media omitted.]"}]


def _collect_user_video_sources(messages: list[dict[str, Any]], start_idx: int) -> set[str]:
    sources: set[str] = set()
    for msg in messages[start_idx:]:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") in {"video", "video_url"}:
                src = _media_part_src(part)
                if src:
                    sources.add(src)
    return sources


def _compact_smart_history_user_content(content: Any, seen_video_sources: set[str]) -> Any:
    if not isinstance(content, list):
        if isinstance(content, str) and content.strip():
            return [
                {
                    "type": "text",
                    "text": _compact_text_value(content, DEFAULT_HISTORY_TEXT_PREVIEW_CHARS),
                }
            ]
        return [{"type": "text", "text": "[Previous user turn omitted.]"}]

    kept: list[dict[str, Any]] = []
    text_values: list[str] = []
    omitted_media = 0
    for part in content:
        part_type = part.get("type")
        if part_type == "text":
            text = str(part.get("text", ""))
            if text.strip():
                text_values.append(text)
        elif part_type in {"video", "video_url"}:
            kept.append(copy.deepcopy(part))
            src = _media_part_src(part)
            if src:
                seen_video_sources.add(src)
        elif part_type in _MEDIA_PART_TYPES:
            omitted_media += 1
        else:
            kept.append(copy.deepcopy(part))

    if text_values:
        kept.insert(
            0,
            {
                "type": "text",
                "text": _compact_text_value(
                    "\n\n".join(text_values),
                    DEFAULT_HISTORY_TEXT_PREVIEW_CHARS,
                ),
            },
        )
    if omitted_media:
        kept.append(
            {
                "type": "text",
                "text": f"[Previous user media omitted: {omitted_media} duplicate or non-video item(s).]",
            }
        )
    if kept:
        return kept
    return [{"type": "text", "text": "[Previous user turn omitted.]"}]


def copy_item_for_history_media_policy(
    item: dict[str, Any],
    policy: str,
) -> dict[str, Any]:
    """Return a request-only copy with earlier user turns compacted."""
    normalized = (policy or "full").strip().lower()
    if normalized == "full":
        return item

    messages = item.get("messages")
    if not isinstance(messages, list):
        return item

    user_indices = [
        msg_idx
        for msg_idx, msg in enumerate(messages)
        if isinstance(msg, dict) and msg.get("role") == "user"
    ]
    if len(user_indices) <= 1:
        return item

    request_item = copy.deepcopy(item)
    request_messages = request_item.get("messages", [])
    current_user_idx = user_indices[-1]
    placeholder = [
        {
            "type": "text",
            "text": "[Previous user turn omitted; prior assistant answer retained.]",
        }
    ]

    if normalized == "smart":
        seen_video_sources = _collect_user_video_sources(request_messages, current_user_idx)
        for msg_idx in reversed(user_indices):
            if msg_idx >= current_user_idx:
                continue
            msg = request_messages[msg_idx]
            msg["content"] = _compact_smart_history_user_content(
                msg.get("content"),
                seen_video_sources,
            )
        return request_item

    for msg_idx in user_indices:
        if msg_idx >= current_user_idx:
            continue
        msg = request_messages[msg_idx]
        if normalized == "answers-only":
            msg["content"] = copy.deepcopy(placeholder)
        elif normalized == "current-turn-only":
            msg["content"] = _strip_media_parts_from_content(msg.get("content"))

    return request_item


def collect_existing_context_outputs(
    data: list[dict[str, Any]],
    excluded_indices: set[int] | None = None,
) -> dict[str, dict[int, str]]:
    outputs: dict[str, dict[int, str]] = defaultdict(dict)
    excluded = excluded_indices or set()
    for idx, item in enumerate(data):
        if idx in excluded:
            continue
        model_output = item.get("model_output")
        if not model_output:
            continue
        context_id, turn_index = get_context_turn(item, idx)
        if context_id is None or turn_index is None:
            continue
        outputs[context_id][turn_index] = str(model_output)
    return outputs


def build_turn_batches(
    data: list[dict[str, Any]],
    indices: list[int],
    apply_history: bool,
) -> list[list[tuple[int, str | None, int | None]]]:
    if not apply_history:
        return [[(idx, None, None)] for idx in indices]

    grouped: dict[int, list[tuple[int, str | None, int | None]]] = defaultdict(list)
    for idx in indices:
        context_id, turn_index = get_context_turn(data[idx], idx)
        if context_id is None or turn_index is None:
            grouped[0].append((idx, None, None))
        else:
            grouped[turn_index].append((idx, context_id, turn_index))

    batches = []
    for turn_index in sorted(grouped):
        batch = sorted(grouped[turn_index], key=lambda item: item[0])
        batches.append(batch)
    return batches


def print_stage(message: str) -> None:
    print(message, flush=True)


def log_and_print(log_path: str, message: str) -> None:
    print_stage(message)
    write_log(log_path, message)


def validate_runtime_config(args: argparse.Namespace) -> None:
    if args.api_key:
        globals()["DEFAULT_API_KEY"] = args.api_key
    if args.base_url:
        base_url = args.base_url.rstrip("/")
        globals()["DEFAULT_BASE_URL"] = base_url
        globals()["GPT_BASE_URL"] = base_url
        globals()["DOUBAO_BASE_URL"] = base_url
    if args.claude_api_url:
        globals()["CLAUDE_API_URL"] = args.claude_api_url.rstrip("/")

    if args.dry_run:
        return

    needs_api = args.stage in {"infer", "eval", "full"}
    if needs_api and not DEFAULT_API_KEY:
        raise RuntimeError(
            "Missing API key. Set CLBENCH_OPENAI_API_KEY in app_config.env or pass --api-key."
        )

    for model in [args.infer_model] if args.stage == "infer" else []:
        if _is_gemini_native_model(model) and not (DEFAULT_BASE_URL or GEMINI_API_URL):
            raise RuntimeError(
                f"Inference model '{model}' requires CLBENCH_OPENAI_BASE_URL or CLBENCH_GEMINI_API_URL."
            )
        if _is_claude_model(model) and not CLAUDE_API_URL:
            raise RuntimeError(f"Inference model '{model}' requires CLBENCH_CLAUDE_API_URL.")

    for model in [args.judge_model] if args.stage == "eval" else []:
        if _is_gemini_native_model(model) and not (DEFAULT_BASE_URL or GEMINI_API_URL):
            raise RuntimeError(
                f"Judge model '{model}' requires CLBENCH_OPENAI_BASE_URL or CLBENCH_GEMINI_API_URL."
            )
        if _is_claude_model(model) and not CLAUDE_API_URL:
            raise RuntimeError(f"Judge model '{model}' requires CLBENCH_CLAUDE_API_URL.")

    if args.stage == "full":
        if _is_gemini_native_model(args.infer_model) and not (DEFAULT_BASE_URL or GEMINI_API_URL):
            raise RuntimeError(
                f"Inference model '{args.infer_model}' requires CLBENCH_OPENAI_BASE_URL or CLBENCH_GEMINI_API_URL."
            )
        if _is_claude_model(args.infer_model) and not CLAUDE_API_URL:
            raise RuntimeError(
                f"Inference model '{args.infer_model}' requires CLBENCH_CLAUDE_API_URL."
            )
        if _is_gemini_native_model(args.judge_model) and not (DEFAULT_BASE_URL or GEMINI_API_URL):
            raise RuntimeError(
                f"Judge model '{args.judge_model}' requires CLBENCH_OPENAI_BASE_URL or CLBENCH_GEMINI_API_URL."
            )
        if _is_claude_model(args.judge_model) and not CLAUDE_API_URL:
            raise RuntimeError(
                f"Judge model '{args.judge_model}' requires CLBENCH_CLAUDE_API_URL."
            )


def media_summary(data: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "items": len(data),
        "image_parts": 0,
        "video_parts": 0,
        "missing_local_media": [],
        "items_with_rubrics": 0,
        "items_with_model_output": 0,
    }
    for item_idx, item in enumerate(data):
        if item.get("rubrics"):
            summary["items_with_rubrics"] += 1
        if item.get("model_output"):
            summary["items_with_model_output"] += 1
        for msg in item.get("messages", []):
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                part_type = part.get("type")
                if part_type == "image_url":
                    summary["image_parts"] += 1
                    url_obj = part.get("image_url", {})
                    src = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                    if src and src.startswith("/") and not os.path.isfile(src):
                        summary["missing_local_media"].append((item_idx, src))
                elif part_type == "video":
                    summary["video_parts"] += 1
                    video_obj = part.get("video", {})
                    src = video_obj.get("url", "") if isinstance(video_obj, dict) else str(video_obj)
                    if src and src.startswith("/") and not os.path.isfile(src):
                        summary["missing_local_media"].append((item_idx, src))
    return summary


def run_inference_stage(
    data: list[dict[str, Any]],
    indices: list[int],
    source_name: str,
    args: argparse.Namespace,
) -> tuple[str, int]:
    model = args.infer_model
    selected_indices = indices[:]
    if args.skip_existing_output:
        selected_indices = [
            idx for idx in selected_indices if not str(data[idx].get("model_output", "")).strip()
        ]

    if not selected_indices:
        print_stage("Inference skipped: no items selected.")
        out_path = args.infer_output or build_output_jsonl_path(
            args.output_dir,
            "infer",
            model,
            source_name,
        )
        save_jsonl(data, out_path)
        return out_path, 0

    use_native = _is_gemini_native_model(model)
    use_claude = _is_claude_model(model)
    client = None if (use_native or use_claude) else OpenAI(
        api_key=DEFAULT_API_KEY,
        base_url=_openai_base_url_for_model(model) or None,
        timeout=DEFAULT_API_TIMEOUT,
        max_retries=0,
    )

    log_path = create_log_file(
        f"infer_{sanitize_filename_part(model)}",
        args.log_dir,
    )
    log_and_print(
        log_path,
        (
            f"Inference started: model={model}, total={len(selected_indices)}, "
            f"workers={args.infer_workers}, "
            f"history_media_policy={args.history_media_policy if args.apply_history else 'off'}"
        ),
    )

    failures = 0
    done = 0
    total = len(selected_indices)

    outputs_by_context = collect_existing_context_outputs(
        data,
        excluded_indices=set(selected_indices),
    )
    batches = build_turn_batches(data, selected_indices, args.apply_history)

    for batch_no, batch in enumerate(batches, start=1):
        if args.apply_history:
            print_stage(
                f"[infer] processing turn batch {batch_no}/{len(batches)} with {len(batch)} item(s)"
            )

        futures = {}
        with ThreadPoolExecutor(max_workers=max(1, int(args.infer_workers))) as executor:
            for idx, context_id, _turn_index in batch:
                task_id = get_task_id(data[idx])
                if context_id is not None:
                    apply_context_outputs_to_item(data[idx], outputs_by_context.get(context_id, {}))
                request_item = (
                    copy_item_for_history_media_policy(data[idx], args.history_media_policy)
                    if args.apply_history
                    else data[idx]
                )
                futures[
                    executor.submit(
                        infer_single_item,
                        request_item,
                        model,
                        client,
                        args.max_retries,
                        _build_attempt_logger(log_path, "infer", idx, task_id, model),
                    )
                ] = (idx, context_id, _turn_index)

            for future in as_completed(futures):
                idx, context_id, turn_index = futures[future]
                task_id = get_task_id(data[idx])
                try:
                    response_text, error, compress_info = future.result()
                except Exception as exc:
                    response_text, error, compress_info = None, str(exc), ""

                if compress_info:
                    data[idx]["infer_fallback_profile"] = compress_info
                    if "degraded=smart-history" in compress_info:
                        data[idx]["infer_fallback_degraded"] = True
                    else:
                        data[idx].pop("infer_fallback_degraded", None)
                    log_and_print(log_path, f"[infer] idx={idx} task={task_id} fallback={compress_info}")
                else:
                    data[idx].pop("infer_fallback_profile", None)
                    data[idx].pop("infer_fallback_degraded", None)

                if error:
                    failures += 1
                    data[idx]["infer_error"] = error
                    log_and_print(log_path, f"[infer] idx={idx} task={task_id} failed: {error}")
                else:
                    data[idx]["model_output"] = response_text
                    data[idx].pop("infer_error", None)
                    if context_id is not None and turn_index is not None:
                        outputs_by_context.setdefault(context_id, {})[turn_index] = response_text or ""
                    log_and_print(
                        log_path,
                        f"[infer] idx={idx} task={task_id} done ({done + 1}/{total})",
                    )

                done += 1

    out_path = args.infer_output or build_output_jsonl_path(
        args.output_dir,
        "infer",
        model,
        source_name,
    )
    save_jsonl(data, out_path)
    log_and_print(
        log_path,
        f"Inference finished: success={total - failures}, failed={failures}, output={out_path}",
    )
    return out_path, failures


def run_evaluation_stage(
    data: list[dict[str, Any]],
    indices: list[int],
    source_name: str,
    args: argparse.Namespace,
) -> tuple[str, int, str]:
    model = args.judge_model
    selected_indices = [idx for idx in indices if str(data[idx].get("model_output", "")).strip()]
    if args.skip_existing_score:
        selected_indices = [idx for idx in selected_indices if data[idx].get("score") is None]

    if not selected_indices:
        summary = compute_statistics(data)
        print_stage(f"Evaluation skipped: no items selected. {summary}")
        out_path = args.eval_output or build_output_jsonl_path(
            args.grade_dir,
            "eval",
            model,
            source_name,
        )
        save_jsonl(data, out_path)
        return out_path, 0, summary

    use_native = _is_gemini_native_model(model)
    use_claude = _is_claude_model(model)
    client = None if (use_native or use_claude) else OpenAI(
        api_key=DEFAULT_API_KEY,
        base_url=_openai_base_url_for_model(model) or None,
        timeout=DEFAULT_API_TIMEOUT,
        max_retries=0,
    )

    log_path = create_log_file(
        f"eval_{sanitize_filename_part(model)}",
        args.grade_log_dir,
    )
    log_and_print(
        log_path,
        f"Evaluation started: judge={model}, total={len(selected_indices)}, workers={args.eval_workers}",
    )

    failures = 0
    done = 0
    total = len(selected_indices)

    with ThreadPoolExecutor(max_workers=max(1, int(args.eval_workers))) as executor:
        futures = {
            executor.submit(
                eval_single_item,
                data[idx],
                model,
                client,
                args.max_retries,
                _build_attempt_logger(log_path, "eval", idx, get_task_id(data[idx]), model),
            ): idx
            for idx in selected_indices
        }

        for future in as_completed(futures):
            idx = futures[future]
            task_id = get_task_id(data[idx])
            try:
                rationale, status, score, error = future.result()
            except Exception as exc:
                rationale, status, score, error = "", [], 0, str(exc)

            data[idx]["grading_rationale"] = rationale
            data[idx]["requirement_status"] = status
            data[idx]["score"] = score

            if error:
                failures += 1
                data[idx]["eval_error"] = error
                log_and_print(log_path, f"[eval] idx={idx} task={task_id} failed: {error}")
            else:
                data[idx].pop("eval_error", None)
                log_and_print(
                    log_path,
                    f"[eval] idx={idx} task={task_id} done ({done + 1}/{total}) score={score}",
                )
            done += 1

    summary = compute_statistics(data)
    out_path = args.eval_output or build_output_jsonl_path(
        args.grade_dir,
        "eval",
        model,
        source_name,
    )
    save_jsonl(data, out_path)
    log_and_print(
        log_path,
        f"Evaluation finished: success={total - failures}, failed={failures}, summary={summary}, output={out_path}",
    )
    return out_path, failures, summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MCL-Bench backend inference/evaluation without Gradio.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Input dataset path (.json or .jsonl)")
    parser.add_argument(
        "media_path",
        nargs="?",
        default="",
        help="Optional media directory or media file path for resolving relative refs",
    )
    parser.add_argument(
        "--stage",
        choices=["full", "infer", "eval"],
        default="full",
        help="Pipeline stage to run",
    )
    parser.add_argument("--infer-model", default="Gemini-2.5-pro", help="Inference model")
    parser.add_argument("--judge-model", default="GPT 5.2", help="Judge model")
    parser.add_argument("--infer-workers", type=int, default=1, help="Inference worker count")
    parser.add_argument("--eval-workers", type=int, default=1, help="Evaluation worker count")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="API retry count",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N items (0 means all)",
    )
    parser.add_argument(
        "--apply-history",
        action="store_true",
        help="Inject generated previous-turn outputs into later-turn assistant messages",
    )
    parser.add_argument(
        "--history-media-policy",
        choices=["full", "smart", "current-turn-only", "answers-only"],
        default=DEFAULT_HISTORY_MEDIA_POLICY,
        help=(
            "How to compact earlier user turns when --apply-history is enabled. "
            "smart keeps current turns intact, keeps prior videos, and compacts prior user text/media; "
            "full keeps old behavior; current-turn-only removes prior media; "
            "answers-only keeps prior assistant answers and omits prior user turns."
        ),
    )
    parser.add_argument(
        "--skip-existing-output",
        action="store_true",
        help="Skip items that already have model_output during inference",
    )
    parser.add_argument(
        "--skip-existing-score",
        action="store_true",
        help="Skip items that already have score during evaluation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only validate loading and media resolution without calling any API",
    )
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Inference output directory")
    parser.add_argument("--grade-dir", default=GRADE_DIR, help="Evaluation output directory")
    parser.add_argument("--log-dir", default=LOG_DIR, help="Inference log directory")
    parser.add_argument(
        "--grade-log-dir",
        default=GRADE_LOG_DIR,
        help="Evaluation log directory",
    )
    parser.add_argument("--infer-output", default="", help="Explicit inference output JSONL path")
    parser.add_argument("--eval-output", default="", help="Explicit evaluation output JSONL path")
    parser.add_argument("--api-key", default="", help="Override CLBENCH_OPENAI_API_KEY")
    parser.add_argument("--base-url", default="", help="Override CLBENCH_OPENAI_BASE_URL")
    parser.add_argument(
        "--claude-api-url",
        default="",
        help="Override CLBENCH_CLAUDE_API_URL",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        validate_runtime_config(args)
        data = load_data_file(args.input, args.media_path)
    except Exception as exc:
        print(f"Failed to load input: {exc}", file=sys.stderr)
        return 1

    if not data:
        print("Input dataset is empty.", file=sys.stderr)
        return 1

    total_items = len(data)
    indices = list(range(total_items))
    if args.limit and args.limit > 0:
        indices = indices[: args.limit]

    print_stage(
        f"Loaded {total_items} item(s) from {args.input}. Selected {len(indices)} item(s) for processing."
    )
    if args.media_path:
        print_stage(f"Media path: {args.media_path}")

    if args.dry_run:
        summary = media_summary(data)
        print_stage(
            "Dry run summary: "
            f"items={summary['items']}, "
            f"images={summary['image_parts']}, "
            f"videos={summary['video_parts']}, "
            f"items_with_rubrics={summary['items_with_rubrics']}, "
            f"items_with_model_output={summary['items_with_model_output']}, "
            f"missing_local_media={len(summary['missing_local_media'])}"
        )
        if summary["missing_local_media"]:
            for item_idx, missing_path in summary["missing_local_media"][:20]:
                print_stage(f"  missing media: item={item_idx} path={missing_path}")
            if len(summary["missing_local_media"]) > 20:
                print_stage("  ... more missing media omitted")
        return 0

    source_name = get_source_filename(args.input)
    infer_failures = 0
    eval_failures = 0

    if args.stage in {"infer", "full"}:
        try:
            infer_output, infer_failures = run_inference_stage(data, indices, source_name, args)
            print_stage(f"Inference output: {infer_output}")
        except Exception as exc:
            print(f"Inference failed: {exc}", file=sys.stderr)
            return 1

    if args.stage in {"eval", "full"}:
        try:
            eval_output, eval_failures, summary = run_evaluation_stage(data, indices, source_name, args)
            print_stage(f"Evaluation output: {eval_output}")
            print_stage(f"Evaluation summary: {summary}")
        except Exception as exc:
            print(f"Evaluation failed: {exc}", file=sys.stderr)
            return 1

    if infer_failures or eval_failures:
        print_stage(
            f"Pipeline completed with failures: infer_failures={infer_failures}, eval_failures={eval_failures}"
        )
        return 2

    print_stage("Pipeline completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
