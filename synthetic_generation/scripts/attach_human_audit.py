from __future__ import annotations

import argparse
from pathlib import Path

from common import read_json, write_json
from models import HumanAdjudication, HumanReview, ReleaseBundle
from validators import validate_human_release


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach two human reviews and adjudication to a release bundle."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = ReleaseBundle.model_validate(read_json(args.bundle))
    reviews = [HumanReview.model_validate(read_json(path)) for path in args.review]
    adjudication = HumanAdjudication.model_validate(read_json(args.adjudication))
    case_id = bundle.improved.case.case_id
    if any(review.case_id != case_id for review in reviews):
        raise ValueError("A human review case_id does not match the release bundle.")
    if adjudication.case_id != case_id:
        raise ValueError("Adjudication case_id does not match the release bundle.")
    failures = validate_human_release(reviews, adjudication)
    bundle.human_reviews = reviews
    bundle.human_adjudication = adjudication
    bundle.release_status = "accepted" if not failures else "discard"
    write_json(args.output, bundle)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 2
    print(f"Human gate passed for {case_id}; wrote accepted bundle to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

