# Reasoning-Style Codebook

## Unit of analysis

The unit is one model response to one task turn. The label describes the
dominant organization of the response; it does not judge correctness.

## Categories

### Hierarchical Audit Structuring

The response first establishes a layered audit framework and then examines
evidence, rules, intermediate findings, and conclusions within that hierarchy.
Typical structures separate global evidence, local evidence, candidate routes,
uncertainty, and unsupported or non-mergeable evidence before a final decision.

### Procedural Constraint Decomposition

The response converts task rules, steps, format requirements, or constraints
into checkable subconditions and verifies them one by one. Typical structures
are ordered checklists covering labels, prerequisites, exclusions, formats, or
dependency rules.

### Local Evidence Grounding

The response is organized mainly around specific images, video segments, table
cells, text fields, or local object relations. It may cite local information
accurately without constructing a complete global schema or cross-turn rule
chain.

### Global Schema Induction

The response infers an overall task pattern, classification system, procedure,
or decision rule from multiple context fragments, and then uses the induced
schema to organize later decisions, dependencies, or exceptions.

## Primary-label decision rule

Assign exactly one label corresponding to the structure that plays the main
organizing role in the final answer. When several styles occur:

1. identify the structure that determines the response's top-level order;
2. identify the structure that connects the evidence to the final decision;
3. select the label best supported by both signals; and
4. manually inspect unclear cases and record a brief rationale.

No new label is created during fixed-code aggregation. This rule makes the
Figure 9 counts mutually exclusive; it does not imply that the underlying
reasoning behaviors never overlap.

## Scope

These four categories are empirical diagnostic codes, not an exhaustive theory
of reasoning. They were obtained through open-ended model-assisted summaries
and manual consolidation, not through a full grounded-theory methodology.
