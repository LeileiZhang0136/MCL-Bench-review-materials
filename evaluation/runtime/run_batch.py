#!/usr/bin/env python3
"""Batch runner for MCL-Bench cases.

Two-stage orchestration:

1. Inference stage — for each case, run inference with every model in
   ``INFER_MODELS`` and write one infer JSON per (case, infer_model).
2. Evaluation stage — for each case, merge all infer JSONs (each item tagged
   with ``infer_model``) and run every judge in ``EVAL_MODELS``. Each judge
   produces a single JSONL where every row carries the ``infer_model`` tag.

Expected layout under the input root:

  root/
    case1.json
    case1/                  # optional media dir
      ...
    case2.json
    ...

Outputs per case::

  root/case1_result/
    infer_case1_<model1>.json
    infer_case1_<model2>.json
    ...
    eval_case1_<eval_model>_<infer_model>.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
RUN_BACKEND_PATH = APP_DIR / "run_backend.py"
DEFAULT_MAX_RETRIES = 20

INFER_MODELS: list[str] = [
    "Gemini-2.5-pro",
    "Gemini-3.1-Pro-Preview (High)",
    "GPT 5.2",
    "Doubao-Seed-2.0-pro",
    "Claude-Sonnet-4.6",
    "Claude-Sonnet-4.6 Thinking",
    "Claude-Opus-4.6",
    "Claude-Opus-4.6 Thinking",
]

EVAL_MODELS: list[str] = [
    "GPT 5.2",
]


@dataclass
class CaseSpec:
    name: str
    json_path: Path
    media_path: Path | None
    result_dir: Path
    case_id: str | None = None
    input_root: Path | None = None

    @property
    def display_name(self) -> str:
        return self.case_id or self.name


def sanitize_filename_part(value: str, default: str = "unknown") -> str:
    cleaned = "".join(
        c if c.isalnum() or c in {"-", "_", "."} else "_"
        for c in (value or "").strip()
    )
    cleaned = cleaned.strip("._")
    return cleaned or default


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-run a folder of json/jsonl MCL-Bench cases.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input_root", help="Folder containing case json/jsonl files")
    parser.add_argument(
        "--recursive-first-level",
        action="store_true",
        help=(
            "Discover case files in first-level child directories and schedule "
            "them as one global case pool while keeping outputs in their source dirs"
        ),
    )
    parser.add_argument(
        "--include-roots",
        default="",
        help=(
            "Comma-separated child directory names to include when using "
            "--recursive-first-level"
        ),
    )
    parser.add_argument(
        "--stage",
        choices=["full", "infer", "eval"],
        default="full",
        help="Which stages to run across all cases",
    )
    parser.add_argument(
        "--case-workers",
        type=int,
        default=1,
        help="How many cases to run in parallel within one input root",
    )
    parser.add_argument("--infer-workers", type=int, default=50)
    parser.add_argument("--eval-workers", type=int, default=50)
    parser.add_argument(
        "--infer-model-workers",
        type=int,
        default=8,
        help="How many infer models to run in parallel within one case",
    )
    parser.add_argument(
        "--eval-model-workers",
        type=int,
        default=12,
        help="How many eval jobs to run in parallel within one case",
    )
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--limit", type=int, default=0, help="Per-case item limit")
    parser.add_argument("--apply-history", action="store_true")
    parser.add_argument(
        "--history-media-policy",
        choices=["full", "smart", "current-turn-only", "answers-only"],
        default=os.getenv("CLBENCH_HISTORY_MEDIA_POLICY", "full"),
        help="History compaction policy forwarded to run_backend.py when applying history",
    )
    parser.add_argument(
        "--skip-existing-infer",
        action="store_true",
        help="Skip (case, infer_model) pairs whose output file already exists",
    )
    parser.add_argument(
        "--skip-existing-eval",
        action="store_true",
        help="Skip (case, eval_model) pairs whose output file already exists",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--claude-api-url", default="")
    parser.add_argument("--summary-path", default="")
    parser.add_argument(
        "--infer-models",
        default="",
        help="Comma-separated override for INFER_MODELS (uses names as-is)",
    )
    parser.add_argument(
        "--eval-models",
        default="",
        help="Comma-separated override for EVAL_MODELS",
    )
    return parser.parse_args(argv)


def discover_cases(input_root: Path, namespace: str = "") -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    for child in sorted(input_root.iterdir(), key=lambda p: p.name):
        if not child.is_file() or child.suffix not in {".json", ".jsonl"}:
            continue
        stem = child.stem
        if stem.startswith("batch_summary_"):
            continue
        if stem.endswith("_result"):
            continue
        media_candidate = input_root / stem
        media_path = media_candidate if media_candidate.exists() else None
        result_dir = input_root / f"{stem}_result"
        cases.append(
            CaseSpec(
                name=stem,
                json_path=child.resolve(),
                media_path=media_path.resolve() if media_path else None,
                result_dir=result_dir.resolve(),
                case_id=f"{namespace}_{stem}" if namespace else stem,
                input_root=input_root.resolve(),
            )
        )
    return cases


def discover_case_roots(
    input_root: Path,
    recursive_first_level: bool,
    include_roots_raw: str = "",
) -> list[Path]:
    include_roots = {
        item.strip()
        for item in include_roots_raw.split(",")
        if item.strip()
    }
    if not recursive_first_level:
        return [input_root]

    roots: list[Path] = []
    for child in sorted(input_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if include_roots and child.name not in include_roots:
            continue
        if discover_cases(child):
            roots.append(child)
    return roots


def discover_cases_for_args(args: argparse.Namespace, input_root: Path) -> list[CaseSpec]:
    roots = discover_case_roots(
        input_root,
        bool(args.recursive_first_level),
        str(args.include_roots),
    )
    cases: list[CaseSpec] = []
    for root in roots:
        namespace = root.name if args.recursive_first_level else ""
        cases.extend(discover_cases(root, namespace=namespace))
    return cases


def infer_output_path(case: CaseSpec, infer_model: str) -> Path:
    name = f"infer_{sanitize_filename_part(case.name)}_{sanitize_filename_part(infer_model)}.json"
    return case.result_dir / name


def make_eval_status_key(eval_model: str, infer_model: str) -> str:
    return f"{eval_model}__{infer_model}"


def eval_output_path(case: CaseSpec, eval_model: str, infer_model: str) -> Path:
    name = (
        f"eval_{sanitize_filename_part(case.name)}_"
        f"{sanitize_filename_part(eval_model)}_"
        f"{sanitize_filename_part(infer_model)}.json"
    )
    return case.result_dir / name


def common_backend_flags(args: argparse.Namespace) -> list[str]:
    flags: list[str] = []
    if args.api_key:
        flags += ["--api-key", args.api_key]
    if args.base_url:
        flags += ["--base-url", args.base_url]
    if args.claude_api_url:
        flags += ["--claude-api-url", args.claude_api_url]
    if args.dry_run:
        flags.append("--dry-run")
    return flags


def run_infer_for_case(
    case: CaseSpec,
    infer_model: str,
    args: argparse.Namespace,
) -> tuple[Path, int, bool]:
    out_path = infer_output_path(case, infer_model)
    if args.skip_existing_infer and out_path.exists():
        print(f"  [skip] infer already exists: {out_path.name}", flush=True)
        return out_path, 0, True

    cmd = [args.python_bin, str(RUN_BACKEND_PATH), str(case.json_path)]
    if case.media_path is not None:
        cmd.append(str(case.media_path))
    cmd += [
        "--stage", "infer",
        "--infer-model", infer_model,
        "--judge-model", EVAL_MODELS[0],
        "--infer-workers", str(args.infer_workers),
        "--eval-workers", str(args.eval_workers),
        "--max-retries", str(args.max_retries),
        "--infer-output", str(out_path),
        "--log-dir", str(case.result_dir / "logs"),
        "--grade-log-dir", str(case.result_dir / "grade_logs"),
    ]
    if args.limit > 0:
        cmd += ["--limit", str(args.limit)]
    if args.apply_history:
        cmd.append("--apply-history")
        cmd += ["--history-media-policy", args.history_media_policy]
    cmd += common_backend_flags(args)

    case.result_dir.mkdir(parents=True, exist_ok=True)
    (case.result_dir / "logs").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(cmd, cwd=str(APP_DIR))
    return out_path, completed.returncode, False


def load_any(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in f if line.strip()]
        obj = json.load(f)
    return obj if isinstance(obj, list) else [obj]


def get_item_task_id(item: dict[str, Any], fallback_idx: int) -> str:
    metadata = item.get("metadata", {})
    task_id = metadata.get("task_id")
    if task_id not in {None, ""}:
        return str(task_id)
    item_idx = item.get("idx")
    if item_idx not in {None, ""}:
        return str(item_idx)
    return str(fallback_idx)


def summarize_failure_reasons(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        reason = str(item.get("failure_reason", "")).strip() or str(item.get("error", "")).strip()
        if not reason:
            reason = "unknown failure reason"
        counts[reason] = counts.get(reason, 0) + 1
    return [
        {"failure_reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def build_process_failure_reason(
    stage_name: str,
    path: Path,
    return_code: int | None = None,
    read_error: str = "",
) -> str:
    details: list[str] = []
    if return_code not in {None, 0}:
        details.append(f"{stage_name} command exited with code {return_code}")
    if read_error:
        details.append(f"failed to read {stage_name} output file {path}: {read_error}")
    elif return_code not in {None, 0} and not path.exists():
        details.append(f"{stage_name} output file was not generated: {path}")
    return "; ".join(details)


def inspect_infer_output(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "output_exists": path.exists(),
        "output_rows": 0,
        "read_error": "",
        "process_failure_reason": "",
        "failed_count": 0,
        "failed_items": [],
        "failure_reason_summary": [],
    }
    if not path.exists():
        return info

    try:
        items = load_any(path)
    except Exception as exc:
        info["read_error"] = str(exc)
        info["process_failure_reason"] = (
            f"failed to read infer output file {path}: {info['read_error']}"
        )
        return info

    failed_items: list[dict[str, Any]] = []
    for row_index, item in enumerate(items):
        error = str(item.get("infer_error", "")).strip()
        if not error:
            continue
        failed_items.append(
            {
                "task_id": get_item_task_id(item, row_index),
                "row_index": row_index,
                "failure_reason": error,
                "error": error,
            }
        )

    info["output_rows"] = len(items)
    info["failed_count"] = len(failed_items)
    info["failed_items"] = failed_items
    info["failure_reason_summary"] = summarize_failure_reasons(failed_items)
    return info


def inspect_eval_output(path: Path, eval_model: str, infer_model: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "output_exists": path.exists(),
        "output_rows": 0,
        "read_error": "",
        "process_failure_reason": "",
        "failed_count": 0,
        "failed_items": [],
        "failure_reason_summary": [],
    }
    if not path.exists():
        return info

    try:
        items = load_any(path)
    except Exception as exc:
        info["read_error"] = str(exc)
        info["process_failure_reason"] = (
            f"failed to read eval output file {path}: {info['read_error']}"
        )
        return info

    failed_items: list[dict[str, Any]] = []
    for row_index, item in enumerate(items):
        error = str(item.get("eval_error", "")).strip()
        if not error:
            continue
        current_infer_model = str(item.get("infer_model", "")).strip() or infer_model
        item_info = {
            "task_id": get_item_task_id(item, row_index),
            "row_index": row_index,
            "failure_reason": error,
            "error": error,
        }
        failed_items.append({"infer_model": current_infer_model, **item_info})

    info["output_rows"] = len(items)
    info["failed_count"] = len(failed_items)
    info["failed_items"] = failed_items
    info["failure_reason_summary"] = summarize_failure_reasons(failed_items)
    return info


def init_case_summary(case: CaseSpec) -> dict[str, Any]:
    return {
        "case": case.display_name,
        "case_name": case.name,
        "input_root": str(case.input_root or case.json_path.parent),
        "json_path": str(case.json_path),
        "media_path": str(case.media_path) if case.media_path is not None else "",
        "result_dir": str(case.result_dir),
        "merged_rows": 0,
        "missing_infer_models": [],
        "infer_outputs": {},
        "infer_run_status": {},
        "eval_outputs": {},
        "eval_run_status": {},
    }


def record_infer_status(
    case_summary: dict[str, Any],
    infer_model: str,
    out_path: Path,
    return_code: int | None,
    used_existing_output: bool,
) -> dict[str, Any]:
    inspection = inspect_infer_output(out_path)
    status = {
        "output_path": str(out_path),
        "return_code": return_code,
        "used_existing_output": used_existing_output,
        **inspection,
    }
    status["process_failure_reason"] = build_process_failure_reason(
        "infer",
        out_path,
        return_code=return_code,
        read_error=str(status.get("read_error", "")),
    ) or str(status.get("process_failure_reason", ""))
    case_summary["infer_outputs"][infer_model] = str(out_path)
    case_summary["infer_run_status"][infer_model] = status
    return status


def record_eval_status(
    case_summary: dict[str, Any],
    eval_model: str,
    infer_model: str,
    out_path: Path,
    return_code: int | None,
    used_existing_output: bool,
) -> dict[str, Any]:
    inspection = inspect_eval_output(out_path, eval_model, infer_model)
    status = {
        "eval_model": eval_model,
        "infer_model": infer_model,
        "output_path": str(out_path),
        "return_code": return_code,
        "used_existing_output": used_existing_output,
        **inspection,
    }
    status["process_failure_reason"] = build_process_failure_reason(
        "eval",
        out_path,
        return_code=return_code,
        read_error=str(status.get("read_error", "")),
    ) or str(status.get("process_failure_reason", ""))
    status_key = make_eval_status_key(eval_model, infer_model)
    case_summary["eval_outputs"][status_key] = str(out_path)
    case_summary["eval_run_status"][status_key] = status
    return status


def infer_status_has_failure(status: dict[str, Any]) -> bool:
    return bool(
        status.get("failed_count")
        or status.get("read_error")
        or status.get("return_code") not in {None, 0}
    )


def eval_status_has_failure(status: dict[str, Any]) -> bool:
    return bool(
        status.get("failed_count")
        or status.get("read_error")
        or status.get("return_code") not in {None, 0}
    )


def ensure_infer_statuses(
    case_summary: dict[str, Any],
    case: CaseSpec,
    infer_models: list[str],
) -> None:
    for infer_model in infer_models:
        if infer_model in case_summary["infer_run_status"]:
            continue
        out_path = infer_output_path(case, infer_model)
        record_infer_status(
            case_summary,
            infer_model,
            out_path,
            return_code=None,
            used_existing_output=out_path.exists(),
        )


def build_case_infer_failures(case_summary: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for infer_model, status in case_summary["infer_run_status"].items():
        if not infer_status_has_failure(status):
            continue
        failures.append(
            {
                "infer_model": infer_model,
                "return_code": status.get("return_code"),
                "read_error": status.get("read_error", ""),
                "process_failure_reason": status.get("process_failure_reason", ""),
                "failed_count": status.get("failed_count", 0),
                "failed_items": status.get("failed_items", []),
                "failure_reason_summary": status.get("failure_reason_summary", []),
            }
        )
    return failures


def build_case_eval_failures(case_summary: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for _status_key, status in case_summary["eval_run_status"].items():
        if not eval_status_has_failure(status):
            continue
        failures.append(
            {
                "eval_model": status.get("eval_model"),
                "infer_model": status.get("infer_model"),
                "return_code": status.get("return_code"),
                "read_error": status.get("read_error", ""),
                "process_failure_reason": status.get("process_failure_reason", ""),
                "failed_count": status.get("failed_count", 0),
                "failed_items": status.get("failed_items", []),
                "failure_reason_summary": status.get("failure_reason_summary", []),
            }
        )
    return failures


def build_eval_input_for_infer(case: CaseSpec, infer_model: str) -> tuple[Path | None, int]:
    rows: list[dict[str, Any]] = []
    path = infer_output_path(case, infer_model)
    if not path.exists():
        return None, 0
    try:
        items = load_any(path)
    except Exception as exc:
        print(f"  [warn] failed to read {path}: {exc}", flush=True)
        return None, 0
    for item in items:
        tagged = dict(item)
        tagged["infer_model"] = infer_model
        tagged["case_name"] = case.name
        rows.append(tagged)
    if not rows:
        return None, 0
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        prefix=f"eval_input_{sanitize_filename_part(case.name)}_{sanitize_filename_part(infer_model)}_",
        dir=str(case.result_dir),
        delete=False,
        encoding="utf-8",
    )
    try:
        for row in rows:
            tmp.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        tmp.close()
    return Path(tmp.name), len(rows)


def run_eval_for_case(
    case: CaseSpec,
    eval_model: str,
    infer_model: str,
    merged_path: Path,
    args: argparse.Namespace,
) -> tuple[Path, int, bool]:
    out_path = eval_output_path(case, eval_model, infer_model)
    if args.skip_existing_eval and out_path.exists():
        print(f"  [skip] eval already exists: {out_path.name}", flush=True)
        return out_path, 0, True

    cmd = [args.python_bin, str(RUN_BACKEND_PATH), str(merged_path)]
    if case.media_path is not None:
        cmd.append(str(case.media_path))
    cmd += [
        "--stage", "eval",
        "--infer-model", infer_model,
        "--judge-model", eval_model,
        "--infer-workers", str(args.infer_workers),
        "--eval-workers", str(args.eval_workers),
        "--max-retries", str(args.max_retries),
        "--eval-output", str(out_path),
        "--log-dir", str(case.result_dir / "logs"),
        "--grade-log-dir", str(case.result_dir / "grade_logs"),
    ]
    if args.apply_history:
        cmd.append("--apply-history")
        cmd += ["--history-media-policy", args.history_media_policy]
    cmd += common_backend_flags(args)

    (case.result_dir / "grade_logs").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(cmd, cwd=str(APP_DIR))
    return out_path, completed.returncode, False


def get_summary_path(input_root: Path, raw: str) -> Path:
    if raw:
        return Path(raw).resolve()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (input_root / f"batch_summary_{ts}.json").resolve()


def bounded_workers(requested: int, total_jobs: int) -> int:
    if total_jobs <= 0:
        return 1
    return max(1, min(requested, total_jobs))


def run_infer_stage_for_case(
    c_idx: int,
    total_cases: int,
    case: CaseSpec,
    case_summary: dict[str, Any],
    infer_models: list[str],
    args: argparse.Namespace,
) -> bool:
    case_failed = False
    print(f"\n[case {c_idx}/{total_cases}] {case.display_name}", flush=True)
    infer_parallelism = bounded_workers(args.infer_model_workers, len(infer_models))
    print(
        f"  infer model parallelism={infer_parallelism} across {len(infer_models)} model(s)",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=infer_parallelism) as executor:
        futures = {}
        for m_idx, infer_model in enumerate(infer_models, start=1):
            print(
                f"  -> infer [{m_idx}/{len(infer_models)}] {infer_model}",
                flush=True,
            )
            futures[executor.submit(run_infer_for_case, case, infer_model, args)] = infer_model

        for future in as_completed(futures):
            infer_model = futures[future]
            try:
                out_path, rc, used_existing_output = future.result()
            except Exception as exc:
                case_failed = True
                print(f"     infer crashed [{case.display_name} / {infer_model}]: {exc}", flush=True)
                out_path = infer_output_path(case, infer_model)
                rc = 1
                used_existing_output = out_path.exists()
            status = record_infer_status(
                case_summary,
                infer_model,
                out_path,
                return_code=rc,
                used_existing_output=used_existing_output,
            )
            if rc not in (0,):
                case_failed = True
                print(f"     infer returned {rc} [{case.display_name} / {infer_model}]", flush=True)
            if infer_status_has_failure(status):
                case_failed = True

    return case_failed


def run_infer_stage_global(
    cases: list[CaseSpec],
    case_summary_map: dict[str, dict[str, Any]],
    infer_models: list[str],
    args: argparse.Namespace,
) -> bool:
    had_failure = False
    total_jobs = len(cases) * len(infer_models)
    job_parallelism = bounded_workers(
        args.case_workers * args.infer_model_workers,
        total_jobs,
    )
    print(
        f"Infer job parallelism={job_parallelism} across {total_jobs} case-model job(s) "
        f"({len(cases)} case(s) x {len(infer_models)} model(s))",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=job_parallelism) as executor:
        futures = {}
        job_idx = 0
        for c_idx, case in enumerate(cases, start=1):
            print(f"\n[case {c_idx}/{len(cases)}] {case.display_name}", flush=True)
            for m_idx, infer_model in enumerate(infer_models, start=1):
                job_idx += 1
                print(
                    f"  -> infer job [{job_idx}/{total_jobs}] "
                    f"[{m_idx}/{len(infer_models)}] {case.display_name} / {infer_model}",
                    flush=True,
                )
                futures[executor.submit(run_infer_for_case, case, infer_model, args)] = (
                    case,
                    infer_model,
                )

        done_jobs = 0
        for future in as_completed(futures):
            case, infer_model = futures[future]
            try:
                out_path, rc, used_existing_output = future.result()
            except Exception as exc:
                had_failure = True
                print(f"     infer crashed [{case.display_name} / {infer_model}]: {exc}", flush=True)
                out_path = infer_output_path(case, infer_model)
                rc = 1
                used_existing_output = out_path.exists()

            status = record_infer_status(
                case_summary_map[case.display_name],
                infer_model,
                out_path,
                return_code=rc,
                used_existing_output=used_existing_output,
            )
            if rc not in (0,):
                had_failure = True
                print(f"     infer returned {rc} [{case.display_name} / {infer_model}]", flush=True)
            if infer_status_has_failure(status):
                had_failure = True
            done_jobs += 1
            print(
                f"  infer job done ({done_jobs}/{total_jobs}) "
                f"{case.display_name} / {infer_model}",
                flush=True,
            )

    return had_failure


def run_eval_stage_for_case(
    c_idx: int,
    total_cases: int,
    case: CaseSpec,
    case_summary: dict[str, Any],
    infer_models: list[str],
    eval_models: list[str],
    args: argparse.Namespace,
) -> bool:
    case_failed = False
    print(f"\n[case {c_idx}/{total_cases}] {case.display_name}", flush=True)
    ensure_infer_statuses(case_summary, case, infer_models)
    available_infer_models: list[str] = []
    missing: list[str] = []
    total_rows = 0
    for infer_model in infer_models:
        infer_path = infer_output_path(case, infer_model)
        if infer_path.exists():
            available_infer_models.append(infer_model)
            try:
                total_rows += len(load_any(infer_path))
            except Exception:
                pass
        else:
            missing.append(infer_model)
    case_summary["merged_rows"] = total_rows
    case_summary["missing_infer_models"] = missing
    if missing:
        print(
            f"  [warn] missing infer outputs for {case.display_name}: {', '.join(missing)}",
            flush=True,
        )
    if not available_infer_models:
        print(f"  [skip] no infer output available for {case.display_name}, skipping eval", flush=True)
        return case_failed

    print(
        f"  found {total_rows} item-rows across {len(available_infer_models)} infer model(s)",
        flush=True,
    )
    eval_inputs: list[tuple[str, Path, int]] = []
    for infer_model in available_infer_models:
        merged_path, infer_rows = build_eval_input_for_infer(case, infer_model)
        if not merged_path:
            print(f"  [skip] no eval input generated for {case.display_name} / {infer_model}", flush=True)
            continue
        eval_inputs.append((infer_model, merged_path, infer_rows))
        print(
            f"  infer input [{case.display_name} / {infer_model}] rows={infer_rows}",
            flush=True,
        )

    eval_jobs: list[tuple[str, str, Path]] = []
    for infer_model, merged_path, _infer_rows in eval_inputs:
        for m_idx, eval_model in enumerate(eval_models, start=1):
            print(
                f"  -> eval [{m_idx}/{len(eval_models)}] {eval_model} on {case.display_name} / {infer_model}",
                flush=True,
            )
            eval_jobs.append((eval_model, infer_model, merged_path))

    eval_parallelism = bounded_workers(args.eval_model_workers, len(eval_jobs))
    print(
        f"  eval job parallelism={eval_parallelism} across {len(eval_jobs)} job(s)",
        flush=True,
    )
    try:
        with ThreadPoolExecutor(max_workers=eval_parallelism) as executor:
            futures = {}
            for eval_model, infer_model, merged_path in eval_jobs:
                futures[
                    executor.submit(
                        run_eval_for_case,
                        case,
                        eval_model,
                        infer_model,
                        merged_path,
                        args,
                    )
                ] = (eval_model, infer_model)

            for future in as_completed(futures):
                eval_model, infer_model = futures[future]
                try:
                    out_path, rc, used_existing_output = future.result()
                except Exception as exc:
                    case_failed = True
                    print(
                        f"     eval crashed [{case.display_name} / {eval_model} on {infer_model}]: {exc}",
                        flush=True,
                    )
                    out_path = eval_output_path(case, eval_model, infer_model)
                    rc = 1
                    used_existing_output = out_path.exists()
                status = record_eval_status(
                    case_summary,
                    eval_model,
                    infer_model,
                    out_path,
                    return_code=rc,
                    used_existing_output=used_existing_output,
                )
                if rc not in (0,):
                    case_failed = True
                    print(
                        f"     eval returned {rc} [{case.display_name} / {eval_model} on {infer_model}]",
                        flush=True,
                    )
                if eval_status_has_failure(status):
                    case_failed = True
    finally:
        for _infer_model, merged_path, _infer_rows in eval_inputs:
            try:
                merged_path.unlink()
            except OSError:
                pass

    return case_failed


def run_eval_stage_global(
    cases: list[CaseSpec],
    case_summary_map: dict[str, dict[str, Any]],
    infer_models: list[str],
    eval_models: list[str],
    args: argparse.Namespace,
) -> bool:
    had_failure = False
    eval_jobs: list[tuple[CaseSpec, str, str, Path]] = []
    eval_inputs_for_cleanup: list[Path] = []

    for c_idx, case in enumerate(cases, start=1):
        case_summary = case_summary_map[case.display_name]
        print(f"\n[case {c_idx}/{len(cases)}] {case.display_name}", flush=True)
        ensure_infer_statuses(case_summary, case, infer_models)

        available_infer_models: list[str] = []
        missing: list[str] = []
        total_rows = 0
        for infer_model in infer_models:
            infer_path = infer_output_path(case, infer_model)
            if infer_path.exists():
                available_infer_models.append(infer_model)
                try:
                    total_rows += len(load_any(infer_path))
                except Exception:
                    pass
            else:
                missing.append(infer_model)

        case_summary["merged_rows"] = total_rows
        case_summary["missing_infer_models"] = missing
        if missing:
            print(
                f"  [warn] missing infer outputs for {case.display_name}: {', '.join(missing)}",
                flush=True,
            )
        if not available_infer_models:
            print(f"  [skip] no infer output available for {case.display_name}, skipping eval", flush=True)
            continue

        print(
            f"  found {total_rows} item-rows across {len(available_infer_models)} infer model(s)",
            flush=True,
        )
        for infer_model in available_infer_models:
            merged_path, infer_rows = build_eval_input_for_infer(case, infer_model)
            if not merged_path:
                print(f"  [skip] no eval input generated for {case.display_name} / {infer_model}", flush=True)
                continue
            eval_inputs_for_cleanup.append(merged_path)
            print(
                f"  infer input [{case.display_name} / {infer_model}] rows={infer_rows}",
                flush=True,
            )
            for m_idx, eval_model in enumerate(eval_models, start=1):
                print(
                    f"  -> eval job [{m_idx}/{len(eval_models)}] "
                    f"{eval_model} on {case.display_name} / {infer_model}",
                    flush=True,
                )
                eval_jobs.append((case, eval_model, infer_model, merged_path))

    total_jobs = len(eval_jobs)
    job_parallelism = bounded_workers(
        args.case_workers * args.eval_model_workers,
        total_jobs,
    )
    print(
        f"Eval job parallelism={job_parallelism} across {total_jobs} judge job(s) "
        f"({len(cases)} case(s) x up to {len(infer_models)} infer model(s) x {len(eval_models)} judge model(s))",
        flush=True,
    )

    try:
        with ThreadPoolExecutor(max_workers=job_parallelism) as executor:
            futures = {
                executor.submit(
                    run_eval_for_case,
                    case,
                    eval_model,
                    infer_model,
                    merged_path,
                    args,
                ): (case, eval_model, infer_model)
                for case, eval_model, infer_model, merged_path in eval_jobs
            }

            done_jobs = 0
            for future in as_completed(futures):
                case, eval_model, infer_model = futures[future]
                try:
                    out_path, rc, used_existing_output = future.result()
                except Exception as exc:
                    had_failure = True
                    print(
                        f"     eval crashed [{case.display_name} / {eval_model} on {infer_model}]: {exc}",
                        flush=True,
                    )
                    out_path = eval_output_path(case, eval_model, infer_model)
                    rc = 1
                    used_existing_output = out_path.exists()

                status = record_eval_status(
                    case_summary_map[case.display_name],
                    eval_model,
                    infer_model,
                    out_path,
                    return_code=rc,
                    used_existing_output=used_existing_output,
                )
                if rc not in (0,):
                    had_failure = True
                    print(
                        f"     eval returned {rc} [{case.display_name} / {eval_model} on {infer_model}]",
                        flush=True,
                    )
                if eval_status_has_failure(status):
                    had_failure = True
                done_jobs += 1
                print(
                    f"  eval job done ({done_jobs}/{total_jobs}) "
                    f"{case.display_name} / {eval_model} on {infer_model}",
                    flush=True,
                )
    finally:
        for merged_path in eval_inputs_for_cleanup:
            try:
                merged_path.unlink()
            except OSError:
                pass

    return had_failure


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_root = Path(args.input_root).resolve()
    if not input_root.is_dir():
        print(f"Input root is not a directory: {input_root}", file=sys.stderr)
        return 1

    infer_models = (
        [m.strip() for m in args.infer_models.split(",") if m.strip()]
        if args.infer_models
        else INFER_MODELS
    )
    eval_models = (
        [m.strip() for m in args.eval_models.split(",") if m.strip()]
        if args.eval_models
        else EVAL_MODELS
    )

    cases = discover_cases_for_args(args, input_root)
    if not cases:
        print(f"No .json/.jsonl cases found in {input_root}", file=sys.stderr)
        return 1

    print(
        f"Discovered {len(cases)} case(s); "
        f"infer models={len(infer_models)}, eval models={len(eval_models)}",
        flush=True,
    )
    if args.recursive_first_level:
        roots = sorted({str(case.input_root or case.json_path.parent) for case in cases})
        print(
            f"Recursive first-level scheduling across {len(roots)} input root(s):",
            flush=True,
        )
        for root in roots:
            print(f"  - {root}", flush=True)

    summary: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_root": str(input_root),
        "recursive_first_level": bool(args.recursive_first_level),
        "include_roots": [
            item.strip()
            for item in str(args.include_roots).split(",")
            if item.strip()
        ],
        "stage": args.stage,
        "case_workers": args.case_workers,
        "infer_workers": args.infer_workers,
        "eval_workers": args.eval_workers,
        "infer_model_workers": args.infer_model_workers,
        "eval_model_workers": args.eval_model_workers,
        "max_retries": args.max_retries,
        "infer_models": infer_models,
        "eval_models": eval_models,
        "infer_failures": [],
        "eval_failures": [],
        "cases": [init_case_summary(case) for case in cases],
    }
    case_summary_map = {
        case_summary["case"]: case_summary
        for case_summary in summary["cases"]
    }
    had_failure = False

    do_infer = args.stage in {"full", "infer"}
    do_eval = args.stage in {"full", "eval"}

    # ---- Inference stage: all cases x all infer models ----
    if do_infer:
        print("\n=== Inference stage ===", flush=True)
        if run_infer_stage_global(cases, case_summary_map, infer_models, args):
            had_failure = True

    # ---- Evaluation stage: merge per case, judge with each eval model ----
    if do_eval:
        print("\n=== Evaluation stage ===", flush=True)
        if run_eval_stage_global(cases, case_summary_map, infer_models, eval_models, args):
            had_failure = True

    for case_summary in summary["cases"]:
        case_infer_failures = build_case_infer_failures(case_summary)
        case_eval_failures = build_case_eval_failures(case_summary)
        case_summary["infer_failures"] = case_infer_failures
        case_summary["eval_failures"] = case_eval_failures

        for failure in case_infer_failures:
            summary["infer_failures"].append(
                {
                    "case": case_summary["case"],
                    **failure,
                }
            )
        for failure in case_eval_failures:
            summary["eval_failures"].append(
                {
                    "case": case_summary["case"],
                    **failure,
                }
            )

    if summary["infer_failures"] or summary["eval_failures"]:
        had_failure = True
    summary["had_failure"] = had_failure

    summary_path = get_summary_path(input_root, args.summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nBatch finished. summary: {summary_path}", flush=True)
    return 2 if had_failure else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
