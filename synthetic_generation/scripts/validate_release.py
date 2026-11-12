from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import read_json
from models import EvolvedCase, ReleaseBundle
from validators import (
    validate_case,
    validate_evolution,
    validate_human_release,
    validate_improvement,
    validate_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one release bundle and report its acceptance state."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Root used to resolve relative source-asset paths in the bundle.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "release.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = read_json(args.config)
    bundle = ReleaseBundle.model_validate(read_json(args.bundle))
    allowed = set(config["allowed_datasets"])
    source_root = args.source_root.expanduser().resolve()
    evolved_view = EvolvedCase(
        protocol_version=bundle.improved.protocol_version,
        case=bundle.improved.case,
        mutation_log=bundle.improved.mutation_log,
    )
    defects = (
        validate_case(bundle.improved.case, allowed, asset_root=source_root)
        + validate_evolution(
            evolved_view, config["required_mutation_families_min"]
        )
        + validate_improvement(bundle.improved)
        + validate_reports(
            bundle.final_critic,
            bundle.final_ablation,
            bundle.improved.case,
        )
    )
    blocking = [
        item.model_dump(mode="json")
        for item in defects
        if item.severity in {"critical", "major"}
    ]
    human_failures = validate_human_release(
        bundle.human_reviews, bundle.human_adjudication
    )
    accepted = not blocking and not human_failures
    report = {
        "case_id": bundle.improved.case.case_id,
        "machine_gate": "pass" if not blocking else "fail",
        "blocking_defects": blocking,
        "human_gate": "pass" if not human_failures else "pending_or_fail",
        "human_failures": human_failures,
        "release_status": "accepted" if accepted else "not_accepted",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
