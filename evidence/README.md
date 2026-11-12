# Evidence Included in This Repository

Only completed, bounded evidence is included here.

## Evaluation reconciliation

`evaluation_reconciliation/` releases eight-model anonymous full-task score
rows, first-turn versus full-task comparisons, model-specific count-aligned
rubric diagnostics, paired Thinking intervals and observed pass coverage.
This supersedes the earlier main-result counts inferred from rounded rates.
It does not rescore responses or independently validate task answerability.

## Targeted judge review and reference reasoning

`judge_calibration/` records the authors' existing targeted 100-response review
and distinguishes selected-sample three-judge agreement from judge-human
agreement. Individual human labels are not provided or inferred. A separate, newly extracted
100-response matched three-judge comparison is also included, with identical
response/rubric checks, per-item scores and illustrative grading rationales.
Its sample agreement is 71%, distinct from the historical targeted review.
`reference_walkthroughs/` makes a representative evidence-to-answer derivation
inspectable; it is not a human baseline or a random audit.

## Uncertainty

`uncertainty/` contains the task-level Wilson 95% confidence intervals for the
reconciled full-task model counts and the three historical media-configuration groups. The
script records the observed main-task counts and historical media denominators
and reproduces the tables.

These intervals quantify binomial uncertainty over saved model-task
evaluations. They do not estimate model run-to-run variation, do not account
for within-case clustering, and are not pairwise model-ranking tests.

## Scoped analyses

`analysis/` contains:

- a case-cluster bootstrap summary comparing the expert-collected and
  synthetic source tracks; and
- a paired case-cluster bootstrap summary for the 138-case multimodal
  evidence ablation; and
- a reasoning-style transparency package containing the codebook, exact
  model-assisted prompts, four complete representative cases, and their
  stored GPT-5.2 responses.

The source-track comparison describes a difficulty association. It is not
evidence that synthetic cases are valid. The ablation result applies only to
the paired 138-case synthetic subset and is not generalized to all 344 cases.

## Supplementary open-weight models

`open_weight_models/` contains the completed full-benchmark evaluation of Kimi
K2.6 and Kimi K3. It provides anonymized task-level paired scores, Wilson
intervals, a case-cluster bootstrap comparison, source-track breakdowns, a
sanitized protocol record, and a reproduction script. These supplementary
results remain separate from the paper's eight-model main result table.

## Evidence intentionally absent

No placeholder or incomplete table is included for:

- historical-case human validity;
- a validated failure-mode annotation study; or
- a human-agreement validation of the reasoning-style taxonomy.

The released reasoning-style materials document the method and representative
examples; they do not establish that the taxonomy is theoretically exhaustive
or causally related to model capability. The absent items above must not be
described as completed based on this repository.

## Synthetic construction evidence

[synthetic_validity/](synthetic_validity/README.md) connects source-locking,
evidence/rule/gold schemas, mutation and repair requirements, and deterministic
checks to the MCL-0083 Turn 3 worked solution and complete example release.
It distinguishes reference-code checks from historical full-case validation.

The [rubric diagnostics](evaluation_reconciliation/RUBRIC_DIAGNOSTICS.md)
include satisfaction, count-aligned coverage, single-entry failures, and
all-task success stratified by serialized rubric count, with CSVs and code.

The [single-failure inspection guide](evaluation_reconciliation/SINGLE_FAILURE_REVIEW.md)
provides a task-model index and eight complete released examples with
requirements and grading rationales, separately from any human-review claim.
