from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from common import sha256_file
from export_release import public_bundle_payload
from generate_case import should_retry_improvement
from models import (
    AblationReport,
    CaseContent,
    DefectReport,
    EvolvedCase,
    HumanAdjudication,
    HumanReview,
    Defect,
)
from validators import (
    validate_case,
    validate_evolution,
    validate_human_release,
    validate_reports,
)


class OfflineProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.asset = Path(self.temp_dir.name) / "asset.png"
        self.asset.write_bytes(b"offline-test-asset")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_case(self) -> CaseContent:
        tasks = []
        claims = []
        states = []
        for index in range(1, 4):
            task_id = f"t{index}"
            gold_id = f"g{index}"
            state_id = f"s{index}"
            tasks.append(
                {
                    "task_id": task_id,
                    "turn_index": index,
                    "user_prompt": f"Solve task {index} using [IMG:asset.png].",
                    "output_schema": {"answer": "string"},
                    "depends_on_task_ids": [] if index == 1 else [f"t{index-1}"],
                    "consumes_state_ids": [] if index == 1 else [f"s{index-1}"],
                    "required_evidence_ids": ["e1"],
                    "required_rule_ids": ["r1"],
                    "rubrics": [
                        {
                            "rubric_id": f"b{index}_{rubric_index}",
                            "statement": (
                                "The response should satisfy the grounded criterion "
                                f"{rubric_index}."
                            ),
                            "evidence_ids": ["e1"],
                            "rule_ids": ["r1"],
                            "gold_claim_ids": [gold_id],
                            "critical": True,
                        }
                        for rubric_index in range(1, 5)
                    ],
                }
            )
            claims.append(
                {
                    "gold_claim_id": gold_id,
                    "task_id": task_id,
                    "claim": f"answer-{index}",
                    "evidence_ids": ["e1"],
                    "rule_ids": ["r1"],
                    "derived_from_state_ids": [] if index == 1 else [f"s{index-1}"],
                    "forbidden_visible_strings": [],
                }
            )
            states.append(
                {
                    "state_id": state_id,
                    "produced_by_task_id": task_id,
                    "value": f"state-{index}",
                    "evidence_ids": ["e1"],
                    "rule_ids": ["r1"],
                }
            )
        return CaseContent.model_validate(
            {
                "case_id": "Synthetic_Test",
                "taxonomy_category": "Rule Learning & Complex Reasoning",
                "subtype": "offline validation",
                "learning_target": "Test the protocol.",
                "source_card": {
                    "source_id": "slidevqa:test",
                    "dataset": "slidevqa",
                    "dataset_version": "test",
                    "split": "test",
                    "sample_id": "test",
                    "upstream_url": "https://github.com/nttmdlab-nlp/SlideVQA",
                    "license_or_access": "test only",
                    "redistribution_status": "review_required",
                    "source_snapshot_date": "2026-07-29",
                    "selected_assets": [
                        {
                            "asset_id": "asset-01",
                            "path": str(self.asset),
                            "sha256": sha256_file(self.asset),
                            "media_type": "image/png",
                            "page_or_image_index": "1",
                        }
                    ],
                    "source_text_fields": {},
                    "traceability_notes": "offline fixture",
                },
                "system_prompt": "Use only the case materials.",
                "evidence_context": "Inspect [IMG:asset.png]; no values are transcribed.",
                "local_rule_context": "Apply local rule r1.",
                "evidence_graph": [
                    {
                        "evidence_id": "e1",
                        "atomic_fact": "A visual fact.",
                        "modality": "visual",
                        "asset_id": "asset-01",
                        "anchor": "visible region",
                        "source_field": None,
                    }
                ],
                "rule_program": [
                    {
                        "rule_id": "r1",
                        "rule_type": "mapping",
                        "statement": "Map the visual fact to the local output.",
                        "input_ids": ["e1"],
                        "output_state": "local answer",
                    }
                ],
                "tasks": tasks,
                "hidden_gold": {
                    "intermediate_states": states,
                    "atomic_claims": claims,
                    "expected_outputs": {
                        f"t{index}": {"answer": f"answer-{index}"}
                        for index in range(1, 4)
                    },
                    "counterfactual_outcomes": {},
                },
            }
        )

    def test_valid_case_has_no_machine_defects(self) -> None:
        case = self.make_case()
        self.assertEqual(validate_case(case, {"slidevqa", "mmlongbench-doc"}), [])

    def test_relative_asset_path_is_resolved_against_source_root(self) -> None:
        source_root = Path(self.temp_dir.name) / "source"
        relative_asset = source_root / "slidevqa" / "asset.png"
        relative_asset.parent.mkdir(parents=True)
        relative_asset.write_bytes(self.asset.read_bytes())
        payload = self.make_case().model_dump(mode="json")
        payload["source_card"]["selected_assets"][0]["path"] = "slidevqa/asset.png"
        case = CaseContent.model_validate(payload)
        self.assertEqual(
            validate_case(
                case,
                {"slidevqa", "mmlongbench-doc"},
                asset_root=source_root,
            ),
            [],
        )
        defect_codes = {
            item.defect_code
            for item in validate_case(case, {"slidevqa", "mmlongbench-doc"})
        }
        self.assertIn("SOURCE_ASSET_ROOT_REQUIRED", defect_codes)

    def test_evolution_requires_two_families(self) -> None:
        case = self.make_case()
        evolved = EvolvedCase.model_validate(
            {
                "protocol_version": "1.0.0",
                "case": case.model_dump(mode="json"),
                "mutation_log": [
                    {
                        "mutation_id": "m1",
                        "family": "cross_modal_interlock",
                        "targeted_weakness": "text shortcut",
                        "changed_object_ids": ["t1"],
                        "preserved_invariants": ["source facts"],
                        "old_gold": {"t1": "answer-1"},
                        "recomputed_gold": {"t1": "answer-1"},
                        "expected_failure_mode": "no visual evidence",
                    },
                    {
                        "mutation_id": "m2",
                        "family": "state_reuse",
                        "targeted_weakness": "independent turns",
                        "changed_object_ids": ["t2"],
                        "preserved_invariants": ["source facts"],
                        "old_gold": {"t2": "answer-2"},
                        "recomputed_gold": {"t2": "answer-2"},
                        "expected_failure_mode": "lost prior state",
                    },
                ],
            }
        )
        self.assertEqual(validate_evolution(evolved), [])

    def make_reports(
        self, case: CaseContent, omit_variant: bool = False
    ) -> tuple[DefectReport, AblationReport]:
        task_reports = []
        for task in case.tasks:
            decisions = [
                {
                    "variant": "full",
                    "solvability": "solvable",
                    "controlling_information": ["complete context"],
                    "rationale": "All required evidence is available.",
                },
                {
                    "variant": "no_visual",
                    "solvability": "not_solvable",
                    "controlling_information": ["e1"],
                    "rationale": "Required visual evidence is absent.",
                },
                {
                    "variant": "no_local_rules",
                    "solvability": "not_solvable",
                    "controlling_information": ["r1"],
                    "rationale": "Required local rule is absent.",
                },
                {
                    "variant": "no_prior_state",
                    "solvability": (
                        "not_solvable"
                        if task.consumes_state_ids
                        else "not_applicable"
                    ),
                    "controlling_information": list(task.consumes_state_ids),
                    "rationale": "Prior-state dependence follows the TaskDAG.",
                },
            ]
            if omit_variant and task.task_id == "t1":
                decisions.pop()
            task_reports.append(
                {
                    "task_id": task.task_id,
                    "decisions": decisions,
                    "defect_codes": [],
                }
            )
        critic = DefectReport.model_validate(
            {
                "case_id": case.case_id,
                "checked_dimensions": ["all"],
                "defects": [],
                "recommendation": "pass",
            }
        )
        ablation = AblationReport.model_validate(
            {
                "case_id": case.case_id,
                "task_reports": task_reports,
                "defects": [],
                "recommendation": "pass",
            }
        )
        return critic, ablation

    def test_ablation_requires_all_four_variants_for_every_task(self) -> None:
        case = self.make_case()
        critic, ablation = self.make_reports(case)
        self.assertEqual(validate_reports(critic, ablation, case), [])
        critic, incomplete = self.make_reports(case, omit_variant=True)
        defect_codes = {
            item.defect_code for item in validate_reports(critic, incomplete, case)
        }
        self.assertIn("ABLATION_INCOMPLETE_VARIANT_SET", defect_codes)

    def test_self_improve_retry_budget_and_routing(self) -> None:
        repairable = Defect.model_validate(
            {
                "defect_code": "RUBRIC_FIX",
                "severity": "major",
                "affected_object_ids": ["b1"],
                "description": "Repair rubric.",
                "evidence": "Rubric is incomplete.",
                "recommended_route": "self_improve",
            }
        )
        reroute = Defect.model_validate(
            {
                "defect_code": "SOURCE_FIX",
                "severity": "critical",
                "affected_object_ids": ["asset-01"],
                "description": "Source asset is missing.",
                "evidence": "Asset is absent.",
                "recommended_route": "source_lock",
            }
        )
        self.assertTrue(should_retry_improvement([repairable], 1, 3))
        self.assertFalse(should_retry_improvement([repairable], 3, 3))
        self.assertFalse(should_retry_improvement([reroute], 1, 3))

    def test_public_bundle_export_removes_machine_paths_and_response_ids(self) -> None:
        class FakeBundle:
            def model_dump(self, mode: str) -> dict[str, object]:
                self.mode = mode
                case = {
                    "source_card": {
                        "selected_assets": [
                            {
                                "asset_id": "asset-01",
                                "path": "/local/private/source/image.png",
                            }
                        ]
                    }
                }
                return {
                    "stage_runs": [
                        {
                            "stage": "01_self_construct_attempt_1",
                            "model": "gpt-5.5",
                            "response_id": "resp_private",
                            "prompt_path": "/local/private/repo/prompts/01.md",
                            "prompt_sha256": "a",
                            "config_sha256": "b",
                            "asset_sha256": {
                                "/local/private/source/image.png": "c"
                            },
                            "usage": {},
                            "output_path": "/local/private/run/output.json",
                        }
                    ],
                    "constructed": {"case": deepcopy(case)},
                    "evolved": {"case": deepcopy(case)},
                    "improved": {"case": deepcopy(case)},
                }

        public = public_bundle_payload(
            FakeBundle(), {"asset-01": "image.png"}
        )
        rendered = str(public)
        self.assertNotIn("/local/private", rendered)
        self.assertNotIn("resp_private", rendered)
        self.assertIn("withheld_from_public_export", rendered)

    def test_human_gate_requires_two_reviews_and_adjudication(self) -> None:
        base = {
            "case_id": "Synthetic_Test",
            "blind_to_model_results": True,
            "asset_complete": "pass",
            "asset_readable": "pass",
            "answerable": "pass",
            "unique_answer": "pass",
            "gold_correct": "pass",
            "rubric_correct": "pass",
            "rubric_complete": "pass",
            "context_dependent": "pass",
            "multimodal_necessary": "pass",
            "no_shortcut": "pass",
            "notes": "",
            "decision": "pass",
        }
        reviews = [
            HumanReview.model_validate({**base, "reviewer_id": "r1"}),
            HumanReview.model_validate({**base, "reviewer_id": "r2"}),
        ]
        adjudication = HumanAdjudication.model_validate(
            {
                "case_id": "Synthetic_Test",
                "adjudicator_id": "a1",
                "reviewed_reviewer_ids": ["r1", "r2"],
                "resolved_items": [],
                "decision": "pass",
                "notes": "",
            }
        )
        self.assertEqual(validate_human_release(reviews, adjudication), [])


if __name__ == "__main__":
    unittest.main()
