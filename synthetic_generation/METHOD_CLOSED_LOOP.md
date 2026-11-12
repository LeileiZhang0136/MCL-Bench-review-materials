# Closed-Loop Synthetic-Case Construction Protocol

## 0. Alignment with the manuscript workflow

The manuscript's four construction steps and this document's three `Self-*`
operations describe two levels of the same process:

| Manuscript workflow | Operational implementation |
|---|---|
| Source curation and quality filtering | Stage 0 Source Lock and its deterministic source gate |
| Case-specific context construction | Self-Construct, followed by controlled Self-Evolve mutations |
| Task and rubric generation | Initial task/rubric drafting in Self-Construct, challenge updates in Self-Evolve, and validator-routed revision in Self-Improve |

Thus, the outer workflow explains where data are selected and transformed,
while the three `Self-*` labels identify the iterative operations applied to a
frozen source.

## 1. Why the loop is auditable

`Self-Construct`, `Self-Evolve`, and `Self-Improve` are not three unconstrained
rounds of rewriting. Each stage has a non-overlapping objective, a typed input,
a typed output, invariants that it may not change, and an explicit failure
route. A newly generated case cannot accept itself: final acceptance is
performed by a release gate that combines deterministic checks with an
independent human review.

The state machine is:

```text
candidate
  -> source_locked
  -> constructed
  -> evolved
  -> improved
  -> machine_validated
  -> human_validated
  -> accepted
```

For newly generated public-release candidates, `accepted` is the only terminal
state eligible for export.

## 2. Stage 0: Source Lock

### Input

A sample from the fixed source allowlist: SlideVQA or MMLongBench-Doc.

### Output

A `SourceCard` containing the dataset, split, sample identifier, upstream URL,
access/license note, local asset paths, asset SHA-256 hashes, selected pages or
images, and the exact source text fields used.

### Invariants

- Every visual asset is locally readable.
- Every asset and text field maps back to one source sample.
- The source facts are immutable in all later stages.
- Unclear redistribution status is recorded; it is never converted into a
  positive license claim by the model.

### Gate S

Pass only when traceability and local readability are complete. A failure
cannot be repaired by prompting; the sample is repaired at source level or
rejected.

## 3. Stage 1: Self-Construct = grounded program synthesis

### Single responsibility

Compile source evidence into one solvable draft. This stage establishes what is
true and how an answer is computed. It does not add difficulty for its own
sake.

### Input

`SourceCard`, source text fields, and the selected visual assets.

### Output

A `ConstructedCase` with separated visible channels and four linked objects:

1. `evidence_context`: source-grounded material index without answer-revealing
   visual transcriptions;
2. `local_rule_context`: the complete executable rule text visible to models;
3. `EvidenceGraph`: atomic evidence nodes with visual/text anchors;
4. `RuleProgram`: case-local definitions, mappings, priorities, exceptions,
   tie-breaking, and fallback states;
5. `TaskDAG`: ordered tasks whose later nodes explicitly consume earlier
   intermediate states;
6. `HiddenGold`: deterministic intermediate states and final answers, with a
   derivation path through evidence and rules.

### Construct invariants

- The model may introduce case-local rules, but may not alter source facts.
- Every atomic gold claim has at least one source anchor and one rule path.
- Every task has one uniquely executable answer under the local rule program.
- Visible context contains all rules required to execute the gold derivation.
- Hidden gold and evidence locations are never copied into visible context.

### Gate C

The draft passes only if:

- evidence coverage is 100%;
- rule coverage is 100%;
- the TaskDAG is connected and acyclic;
- all final answers are deterministically derivable;
- no task is ordinary source QA or answer-key repetition.

Failure routing:

- missing/unclear source evidence -> Stage 0 or reject;
- incomplete rule or ambiguous answer -> rerun Stage 1 with defect codes;
- leakage discovered here -> remove the leaked field and reconstruct.

## 4. Stage 2: Self-Evolve = controlled adversarial mutation

### Single responsibility

Convert a valid but potentially easy draft into a multimodal context-learning
stress test. This stage mutates challenge structure while preserving the
source facts and the executable semantics established in Stage 1.

### Input

A Gate-C-passing `ConstructedCase`.

### Output

An `EvolvedCase` plus a `MutationLog`. Every mutation records:

- targeted weakness;
- operation applied;
- objects changed;
- invariants checked;
- old and recomputed gold;
- expected failure mode.

### Required mutation families

At least two of the following must be used, and they must target different
weaknesses:

- `cross_modal_interlock`: split necessary evidence across visual and textual
  channels;
- `neighbor_rule`: add a plausible adjacent branch that must be rejected;
- `evidence_distractor`: add a source-grounded but task-irrelevant cue;
- `counterfactual`: change exactly one declared condition and recompute all
  affected downstream states;
- `state_reuse`: make a later task consume a named earlier intermediate state;
- `priority_conflict`: create a resolvable local-rule conflict;
- `missing_or_conflict_fallback`: exercise an explicit fallback state.

### Evolve invariants

