from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from common import (
    canonical_json,
    image_data_url,
    read_json,
    render_template,
    sha256_file,
    sha256_text,
    write_json,
)
from models import (
    AblationReport,
    CandidateSpec,
    ConstructedCase,
    Defect,
    DefectReport,
    EvolvedCase,
    ImprovedCase,
    ReleaseBundle,
    SourceCard,
    StageRun,
    UsageRecord,
)
from validators import (
    validate_case,
    validate_evolution,
    validate_improvement,
    validate_reports,
)


ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T", bound=BaseModel)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one audited synthetic case with the GPT-5.5 API."
    )
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config" / "release.json"
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Root containing the slideVQA and mmlongbench-doc directories.",
    )
    return parser.parse_args()


def resolve_asset_path(raw_path: str, source_root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = source_root / path
    return path.resolve()


def hydrate_source_hashes(source: SourceCard, source_root: Path) -> SourceCard:
    payload = source.model_dump(mode="json")
    for asset in payload["selected_assets"]:
        path = resolve_asset_path(asset["path"], source_root)
        if not path.is_file():
            raise FileNotFoundError(f"Source asset not found: {path}")
        actual = sha256_file(path)
        recorded = asset["sha256"]
        if recorded in {"", "COMPUTED_BY_SCRIPT"}:
            asset["sha256"] = actual
        elif recorded != actual:
            raise ValueError(
                f"Source hash mismatch for {path}: recorded={recorded}, actual={actual}"
            )
    return SourceCard.model_validate(payload)


def response_usage(response: object) -> UsageRecord:
    usage = getattr(response, "usage", None)
    if usage is None:
        return UsageRecord(input_tokens=None, output_tokens=None, total_tokens=None)
    return UsageRecord(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


class ApiRunner:
    def __init__(self, config_path: Path, output_dir: Path):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is missing. Run: pip install -r requirements.txt"
            ) from exc
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self.client = OpenAI()
        self.config_path = config_path.resolve()
        self.config = read_json(self.config_path)
        self.config_hash = sha256_file(self.config_path)
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stage_runs: list[StageRun] = []

    @staticmethod
    def public_prompt_path(prompt_path: Path) -> str:
        resolved = prompt_path.resolve()
        try:
            return resolved.relative_to(ROOT).as_posix()
        except ValueError:
            return f"prompts/{resolved.name}"

    def call(
        self,
        stage: str,
        prompt_path: Path,
        replacements: dict[str, str],
        assets: list[Path],
        output_model: type[T],
    ) -> T:
        prompt = render_template(prompt_path, replacements)
        prompt_hash = sha256_text(prompt)
        stage_dir = self.output_dir / "stages" / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "rendered_prompt.md").write_text(prompt, encoding="utf-8")

        user_content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": "Use the attached locked source assets when verifying evidence.",
            }
        ]
        for asset in assets:
            user_content.append(
                {"type": "input_image", "image_url": image_data_url(asset)}
            )

        response = self.client.responses.parse(
            model=self.config["model"],
            reasoning={"effort": self.config["reasoning_effort"]},
            store=self.config["store"],
            input=[
                {"role": "developer", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            text_format=output_model,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError(f"Stage {stage} returned no parsed structured output.")
        output_path = stage_dir / "output.json"
        write_json(output_path, parsed)
        self.stage_runs.append(
            StageRun(
                stage=stage,
                model=self.config["model"],
                response_id=response.id,
                prompt_path=self.public_prompt_path(prompt_path),
                prompt_sha256=prompt_hash,
                config_sha256=self.config_hash,
                asset_sha256={
                    f"asset-{index:03d}:{path.name}": sha256_file(path)
                    for index, path in enumerate(assets, start=1)
                },
                usage=response_usage(response),
                output_path=output_path.relative_to(self.output_dir).as_posix(),
            )
        )
        return parsed


def critical_or_major(defects: list[Defect]) -> list[Defect]:
    return [item for item in defects if item.severity in {"critical", "major"}]


def should_retry_improvement(
    defects: list[Defect], attempt: int, maximum_attempts: int
) -> bool:
    blocking = critical_or_major(defects)
    return (
        bool(blocking)
        and attempt < maximum_attempts
        and all(item.recommended_route == "self_improve" for item in blocking)
    )


def immutable_source_defect(
    before: SourceCard, after: SourceCard, stage: str
) -> list[Defect]:
    if canonical_json(before.model_dump(mode="json")) == canonical_json(
        after.model_dump(mode="json")
    ):
        return []
    return [
        Defect(
            defect_code="IMMUTABLE_SOURCE_CHANGED",
            severity="critical",
            affected_object_ids=[before.source_id],
            description=f"{stage} changed the locked source card.",
            evidence="Canonical source-card values differ before and after the stage.",
            recommended_route="discard",
        )
    ]


def run() -> int:
    args = parse_args()
    candidate_payload = read_json(args.candidate)
    candidate = CandidateSpec.model_validate(candidate_payload)
    source_root = args.source_root.expanduser().resolve()
    candidate.source_card = hydrate_source_hashes(candidate.source_card, source_root)
    config = read_json(args.config)
    allowed = set(config["allowed_datasets"])
    assets = [
        resolve_asset_path(item.path, source_root)
        for item in candidate.source_card.selected_assets
    ]
    runner = ApiRunner(args.config, args.output_dir)

    construct_payload = candidate.model_dump(mode="json")
    constructed: ConstructedCase | None = None
    construct_defects: list[Defect] = []
    for attempt in range(1, config["max_repair_iterations"] + 1):
        if construct_defects:
            construct_payload["validation_defects"] = [
                item.model_dump(mode="json") for item in construct_defects
            ]
        constructed = runner.call(
            f"01_self_construct_attempt_{attempt}",
            ROOT / "prompts" / "01_self_construct.md",
            {"candidate_json": json.dumps(construct_payload, ensure_ascii=False, indent=2)},
            assets,
            ConstructedCase,
        )
        construct_defects = validate_case(
            constructed.case, allowed, asset_root=source_root
        )
        construct_defects += immutable_source_defect(
            candidate.source_card, constructed.case.source_card, "Self-Construct"
        )
        if not critical_or_major(construct_defects):
            break
    if constructed is None or critical_or_major(construct_defects):
        write_json(args.output_dir / "construct_failures.json", construct_defects)
        print("Self-Construct failed its gate; see construct_failures.json.", file=sys.stderr)
        return 2

    evolve_payload = constructed.model_dump(mode="json")
    evolved: EvolvedCase | None = None
    evolve_defects: list[Defect] = []
    for attempt in range(1, config["max_repair_iterations"] + 1):
        if evolve_defects:
            evolve_payload["validation_defects"] = [
                item.model_dump(mode="json") for item in evolve_defects
            ]
        evolved = runner.call(
            f"02_self_evolve_attempt_{attempt}",
            ROOT / "prompts" / "02_self_evolve.md",
            {
                "constructed_case_json": json.dumps(
                    evolve_payload, ensure_ascii=False, indent=2
                )
            },
            assets,
            EvolvedCase,
        )
        evolve_defects = validate_case(
            evolved.case, allowed, asset_root=source_root
        )
        evolve_defects += validate_evolution(
            evolved, config["required_mutation_families_min"]
        )
        evolve_defects += immutable_source_defect(
            constructed.case.source_card, evolved.case.source_card, "Self-Evolve"
        )
        if not critical_or_major(evolve_defects):
            break
    if evolved is None or critical_or_major(evolve_defects):
        write_json(args.output_dir / "evolve_failures.json", evolve_defects)
        print("Self-Evolve failed its gate; see evolve_failures.json.", file=sys.stderr)
        return 2

    pre_critic = runner.call(
        "03a_pre_improve_critic",
        ROOT / "prompts" / "05_release_critic.md",
        {"case_json": json.dumps(evolved.model_dump(mode="json"), ensure_ascii=False, indent=2)},
        assets,
        DefectReport,
    )
    pre_ablation = runner.call(
        "03b_pre_improve_ablation",
        ROOT / "prompts" / "04_ablation_audit.md",
        {"case_json": json.dumps(evolved.model_dump(mode="json"), ensure_ascii=False, indent=2)},
        assets,
        AblationReport,
    )
    repair_defects = (
        validate_case(evolved.case, allowed, asset_root=source_root)
        + validate_evolution(evolved, config["required_mutation_families_min"])
        + validate_reports(pre_critic, pre_ablation, evolved.case)
    )

    current_evolved = evolved
    pending_defects = repair_defects
    accumulated_repairs = []
    improved: ImprovedCase | None = None
    final_critic: DefectReport | None = None
    final_ablation: AblationReport | None = None
    final_defects: list[Defect] = []
    for attempt in range(1, config["max_repair_iterations"] + 1):
        improved_attempt = runner.call(
            f"03_self_improve_attempt_{attempt}",
            ROOT / "prompts" / "03_self_improve.md",
            {
                "evolved_case_json": json.dumps(
                    current_evolved.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
                "defects_json": json.dumps(
                    [item.model_dump(mode="json") for item in pending_defects],
                    ensure_ascii=False,
                    indent=2,
                ),
            },
            assets,
            ImprovedCase,
        )
        accumulated_repairs.extend(improved_attempt.repair_log)
        improved_payload = improved_attempt.model_dump(mode="json")
        improved_payload["repair_log"] = [
            item.model_dump(mode="json") for item in accumulated_repairs
        ]
        improved = ImprovedCase.model_validate(improved_payload)

        final_critic = runner.call(
            f"04a_release_critic_after_improve_{attempt}",
            ROOT / "prompts" / "05_release_critic.md",
            {
                "case_json": json.dumps(
                    improved.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                )
            },
            assets,
            DefectReport,
        )
        final_ablation = runner.call(
            f"04b_ablation_after_improve_{attempt}",
            ROOT / "prompts" / "04_ablation_audit.md",
            {
                "case_json": json.dumps(
                    improved.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                )
            },
            assets,
            AblationReport,
        )
        improved_as_evolved = EvolvedCase(
            protocol_version=improved.protocol_version,
            case=improved.case,
            mutation_log=improved.mutation_log,
        )
        final_defects = (
            validate_case(improved.case, allowed, asset_root=source_root)
            + validate_evolution(
                improved_as_evolved,
                config["required_mutation_families_min"],
            )
            + validate_improvement(improved)
            + validate_reports(final_critic, final_ablation, improved.case)
            + immutable_source_defect(
                candidate.source_card, improved.case.source_card, "Self-Improve"
            )
        )
        if not critical_or_major(final_defects):
            break
        if not should_retry_improvement(
            final_defects,
            attempt,
            config["max_repair_iterations"],
        ):
            break
        current_evolved = improved_as_evolved
        pending_defects = final_defects

    if improved is None or final_critic is None or final_ablation is None:
        raise RuntimeError("Self-Improve did not produce a complete audited result.")
    machine_clean = not critical_or_major(final_defects)
    write_json(args.output_dir / "machine_validation.json", final_defects)

    bundle = ReleaseBundle(
        protocol_version=config["protocol_version"],
        constructed=constructed,
        evolved=evolved,
        pre_improve_critic=pre_critic,
        pre_improve_ablation=pre_ablation,
        improved=improved,
        final_critic=final_critic,
        final_ablation=final_ablation,
        stage_runs=runner.stage_runs,
        human_reviews=[],
        human_adjudication=None,
        release_status="pending_human_review" if machine_clean else "discard",
    )
    write_json(args.output_dir / "release_bundle.json", bundle)
    if not machine_clean:
        print("Machine release gate failed; case marked discard.", file=sys.stderr)
        return 2
    print(
        "Machine checks passed. The case remains pending until two human reviews "
        "and adjudication are attached."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
