# Released Results for the 60 Examples

This directory contains the anonymized model outputs and GPT-5.2 judge records
for the 60 complete examples released in `../../examples/`.

## Coverage

- 60 cases spanning all 20 subcategories;
- 174 unique tasks;
- 8 main-paper model settings;
- 1,392 prediction records (`174 × 8`);
- 1,392 GPT-5.2 judgment records (`174 × 8`).

These files reproduce the aggregate results for the released 60-example
subset. They do not reconstruct the full 344-case main result table reported
in the paper.

## Files

- `predictions.jsonl`: one anonymized model output per task and model.
- `judgments_gpt5.2.jsonl`: the corresponding GPT-5.2 rationale, logical
  rubric decisions, stored score, normalized score, and record status.
- `evaluation_errors.jsonl`: the 19 task-model records affected by an
  inference or judge API error.
- `correction_log.json`: one case-text terminology correction and two
  deterministic normalizations of malformed stored judgment fields. No model
  answer or judge rationale was rewritten.
- `summary.json` and `summary_by_model.csv`: committed reference aggregates.

Each JSONL record contains only public `MCL-xxxx` identifiers. Repeated
multimodal messages, private source mappings, provider request identifiers,
account metadata, and machine-local paths are not included.

## Error and score policy

The released subset is summarized as an end-to-end evaluation. A task receives
one only when all logical rubric decisions are `yes`. An inference failure or
judge API failure is retained with an explicit `record_status` and counted as
zero. The error list is provided so the policy and affected denominators remain
inspectable.

The case JSON files contain 1,163 serialized rubric entries. Some multiline
logical rubrics occupy more than one serialized array entry. The judge records
therefore report both the serialized entry count and the number of logical
rubric decisions used during judging.

For `MCL-0087_T1`, the rubric label `peer-driven` was harmonized to
`companion-driven`, the term used in the task, and the sentence grammar was
repaired. The correction is explicitly logged. It does not change the intended
paired-running category or any released binary score.

## Reaggregate

From the repository root:

```bash
python evaluation/scripts/reproduce_released_examples.py \
  --output-dir reproduced/released_examples
```

The command checks full task-model coverage, validates the normalization and
all-or-nothing rule, writes a fresh summary, and compares it with the committed
reference summary.