- Source facts and asset hashes remain unchanged.
- A mutation never adds unsupported factual content.
- A counterfactual changes only declared variables; unchanged conclusions stay
  unchanged.
- Every mutated task remains uniquely solvable.
- Difficulty changes never weaken evidence traceability.

### Gate E

For every task, record the following adjudicated necessity vector:

```text
N(task) = [full, no_visual, no_local_rules, no_prior_state]
```

A task is multimodal-context-dependent only when `full=solvable` and at least
the critical `no_visual` and `no_local_rules` variants are not reliably
solvable. For later-turn tasks, `no_prior_state` must also fail when the task
claims state reuse.

Gate E additionally requires:

- at least one genuine cross-modal dependency per task;
- at least one case-level counterfactual or conflict/fallback test;
- no single-cue or source-answer shortcut;
- a valid TaskDAG after mutation;
- a complete, machine-readable mutation log.

Failures route back to Stage 2 with the precise shortcut or dependency defect.
If the source cannot support genuine interlocking, route to Stage 0 and choose
another sample.

## 5. Stage 3: Self-Improve = verifier-driven constrained repair

### Single responsibility

Repair defects discovered by explicit validators. This stage is not allowed to
invent a new case or silently change its source, rules, or intended answer.

### Input

An `EvolvedCase`, its mutation log, and a list of validator defect codes.

### Output

An `ImprovedCase` and a `RepairLog`. Each repair links:

```text
defect code -> affected object -> patch -> rechecked invariants -> result
```

### Improve checks

- prompt/gold consistency;
- gold/evidence/rule traceability;
- rubric atomicity and binary decidability;
- rubric coverage of evidence, intermediate state, rule application, final
  answer, and output constraints;
- absence of hidden rules introduced only by rubrics;
- placeholder/path consistency;
- counterfactual conservation;
- leakage and shortcut checks.

### Improve invariants

- Source assets, source facts, and their hashes are immutable.
- A repair may change only objects named in the repair plan.
- Gold changes require re-execution of the rule program and regeneration of
  all affected rubrics.
- Every rubric must map to one or more gold/evidence identifiers.

### Gate I

Pass only when there are zero critical defects and all deterministic validators
pass. The maximum repair budget is three iterations. Remaining critical
defects after three iterations produce `discard`, not automatic acceptance.
The implementation executes this loop up to
`config/release.json::max_repair_iterations`, rerunning the critic and ablation
audit after every repair attempt.

## 6. Independent Release Gate

The generator is not the final authority. Acceptance requires all of:

### Machine checks

- schema validation;
- source and asset hash validation;
- 100% gold-to-evidence and gold-to-rule coverage;
- TaskDAG validity;
- rubric traceability and minimum rubric coverage;
- zero unresolved critical defect;
- exact prompt/model/config hashes saved;
- source dataset belongs to the fixed allowlist.
- exactly one `full`, `no_visual`, `no_local_rules`, and `no_prior_state`
  decision is present for every task;
- `full` is solvable, while `no_visual` and `no_local_rules` are not solvable;
- tasks that consume an earlier state are not solvable under
  `no_prior_state`.

### Independent human checks

Two reviewers, blind to model evaluation outcomes, independently judge:

- asset completeness and readability;
- answerability and uniqueness;
- gold correctness;
- rubric correctness and completeness;
- context dependence;
- genuine multimodal necessity;
- shortcut or pretrained-knowledge leakage.

Disagreements are adjudicated and saved. If the two reviewers are paper
authors, the result is reported as an `independent author audit`, not an
external expert audit.

### Release rule for newly generated candidates

```text
accepted =
    all_machine_checks_pass
    AND both_human_reviews_present
    AND adjudicated_human_decision == pass
```

No model difficulty score can replace human validity evidence. The prospective
human gate above applies to newly generated public-release candidates.

## 7. Formal coverage measures

For case `c`, let `G_c` be its atomic gold claims. Each claim `g` must map to
source evidence `E(g)`, local rules `R(g)`, and rubric criteria `B(g)`.

```text
EvidenceCoverage(c) = |{g in G_c : E(g) is non-empty}| / |G_c|
RuleCoverage(c)     = |{g in G_c : R(g) is non-empty}| / |G_c|
RubricCoverage(c)   = |{g in G_c : B(g) is non-empty}| / |G_c|
```

All three must equal 1.0 for release. These are structural coverage measures,
not claims that a model will reason correctly.

## 8. Reproducibility boundary

The executable release method can be stated as:

> We implement a unified synthetic-case construction pipeline using the
> GPT-5.5 API through the Responses API. Candidate samples
> are drawn from SlideVQA and MMLongBench-Doc. Each accepted case preserves
> source- and asset-level hashes, stage-specific structured outputs, mutation
> and repair logs, and independent release-gate decisions.

All 189 synthetic cases in the paper were generated through the GPT-5.5 API using
source material from SlideVQA or MMLongBench-Doc. The repository provides the
prompts, typed schemas, validators, configuration, and executable reference
code for the common synthetic-case construction method.
