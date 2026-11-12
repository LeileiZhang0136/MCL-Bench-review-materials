# Evidence for inspecting synthetic-case construction

This index connects construction requirements to their public implementation
and to a worked example. Readers can follow the chain from source evidence
to local rules, reference reasoning and task-level rubrics.

## 1. Construction requirements and implementation

| Requirement | Inspectable material | What to check |
|---|---|---|
| Source facts remain fixed | [Self-Construct prompt](../../synthetic_generation/prompts/01_self_construct.md), [source and evidence schemas](../../synthetic_generation/scripts/models.py) | The source is immutable; evidence nodes carry identifiers, modality and anchors |
| Conclusions have evidence and rule support | [GoldClaim and RubricCriterion schemas](../../synthetic_generation/scripts/models.py), [validators](../../synthetic_generation/scripts/validators.py) | `GOLD_EVIDENCE_COVERAGE`, `GOLD_RULE_COVERAGE`, `GOLD_RUBRIC_COVERAGE`; reference IDs must resolve |
| Tasks reuse declared states | [construction prompt](../../synthetic_generation/prompts/01_self_construct.md), [validators](../../synthetic_generation/scripts/validators.py) | Connected acyclic task graph, declared dependencies, evidence/rule/state references |
| Changes preserve facts and propagate to answers | [Self-Evolve prompt](../../synthetic_generation/prompts/02_self_evolve.md) | Mutations identify changed objects and invariants; affected states, answers and rubrics must be recomputed |
| Repair targets explicit defects | [Self-Improve prompt](../../synthetic_generation/prompts/03_self_improve.md), [repair models](../../synthetic_generation/scripts/models.py) | Defect codes, affected IDs, minimal patches and unresolved defects are recorded |
| Rubrics refer to case content | [validators](../../synthetic_generation/scripts/validators.py) | `RUBRIC_UNGROUNDED` and unknown evidence/rule/gold references are checked |
| Hidden answers do not appear in visible context | [validators](../../synthetic_generation/scripts/validators.py) | Explicit forbidden reference strings are checked by `VISIBLE_GOLD_LEAKAGE` |

For the full protocol, see
[construction overview](../../synthetic_generation/README.md) and
[closed-loop method](../../synthetic_generation/METHOD_CLOSED_LOOP.md).
The source allowlist is SlideVQA and MMLongBench-Doc.

These are explicit requirements and reference-code checks. Identifier
coverage and string checks establish structural properties; they do not by
themselves prove that every visual interpretation is correct or that every
answer is unique. The released reference implementation is not presented as
a completed new re-execution of all 189 historical synthetic cases. The
[package validation record](../../synthetic_generation/PACKAGE_VALIDATION.md)
identifies implementation checks and execution status separately.

## 2. Follow an evidence-to-answer derivation

[MCL-0083 Turn 3 worked solution](../reference_walkthroughs/MCL-0083_T3.md)
provides direct links to its original images, visible values, local evidence
rules, reference answer and correspondence to all six Turn 3 requirements.

The intervention is to hypothetically withhold a genealogy chart while
retaining a silver-flow chart. The answer follows three steps:

1. Apply the local evidence boundary: genealogy supports succession claims;
   the silver chart supports trade observations.
2. Withhold genealogy-based conclusions under the hypothetical while
   retaining the two-period trade comparison visible in the remaining chart.
3. Keep this hypothetical separate from the real two-page archive and avoid
   inferring cross-page causality unsupported by the materials.

The walkthrough includes Western Europe, Americas, East and South Asia,
Japan and route values. It is an inspectable reference derivation, not a new
model result or certification of other turns or cases.

## 3. Inspect complete case inputs and requirements

The [example release](../../examples/README.md) contains 60 complete cases,
three from each of 20 subcategories, with their full task messages and
rubrics. Readers can inspect explicit rules, task dependencies and evaluation
requirements beyond the paper's cropped figures. The source composition and
scope are documented in the public example manifest; this is a representative
example release rather than a random validity study.

This evidence supports transparent inspection of construction and concrete
answers. Low model pass rates are not used as validity evidence.
