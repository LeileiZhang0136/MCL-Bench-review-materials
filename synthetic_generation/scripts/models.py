from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Asset(StrictModel):
    asset_id: str
    path: str
    sha256: str
    media_type: str
    page_or_image_index: str


class SourceCard(StrictModel):
    source_id: str
    dataset: Literal["slidevqa", "mmlongbench-doc"]
    dataset_version: str
    split: str
    sample_id: str
    upstream_url: str
    license_or_access: str
    redistribution_status: Literal[
        "redistributable", "retrieval_only", "review_required"
    ]
    source_snapshot_date: str
    selected_assets: list[Asset]
    source_text_fields: dict[str, str]
    traceability_notes: str


class CandidateSpec(StrictModel):
    case_id: str
    taxonomy_category: Literal[
        "Rule Learning & Complex Reasoning",
        "Temporal Dynamics & Environmental Interaction",
        "Evidence Integration & Structured Auditing",
        "Expert Standards & Scenario Decision-Making",
    ]
    subtype: str
    learning_target: str
    source_card: SourceCard
    construction_constraints: list[str]


class EvidenceNode(StrictModel):
    evidence_id: str
    atomic_fact: str
    modality: Literal["visual", "text", "cross_modal"]
    asset_id: str | None
    anchor: str
    source_field: str | None


class LocalRule(StrictModel):
    rule_id: str
    rule_type: Literal[
        "definition",
        "mapping",
        "priority",
        "exception",
        "tie_break",
        "fallback",
        "transition",
        "aggregation",
    ]
    statement: str
    input_ids: list[str]
    output_state: str


class RubricCriterion(StrictModel):
    rubric_id: str
    statement: str
    evidence_ids: list[str]
    rule_ids: list[str]
    gold_claim_ids: list[str]
    critical: bool = True


class Task(StrictModel):
    task_id: str
    turn_index: int = Field(ge=1)
    user_prompt: str
    output_schema: dict[str, Any]
    depends_on_task_ids: list[str]
    consumes_state_ids: list[str]
    required_evidence_ids: list[str]
    required_rule_ids: list[str]
    rubrics: list[RubricCriterion]


class GoldClaim(StrictModel):
    gold_claim_id: str
    task_id: str
    claim: str
    evidence_ids: list[str]
    rule_ids: list[str]
    derived_from_state_ids: list[str]
    forbidden_visible_strings: list[str]


class IntermediateState(StrictModel):
    state_id: str
    produced_by_task_id: str
    value: Any
    evidence_ids: list[str]
    rule_ids: list[str]


class HiddenGold(StrictModel):
    intermediate_states: list[IntermediateState]
    atomic_claims: list[GoldClaim]
    expected_outputs: dict[str, Any]
    counterfactual_outcomes: dict[str, Any]


class CaseContent(StrictModel):
    case_id: str
    taxonomy_category: Literal[
        "Rule Learning & Complex Reasoning",
        "Temporal Dynamics & Environmental Interaction",
        "Evidence Integration & Structured Auditing",
        "Expert Standards & Scenario Decision-Making",
    ]
    subtype: str
    learning_target: str
    source_card: SourceCard
    system_prompt: str
    evidence_context: str
    local_rule_context: str
    evidence_graph: list[EvidenceNode]
    rule_program: list[LocalRule]
    tasks: list[Task]
    hidden_gold: HiddenGold


class ConstructedCase(StrictModel):
    protocol_version: str
    case: CaseContent
    construction_notes: list[str]


MutationFamily = Literal[
    "cross_modal_interlock",
    "neighbor_rule",
    "evidence_distractor",
    "counterfactual",
    "state_reuse",
    "priority_conflict",
    "missing_or_conflict_fallback",
]


class Mutation(StrictModel):
    mutation_id: str
    family: MutationFamily
    targeted_weakness: str
    changed_object_ids: list[str]
    preserved_invariants: list[str]
    old_gold: dict[str, Any]
    recomputed_gold: dict[str, Any]
    expected_failure_mode: str


class EvolvedCase(StrictModel):
    protocol_version: str
    case: CaseContent
    mutation_log: list[Mutation]


Severity = Literal["critical", "major", "minor"]


class Defect(StrictModel):
    defect_code: str
    severity: Severity
    affected_object_ids: list[str]
    description: str
    evidence: str
    recommended_route: Literal[
        "source_lock", "self_construct", "self_evolve", "self_improve", "discard"
    ]


class DefectReport(StrictModel):
    case_id: str
    checked_dimensions: list[str]
    defects: list[Defect]
    recommendation: Literal["pass", "repair", "discard"]


class Repair(StrictModel):
    repair_id: str
    defect_code: str
    affected_object_ids: list[str]
    patch_description: str
    before_value_or_hash: str
    after_value_or_hash: str
    rechecked_invariants: list[str]
    result: Literal["resolved", "unresolved"]


class ImprovedCase(StrictModel):
    protocol_version: str
    case: CaseContent
    mutation_log: list[Mutation]
    repair_log: list[Repair]
    recommended_status: Literal["machine_check", "discard"]


Solvability = Literal["solvable", "not_solvable", "uncertain", "not_applicable"]


class AblationDecision(StrictModel):
    variant: Literal["full", "no_visual", "no_local_rules", "no_prior_state"]
    solvability: Solvability
    controlling_information: list[str]
    rationale: str


class TaskAblation(StrictModel):
    task_id: str
    decisions: list[AblationDecision]
    defect_codes: list[str]


class AblationReport(StrictModel):
    case_id: str
    task_reports: list[TaskAblation]
    defects: list[Defect]
    recommendation: Literal["pass", "repair", "discard"]


class UsageRecord(StrictModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class StageRun(StrictModel):
    stage: str
    model: str
    response_id: str
    prompt_path: str
    prompt_sha256: str
    config_sha256: str
    asset_sha256: dict[str, str]
    usage: UsageRecord
    output_path: str


PassFail = Literal["pass", "fail"]


class HumanReview(StrictModel):
    case_id: str
    reviewer_id: str
    blind_to_model_results: bool
    asset_complete: PassFail
    asset_readable: PassFail
    answerable: PassFail
    unique_answer: PassFail
    gold_correct: PassFail
    rubric_correct: PassFail
    rubric_complete: PassFail
    context_dependent: PassFail
    multimodal_necessary: PassFail
    no_shortcut: PassFail
    notes: str
    decision: PassFail


class HumanAdjudication(StrictModel):
    case_id: str
    adjudicator_id: str
    reviewed_reviewer_ids: list[str]
    resolved_items: list[str]
    decision: PassFail
    notes: str


class ReleaseBundle(StrictModel):
    protocol_version: str
    constructed: ConstructedCase
    evolved: EvolvedCase
    pre_improve_critic: DefectReport
    pre_improve_ablation: AblationReport
    improved: ImprovedCase
    final_critic: DefectReport
    final_ablation: AblationReport
    stage_runs: list[StageRun]
    human_reviews: list[HumanReview] = Field(default_factory=list)
    human_adjudication: HumanAdjudication | None = None
    release_status: Literal["pending_human_review", "accepted", "discard"] = (
        "pending_human_review"
    )
