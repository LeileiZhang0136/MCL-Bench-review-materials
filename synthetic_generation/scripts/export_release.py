from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from openpyxl import Workbook

from common import read_json, write_json
from models import ReleaseBundle


HEADERS = [
    "Case_ID",
    "Sequence",
    "Role",
    "Text_Content",
    "Image_Files",
    "Video_Files",
    "Md_Files",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export accepted bundles to an MCL-Bench-compatible workbook."
    )
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="For debugging only; exported cases are not release-eligible.",
    )
    return parser.parse_args()


def resolve_asset(source_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else source_root / path


def copy_assets_and_replacements(
    bundle: ReleaseBundle, source_root: Path, output_dir: Path
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    case = bundle.improved.case
    case_dir = output_dir / "case" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    relative_paths: list[str] = []
    replacements: dict[str, str] = {}
    public_asset_paths: dict[str, str] = {}
    used_names: set[str] = set()
    for index, asset in enumerate(case.source_card.selected_assets, start=1):
        source = resolve_asset(source_root, asset.path)
        if not source.is_file():
            raise FileNotFoundError(source)
        name = source.name
        if name in used_names:
            name = f"{asset.asset_id}_{name}"
        used_names.add(name)
        destination = case_dir / name
        shutil.copy2(source, destination)
        relative_paths.append(f"./case/{case.case_id}/{name}")
        public_asset_paths[asset.asset_id] = name
        replacements[f"[IMG:{source.name}]"] = f"[IMG:{name}]"
        replacements[f"[IMG:{asset.asset_id}]"] = f"[IMG:{name}]"
    return relative_paths, replacements, public_asset_paths


def public_bundle_payload(
    bundle: ReleaseBundle,
    public_asset_paths: dict[str, str],
) -> dict[str, object]:
    """Remove machine-local paths and API identifiers from a public audit bundle."""
    payload = bundle.model_dump(mode="json")
    for stage_run in payload["stage_runs"]:
        prompt_name = Path(stage_run["prompt_path"]).name
        stage_run["prompt_path"] = f"prompts/{prompt_name}"
        stage_run["output_path"] = (
            f"stages/{stage_run['stage']}/output.json"
        )
        stage_run["asset_sha256"] = {
            f"asset-{index:03d}": digest
            for index, digest in enumerate(
                stage_run["asset_sha256"].values(), start=1
            )
        }
        stage_run["response_id"] = "withheld_from_public_export"

    for section in ("constructed", "evolved", "improved"):
        assets = payload[section]["case"]["source_card"]["selected_assets"]
        for asset in assets:
            asset["path"] = public_asset_paths.get(
                asset["asset_id"], f"{asset['asset_id']}.asset"
            )
    return payload


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    for before, after in replacements.items():
        text = text.replace(before, after)
    return text


def main() -> int:
    args = parse_args()
    source_root = args.source_root.expanduser().resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_paths = sorted(args.runs_dir.glob("*/release_bundle*.json"))
    if not bundle_paths:
        raise ValueError(f"No release bundles found under {args.runs_dir}")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "synthetic_189"
    sheet.append(HEADERS)
    exported = []
    for bundle_path in bundle_paths:
        bundle = ReleaseBundle.model_validate(read_json(bundle_path))
        if bundle.release_status != "accepted" and not args.allow_pending:
            continue
        case = bundle.improved.case
        image_files, replacements, public_asset_paths = copy_assets_and_replacements(
            bundle, source_root, output_dir
        )
        write_json(
            output_dir
            / "case"
            / case.case_id
            / "release_bundle.public.json",
            public_bundle_payload(bundle, public_asset_paths),
        )
        system = "\n\n".join(
            [
                case.system_prompt,
                "Evidence context:\n" + case.evidence_context,
                "Case-local rules:\n" + case.local_rule_context,
            ]
        )
        sheet.append(
            [
                case.case_id,
                1,
                "system",
                apply_replacements(system, replacements),
                "",
                "",
                "",
            ]
        )
        sequence = 2
        for task_index, task in enumerate(
            sorted(case.tasks, key=lambda item: item.turn_index)
        ):
            output_contract = json.dumps(
                task.output_schema, ensure_ascii=False, sort_keys=True
            )
            user = (
                apply_replacements(task.user_prompt, replacements)
                + "\n\nRequired output schema:\n"
                + output_contract
            )
            sheet.append(
                [
                    case.case_id,
                    sequence,
                    "user",
                    user,
                    "\n".join(image_files) if task_index == 0 else "",
                    "",
                    "",
                ]
            )
            sequence += 1
            rubric_text = "\n".join(
                f"{index}. {criterion.statement}"
                for index, criterion in enumerate(task.rubrics, start=1)
            )
            sheet.append(
                [case.case_id, sequence, "rubric", rubric_text, "", "", ""]
            )
            sequence += 1
        exported.append(case.case_id)

    workbook_path = output_dir / "synthetic_189_release.xlsx"
    workbook.save(workbook_path)
    (output_dir / "export_summary.json").write_text(
        json.dumps(
            {
                "exported_case_count": len(exported),
                "case_ids": exported,
                "allow_pending": args.allow_pending,
                "release_eligible": not args.allow_pending and len(exported) == 189,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(exported)} cases to {workbook_path}")
    return 0 if exported else 2


if __name__ == "__main__":
    raise SystemExit(main())
