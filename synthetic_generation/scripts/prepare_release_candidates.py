from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from common import read_json, sha256_file, write_json
from models import CandidateSpec


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = {
    "slidevqa": "https://github.com/nttmdlab-nlp/SlideVQA",
    "mmlongbench-doc": "https://github.com/mayubo2333/MMLongBench-Doc",
}
LEARNING_TARGETS = {
    "Rule Learning & Complex Reasoning": (
        "Infer and execute case-local rules grounded in linked visual examples."
    ),
    "Temporal Dynamics & Environmental Interaction": (
        "Maintain and update a case-local state across ordered visual steps."
    ),
    "Evidence Integration & Structured Auditing": (
        "Build a reusable evidence ledger and apply local audit rules."
    ),
    "Expert Standards & Scenario Decision-Making": (
        "Apply an explicitly provided benchmark-local standard to visual evidence."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a deterministic 189-case reference execution plan."
    )
    parser.add_argument("--formal-candidates", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--plan", type=Path, default=ROOT / "config" / "candidate_plan.json"
    )
    parser.add_argument(
        "--source-versions",
        type=Path,
        default=ROOT / "config" / "source_versions.json",
    )
    return parser.parse_args()


def normalize_dataset(raw: str) -> str:
    value = raw.strip().lower()
    if value == "slidevqa":
        return "slidevqa"
    if value == "mmlongbench-doc":
        return value
    raise ValueError(f"Unsupported dataset: {raw}")


def evenly_spaced(items: list[str], limit: int) -> list[str]:
    if len(items) <= limit:
        return items
    if limit < 2:
        return items[:limit]
    last = len(items) - 1
    indices: list[int] = []
    for position in range(limit):
        raw = round(position * last / (limit - 1))
        minimum = indices[-1] + 1 if indices else 0
        maximum = len(items) - (limit - position)
        indices.append(min(max(raw, minimum), maximum))
    return [items[index] for index in indices]


def media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")


def main() -> int:
    args = parse_args()
    plan = read_json(args.plan)
    source_versions = read_json(args.source_versions)
    source_root = args.source_root.expanduser().resolve()
    output_dir = args.output_dir.resolve()
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    snapshot_hash = sha256_file(args.formal_candidates)

    by_dataset: dict[str, list[dict[str, object]]] = defaultdict(list)
    with args.formal_candidates.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                by_dataset[normalize_dataset(record["dataset"])].append(record)

    rng = random.Random(plan["random_seed"])
    for records in by_dataset.values():
        records.sort(key=lambda item: str(item["sample_id"]))
        rng.shuffle(records)

    cursors = defaultdict(int)
    manifest: list[dict[str, object]] = []
    case_number = 1
    for allocation in plan["allocation"]:
        dataset = normalize_dataset(allocation["dataset"])
        count = int(allocation["count"])
        start = cursors[dataset]
        selected_records = by_dataset[dataset][start : start + count]
        if len(selected_records) != count:
            raise ValueError(
                f"Not enough {dataset} candidates for allocation: requested {count}"
            )
        cursors[dataset] += count

        for record in selected_records:
            case_id = f"Synthetic_{case_number:03d}"
            selected_paths = evenly_spaced(
                list(record["image_paths"]), int(plan["max_assets_per_case"])
            )
            assets = []
            for asset_index, relative_path in enumerate(selected_paths, start=1):
                local_path = source_root / relative_path
                if not local_path.is_file():
                    raise FileNotFoundError(local_path)
                assets.append(
                    {
                        "asset_id": f"asset-{asset_index:02d}",
                        "path": relative_path,
                        "sha256": sha256_file(local_path),
                        "media_type": media_type(local_path),
                        "page_or_image_index": str(asset_index),
                    }
                )

            candidate = CandidateSpec(
                case_id=case_id,
                taxonomy_category=allocation["taxonomy_category"],
                subtype=allocation["subtype"],
                learning_target=LEARNING_TARGETS[allocation["taxonomy_category"]],
                source_card={
                    "source_id": f"{dataset}:{record['sample_id']}",
                    "dataset": dataset,
                    "dataset_version": (
                        "reference-reexecution:"
                        + source_versions[dataset]["upstream_revision"]
                        + f";formal-candidates-sha256:{snapshot_hash}"
                    ),
                    "split": str(
                        record.get("split")
                        or source_versions[dataset]["default_split"]
                    ),
                    "sample_id": str(record["sample_id"]),
                    "upstream_url": UPSTREAM[dataset],
                    "license_or_access": "See upstream dataset and underlying-asset terms.",
                    "redistribution_status": "review_required",
                    "source_snapshot_date": source_versions[dataset][
                        "reference_snapshot_date"
                    ],
                    "selected_assets": assets,
                    "source_text_fields": {
                        "candidate_level": str(record.get("candidate_level", "")),
                        "text_support_status": str(
                            record.get("text_support_status", "")
                        ),
                        "filter_reasons": json.dumps(
                            record.get("reasons", []), ensure_ascii=False
                        ),
                    },
                    "traceability_notes": (
                        "Prepared deterministically from formal_candidates.jsonl; "
                        "selected pages/images are evenly spaced when the source "
                        "contains more than the configured asset cap."
                    ),
                },
                construction_constraints=[
                    "Use three to five dependent tasks.",
                    "Require visual evidence and a case-local textual rule in every task.",
                    "Do not reuse an upstream QA answer as the benchmark answer.",
                    "Include at least two controlled challenge mutations.",
                    "Keep every final claim traceable to evidence and local rules.",
                ],
            )
            candidate_path = candidates_dir / f"{case_id}.json"
            write_json(candidate_path, candidate)
            manifest.append(
                {
                    "case_id": case_id,
                    "taxonomy_category": allocation["taxonomy_category"],
                    "subtype": allocation["subtype"],
                    "dataset": dataset,
                    "sample_id": record["sample_id"],
                    "source_image_count": record["image_count"],
                    "selected_asset_count": len(assets),
                    "data_quality_score": record["data_quality_score"],
                    "caseability_score": record["caseability_score"],
                    "candidate_file": str(candidate_path.relative_to(output_dir)),
                    "generation_status": "not_run_reference_reexecution",
                    "release_bundle": "",
                    "machine_gate": "pending",
                    "human_gate": "pending",
                    "release_status": "pending",
                }
            )
            case_number += 1

    if len(manifest) != plan["total_cases"]:
        raise ValueError(
            f"Plan expected {plan['total_cases']} cases, produced {len(manifest)}"
        )
    manifest_path = output_dir / "reference_reexecution_189_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    write_json(
        output_dir / "selection_metadata.json",
        {
            "random_seed": plan["random_seed"],
            "artifact_role": "reference_execution_plan",
            "formal_candidates_sha256": snapshot_hash,
            "source_versions_file": str(args.source_versions.name),
            "source_versions_sha256": sha256_file(args.source_versions),
            "source_root_not_embedded": True,
            "case_count": len(manifest),
            "dataset_counts": {
                dataset: sum(1 for row in manifest if row["dataset"] == dataset)
                for dataset in sorted(by_dataset)
            },
            "taxonomy_counts": {
                category: sum(
                    1 for row in manifest if row["taxonomy_category"] == category
                )
                for category in LEARNING_TARGETS
            },
        },
    )
    print(f"Prepared {len(manifest)} candidates at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
