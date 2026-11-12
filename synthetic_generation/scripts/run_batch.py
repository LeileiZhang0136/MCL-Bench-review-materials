from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the GPT-5.5 case generator with resume-safe logging."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; batch generation cannot start.", file=sys.stderr)
        return 2
    manifest_dir = args.manifest.resolve().parent
    with args.manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = rows[args.start - 1 :]
    if args.limit is not None:
        selected = selected[: args.limit]

    args.runs_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for position, row in enumerate(selected, start=args.start):
        case_id = row["case_id"]
        run_dir = args.runs_dir / case_id
        bundle = run_dir / "release_bundle.json"
        if args.resume and bundle.is_file():
            print(f"[{position}/{len(rows)}] skip {case_id}: release bundle exists")
            continue
        candidate = manifest_dir / row["candidate_file"]
        run_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "generate_case.py"),
            "--candidate",
            str(candidate),
            "--source-root",
            str(args.source_root),
            "--output-dir",
            str(run_dir),
        ]
        print(f"[{position}/{len(rows)}] generating {case_id}")
        result = subprocess.run(command, text=True, capture_output=True)
        (run_dir / "batch_stdout.log").write_text(result.stdout, encoding="utf-8")
        (run_dir / "batch_stderr.log").write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            failed += 1
            print(f"  failed with exit code {result.returncode}")
        else:
            print("  machine pipeline complete; human review still required")
    print(f"Batch finished: attempted={len(selected)}, failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

