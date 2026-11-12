from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

from models import (
    AblationReport,
    CaseContent,
    Defect,
    DefectReport,
    EvolvedCase,
    HumanAdjudication,
    HumanReview,
    ImprovedCase,
)
from common import normalize_dataset, sha256_file


def _defect(
    code: str,
    severity: str,
    objects: list[str],
    description: str,
    route: str,
) -> Defect:
    return Defect(
        defect_code=code,
        severity=severity,
        affected_object_ids=objects,
        description=description,
        evidence=description,
        recommended_route=route,
    )


def _is_connected_acyclic(case: CaseContent) -> tuple[bool, bool]:
    task_ids = {task.task_id for task in case.tasks}
    indegree = {task_id: 0 for task_id in task_ids}
    outgoing: dict[str, set[str]] = defaultdict(set)
    undirected: dict[str, set[str]] = defaultdict(set)

    for task in case.tasks:
        for parent in task.depends_on_task_ids:
            if parent not in task_ids:
                continue
            outgoing[parent].add(task.task_id)
            undirected[parent].add(task.task_id)
            undirected[task.task_id].add(parent)
            indegree[task.task_id] += 1

    queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for child in outgoing[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    acyclic = visited == len(task_ids)

    if not task_ids:
        return False, acyclic
    seen = set()
    queue = deque([next(iter(task_ids))])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(undirected[node] - seen)
    connected = seen == task_ids
    return connected, acyclic


def validate_case(
    case: CaseContent,
    allowed_datasets: set[str],
    check_assets: bool = True,
    asset_root: Path | None = None,
) -> list[Defect]:
    defects: list[Defect] = []
    dataset = normalize_dataset(case.source_card.dataset)
    if dataset not in allowed_datasets:
        defects.append(
            _defect(
                "SOURCE_DATASET_NOT_ALLOWED",
                "critical",
                [case.source_card.source_id],
                f"Dataset {dataset!r} is outside the fixed allowlist.",
                "source_lock",
            )
        )

    asset_ids = {asset.asset_id for asset in case.source_card.selected_assets}
    if len(asset_ids) != len(case.source_card.selected_assets):
        defects.append(
            _defect(
                "SOURCE_DUPLICATE_ASSET_ID",
                "critical",
                [case.source_card.source_id],
                "Asset identifiers are not unique.",
                "source_lock",
            )
        )
    if check_assets:
        for asset in case.source_card.selected_assets:
            path = Path(asset.path).expanduser()
            if not path.is_absolute():
                if asset_root is None:
                    defects.append(
                        _defect(
                            "SOURCE_ASSET_ROOT_REQUIRED",
                            "critical",
                            [asset.asset_id],
                            (
                                "Asset path is relative but no asset root was "
                                f"provided for validation: {asset.path}"
                            ),
                            "source_lock",
                        )
                    )
                    continue
                path = asset_root / path
            path = path.resolve()
            if not path.is_file():
                defects.append(
                    _defect(
                        "SOURCE_ASSET_MISSING",
                        "critical",
                        [asset.asset_id],
                        f"Local asset does not exist: {path}",
                        "source_lock",
                    )
                )
            elif asset.sha256 != sha256_file(path):
                defects.append(
                    _defect(
                        "SOURCE_ASSET_HASH_MISMATCH",
                        "critical",
                        [asset.asset_id],
                        f"Asset hash does not match: {path}",
                        "source_lock",
                    )
                )

    evidence_ids = {node.evidence_id for node in case.evidence_graph}
    evidence_by_id = {node.evidence_id: node for node in case.evidence_graph}
    rule_ids = {rule.rule_id for rule in case.rule_program}
    task_ids = {task.task_id for task in case.tasks}
    state_ids = {
        state.state_id for state in case.hidden_gold.intermediate_states
    }
    gold_ids = {claim.gold_claim_id for claim in case.hidden_gold.atomic_claims}

    id_groups = [
        ("evidence", evidence_ids, len(case.evidence_graph)),
        ("rule", rule_ids, len(case.rule_program)),
        ("task", task_ids, len(case.tasks)),
        ("state", state_ids, len(case.hidden_gold.intermediate_states)),
        ("gold", gold_ids, len(case.hidden_gold.atomic_claims)),
    ]
    for label, identifiers, expected_count in id_groups:
        if len(identifiers) != expected_count:
            defects.append(
                _defect(
                    f"DUPLICATE_{label.upper()}_ID",
                    "critical",
                    [case.case_id],
                    f"{label.title()} identifiers are not unique.",
                    "self_improve",
                )
            )

    if not 3 <= len(case.tasks) <= 5:
        defects.append(
            _defect(
                "TASK_COUNT_OUT_OF_RANGE",
                "major",
                [case.case_id],
                f"Expected 3-5 tasks, found {len(case.tasks)}.",
                "self_construct",
            )
        )

    connected, acyclic = _is_connected_acyclic(case)
    if not connected:
        defects.append(
            _defect(
                "TASK_DAG_DISCONNECTED",
                "major",
                list(task_ids),
                "Task dependency graph is disconnected.",
                "self_construct",
            )
        )
    if not acyclic:
        defects.append(
            _defect(
                "TASK_DAG_CYCLE",
                "critical",
                list(task_ids),
                "Task dependency graph contains a cycle.",
                "self_construct",
            )
        )

    rubric_gold_refs: set[str] = set()
    for task in case.tasks:
        unknown_parents = set(task.depends_on_task_ids) - task_ids
        if unknown_parents:
            defects.append(
                _defect(
                    "TASK_UNKNOWN_DEPENDENCY",
                    "critical",
                    [task.task_id],
                    f"Unknown task dependencies: {sorted(unknown_parents)}",
                    "self_construct",
                )
            )
        if task.turn_index > 1 and not task.depends_on_task_ids:
            defects.append(
                _defect(
                    "TASK_NO_PRIOR_DEPENDENCY",
                    "major",
                    [task.task_id],
                    "A later task has no declared prior dependency.",
                    "self_construct",
                )
            )
        task_evidence = [
            evidence_by_id[item]
            for item in task.required_evidence_ids
            if item in evidence_by_id
        ]
        if not any(
            node.modality in {"visual", "cross_modal"} for node in task_evidence
        ):
            defects.append(
                _defect(
                    "TASK_NO_VISUAL_EVIDENCE",
                    "critical",
                    [task.task_id],
                    "Task has no required visual or cross-modal evidence node.",
                    "self_evolve",
                )
            )
        if not task.required_rule_ids:
            defects.append(
                _defect(
                    "TASK_NO_LOCAL_RULE",
                    "critical",
                    [task.task_id],
                    "Task declares no required local rule.",
                    "self_evolve",
                )
            )
        unknown_evidence = set(task.required_evidence_ids) - evidence_ids
        unknown_rules = set(task.required_rule_ids) - rule_ids
        unknown_states = set(task.consumes_state_ids) - state_ids
        if unknown_evidence:
            defects.append(
                _defect(
                    "TASK_UNKNOWN_EVIDENCE",
                    "critical",
                    [task.task_id],
                    f"Unknown evidence references: {sorted(unknown_evidence)}",
                    "self_improve",
                )
            )
        if unknown_rules:
            defects.append(
                _defect(
                    "TASK_UNKNOWN_RULE",
                    "critical",
                    [task.task_id],
                    f"Unknown rule references: {sorted(unknown_rules)}",
                    "self_improve",
                )
            )
        if unknown_states:
            defects.append(
                _defect(
                    "TASK_UNKNOWN_STATE",
                    "critical",
                    [task.task_id],
                    f"Unknown state references: {sorted(unknown_states)}",
                    "self_improve",
                )
            )
        if len(task.rubrics) < 4:
            defects.append(
                _defect(
                    "RUBRIC_COUNT_TOO_LOW",
                    "major",
                    [task.task_id],
                    f"Expected at least 4 rubrics, found {len(task.rubrics)}.",
                    "self_improve",
                )
            )
        for rubric in task.rubrics:
            if not rubric.statement.startswith("The response should"):
                defects.append(
                    _defect(
                        "RUBRIC_BAD_PREFIX",
                        "minor",
                        [rubric.rubric_id],
                        "Rubric must begin with 'The response should'.",
                        "self_improve",
                    )
                )
            if not rubric.evidence_ids or not rubric.rule_ids:
                defects.append(
                    _defect(
                        "RUBRIC_UNGROUNDED",
                        "critical",
                        [rubric.rubric_id],
                        "Rubric lacks evidence or rule references.",
                        "self_improve",
                    )
                )
            if set(rubric.evidence_ids) - evidence_ids:
                defects.append(
                    _defect(
                        "RUBRIC_UNKNOWN_EVIDENCE",
                        "critical",
                        [rubric.rubric_id],
                        "Rubric references unknown evidence.",
                        "self_improve",
                    )
                )
            if set(rubric.rule_ids) - rule_ids:
                defects.append(
                    _defect(
                        "RUBRIC_UNKNOWN_RULE",
                        "critical",
                        [rubric.rubric_id],
                        "Rubric references an unknown rule.",
                        "self_improve",
                    )
                )
            if set(rubric.gold_claim_ids) - gold_ids:
                defects.append(
                    _defect(
                        "RUBRIC_UNKNOWN_GOLD",
                        "critical",
                        [rubric.rubric_id],
                        "Rubric references an unknown gold claim.",
                        "self_improve",
                    )
                )
            rubric_gold_refs.update(rubric.gold_claim_ids)

    visible = (
        case.system_prompt
        + "\n"
        + case.evidence_context
        + "\n"
        + case.local_rule_context
    ).casefold()
    for claim in case.hidden_gold.atomic_claims:
        if not claim.evidence_ids or set(claim.evidence_ids) - evidence_ids:
            defects.append(
                _defect(
                    "GOLD_EVIDENCE_COVERAGE",
                    "critical",
                    [claim.gold_claim_id],
                    "Gold claim lacks complete evidence coverage.",
                    "self_construct",
                )
            )
        if not claim.rule_ids or set(claim.rule_ids) - rule_ids:
            defects.append(
                _defect(
                    "GOLD_RULE_COVERAGE",
                    "critical",
                    [claim.gold_claim_id],
                    "Gold claim lacks complete rule coverage.",
                    "self_construct",
                )
            )
        if claim.gold_claim_id not in rubric_gold_refs:
            defects.append(
                _defect(
                    "GOLD_RUBRIC_COVERAGE",
                    "critical",
                    [claim.gold_claim_id],
                    "No rubric covers this atomic gold claim.",
                    "self_improve",
                )
            )
        for forbidden in claim.forbidden_visible_strings:
            token = forbidden.strip().casefold()
            if len(token) >= 4 and token in visible:
                defects.append(
                    _defect(
                        "VISIBLE_GOLD_LEAKAGE",
                        "critical",
                        [claim.gold_claim_id],
                        f"Forbidden hidden-gold string appears in visible context: {forbidden!r}",
                        "self_improve",
                    )
                )
    return defects


def validate_evolution(evolved: EvolvedCase, minimum_families: int = 2) -> list[Defect]:
    defects: list[Defect] = []
    families = {mutation.family for mutation in evolved.mutation_log}
    if len(families) < minimum_families:
        defects.append(
            _defect(
                "EVOLVE_INSUFFICIENT_MUTATION_FAMILIES",
                "major",
                [evolved.case.case_id],
                f"Expected at least {minimum_families} mutation families, found {len(families)}.",
                "self_evolve",
            )
        )
    for mutation in evolved.mutation_log:
        if not mutation.changed_object_ids or not mutation.preserved_invariants:
            defects.append(
                _defect(
                    "EVOLVE_INCOMPLETE_MUTATION_LOG",
                    "critical",
                    [mutation.mutation_id],
                    "Mutation log lacks changed objects or preserved invariants.",
                    "self_evolve",
                )
            )
    return defects


def validate_improvement(improved: ImprovedCase) -> list[Defect]:
    defects: list[Defect] = []
    unresolved = [item for item in improved.repair_log if item.result == "unresolved"]
    if unresolved:
        defects.append(
            _defect(
                "IMPROVE_UNRESOLVED_DEFECTS",
                "critical",
                [item.repair_id for item in unresolved],
                "Repair log contains unresolved defects.",
                "discard",
            )
        )
    if improved.recommended_status == "discard":
        defects.append(
            _defect(
                "IMPROVE_RECOMMENDS_DISCARD",
                "critical",
                [improved.case.case_id],
                "The repair stage recommends discarding this case.",
                "discard",
            )
        )
    return defects


def validate_reports(
    critic: DefectReport,
    ablation: AblationReport,
    case: CaseContent | None = None,
) -> list[Defect]:
    defects = list(critic.defects) + list(ablation.defects)
    if critic.case_id != ablation.case_id:
        defects.append(
            _defect(
                "REPORT_CASE_ID_MISMATCH",
                "critical",
                [critic.case_id, ablation.case_id],
                "Critic and ablation reports refer to different cases.",
                "self_improve",
            )
        )
    if case is not None:
        if critic.case_id != case.case_id or ablation.case_id != case.case_id:
            defects.append(
                _defect(
                    "REPORT_TARGET_CASE_MISMATCH",
                    "critical",
                    [case.case_id, critic.case_id, ablation.case_id],
                    "A report case identifier does not match the evaluated case.",
                    "self_improve",
                )
            )
        task_by_id = {task.task_id: task for task in case.tasks}
        expected_task_ids = set(task_by_id)
        reported_task_ids = [report.task_id for report in ablation.task_reports]
        duplicate_task_ids = sorted(
            {
                task_id
                for task_id in reported_task_ids
                if reported_task_ids.count(task_id) > 1
            }
        )
        if duplicate_task_ids:
            defects.append(
                _defect(
                    "ABLATION_DUPLICATE_TASK_REPORT",
                    "critical",
                    duplicate_task_ids,
                    "Ablation report contains duplicate task entries.",
                    "self_evolve",
                )
            )
        missing_task_ids = sorted(expected_task_ids - set(reported_task_ids))
        extra_task_ids = sorted(set(reported_task_ids) - expected_task_ids)
        if missing_task_ids:
            defects.append(
                _defect(
                    "ABLATION_MISSING_TASK_REPORT",
                    "critical",
                    missing_task_ids,
                    "Ablation report does not cover every task.",
                    "self_evolve",
                )
            )
        if extra_task_ids:
            defects.append(
                _defect(
                    "ABLATION_UNKNOWN_TASK_REPORT",
                    "critical",
                    extra_task_ids,
                    "Ablation report contains tasks absent from the case.",
                    "self_evolve",
                )
            )

        required_variants = {
            "full",
            "no_visual",
            "no_local_rules",
            "no_prior_state",
        }
        for task_report in ablation.task_reports:
            if task_report.task_id not in task_by_id:
                continue
            variants = [decision.variant for decision in task_report.decisions]
            variant_set = set(variants)
            if len(variants) != 4 or variant_set != required_variants:
                defects.append(
                    _defect(
                        "ABLATION_INCOMPLETE_VARIANT_SET",
                        "critical",
                        [task_report.task_id],
                        (
                            "Each task must contain exactly one decision for "
                            "full, no_visual, no_local_rules, and no_prior_state."
                        ),
                        "self_evolve",
                    )
                )
                continue
            by_variant = {
                decision.variant: decision for decision in task_report.decisions
            }
            required_outcomes = {
                "full": "solvable",
                "no_visual": "not_solvable",
                "no_local_rules": "not_solvable",
            }
            for variant, expected in required_outcomes.items():
                actual = by_variant[variant].solvability
                if actual != expected:
                    defects.append(
                        _defect(
                            f"ABLATION_{variant.upper()}_GATE_FAILED",
                            "major",
                            [task_report.task_id],
                            (
                                f"{variant} must be {expected!r} for release, "
                                f"found {actual!r}."
                            ),
                            "self_evolve",
                        )
                    )
            task = task_by_id[task_report.task_id]
            prior_decision = by_variant["no_prior_state"].solvability
            if task.consumes_state_ids and prior_decision != "not_solvable":
                defects.append(
                    _defect(
                        "ABLATION_PRIOR_STATE_GATE_FAILED",
                        "major",
                        [task_report.task_id],
                        (
                            "A task that consumes prior state must be not_solvable "
                            "under the no_prior_state ablation."
                        ),
                        "self_evolve",
                    )
                )
            if not task.consumes_state_ids and prior_decision not in {
                "solvable",
                "not_applicable",
            }:
                defects.append(
                    _defect(
                        "ABLATION_PRIOR_STATE_UNEXPECTED",
                        "major",
                        [task_report.task_id],
                        (
                            "A task with no consumed prior state should mark the "
                            "no_prior_state variant solvable or not_applicable."
                        ),
                        "self_evolve",
                    )
                )
    if critic.recommendation != "pass" and not critic.defects:
        defects.append(
            _defect(
                "CRITIC_NONPASS_WITHOUT_DEFECT",
                "critical",
                [critic.case_id],
                "Critic recommendation is non-pass but lists no defect.",
                "self_improve",
            )
        )
    if ablation.recommendation != "pass" and not ablation.defects:
        defects.append(
            _defect(
                "ABLATION_NONPASS_WITHOUT_DEFECT",
                "critical",
                [ablation.case_id],
                "Ablation recommendation is non-pass but lists no defect.",
                "self_evolve",
            )
        )
    return defects


def validate_human_release(
    reviews: list[HumanReview],
    adjudication: HumanAdjudication | None,
) -> list[str]:
    failures: list[str] = []
    if len(reviews) < 2:
        failures.append("Two independent human reviews are required.")
    reviewer_ids = {review.reviewer_id for review in reviews}
    if len(reviewer_ids) < 2:
        failures.append("Human reviews must come from two distinct reviewers.")
    if any(not review.blind_to_model_results for review in reviews):
        failures.append("Human reviewers must be blind to model evaluation results.")
    if any(review.decision != "pass" for review in reviews) and adjudication is None:
        failures.append("Disagreement or failure requires a saved adjudication.")
    if adjudication is None:
        failures.append("A final human adjudication record is required.")
    elif adjudication.decision != "pass":
        failures.append("Human adjudication did not pass.")
    return failures
