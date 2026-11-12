# Reasoning-Style Analyses

This directory documents the reasoning-style labeling protocol used for the
diagnostic analysis in Figure 9. It provides the codebook, the two exact
model-assisted prompts, and one complete representative case for each of the
four reported reasoning styles.

## Directory contents

- `codebook/reasoning_style_codebook.md`: category definitions, the
  primary-label rule, overlap handling, and the scope of the taxonomy;
- `prompts/exploratory_summarization_prompt.md`: the open-ended first-stage
  prompt, which contains no predefined style labels;
- `prompts/fixed_code_relabeling_prompt.md`: the frozen-codebook prompt used
  after manual consolidation;
- `examples/`: four anonymized cases, their media, all task-level rubrics, all
  four stored GPT-5.2 responses, and the selected Turn 1 style annotation; and
- `examples/example_index.csv`: a compact public index using only MCL case
  identifiers.

The stored response files contain only anonymized task identifiers and model
responses. Original inference-message copies are not included because the
task prompts, rubrics, and media are already present in each `case.json` and
`assets/` directory.

## Labeling procedure

The analysis used three steps:

1. **Exploratory summarization.** GPT-5.2 received the task prompt, model
   response, and grading rationale and described the dominant organization of
   the response in free form. No reasoning-style labels were supplied.
2. **Manual consolidation.** Recurring descriptions that were semantically
   stable and interpretable were consolidated into four diagnostic categories:
   Hierarchical Audit Structuring, Procedural Constraint Decomposition, Local
   Evidence Grounding, and Global Schema Induction.
3. **Fixed-code re-labeling.** The taxonomy was frozen and exactly one primary
   label was assigned to each response for the Figure 9 aggregation. Borderline
   cases were manually inspected, and the style providing the main organizing
   structure of the final answer was selected.

## Overlap and interpretation

The four categories are not claimed to be semantically disjoint. A response
can, for example, combine local evidence grounding with procedural constraint
checks. Figure 9 is mutually exclusive only at the aggregation level: it uses
one dominant primary label per response to prevent double counting. The labels
therefore summarize the main organization of a response rather than enumerate
every reasoning behavior it contains.

The taxonomy is also not claimed to be theoretically exhaustive. It is an
empirically consolidated diagnostic taxonomy covering recurring patterns in
the analyzed benchmark responses. The procedure was inspired by exploratory
coding, but it was not a full grounded-theory study. Figure 9 should therefore
be read as diagnostic and hypothesis-generating, not as a causal analysis or a
complete theory of reasoning behavior.

## Released examples

| Primary reasoning style | Case | Analyzed response | Benchmark subcategory |
|---|---|---:|---|
| Hierarchical Audit Structuring | [`MCL-0169`](examples/01_hierarchical_audit_structuring/MCL-0169_synthetic/) | Turn 1 | Evidence Ledger |
| Procedural Constraint Decomposition | [`MCL-0188`](examples/02_procedural_constraint_decomposition/MCL-0188_synthetic/) | Turn 1 | Repair Help |
| Local Evidence Grounding | [`MCL-0089`](examples/03_local_evidence_grounding/MCL-0089_synthetic/) | Turn 1 | Sports Actions |
| Global Schema Induction | [`MCL-0039`](examples/04_global_schema_induction/MCL-0039_synthetic/) | Turn 1 | Puzzle Games |

Each case directory is self-contained. Although Turn 1 is the labeled example,
`gpt-5.2_outputs.json` retains all four stored turns so readers can inspect the
response in its sequential context.
