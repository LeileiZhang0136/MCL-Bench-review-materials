# Full-benchmark score reconciliation

This supplement releases 8,640 anonymized task-model score rows from the
existing eight-model evaluation: 344 cases and 1,080 ordered tasks per model.
It provides an offline numerical audit, not a new generation or regrading run.

## Reproduce

From the repository root:

```bash
python evidence/evaluation_reconciliation/reproduce.py --output-dir reproduced/evaluation_reconciliation
```

The script uses only Python's standard library, the local anonymous score CSV
and the already released Kimi score CSV. It reproduces `summary.json` and
`SUMMARY.md`, including first-turn versus all-task scores, context macro
averages, model-specific rubric diagnostics, paired Thinking comparisons and
observed automated-pass coverage.

## Definitions and corrections

- First-turn success uses one first task from each of 344 cases.
- Task micro success uses all 1,080 ordered tasks.
- Context macro success first averages scores within each case and then
  averages across 344 cases.
- The eight original overall rates match the first-turn rates at the printed
  precision. This numerical correspondence does not reconstruct the original
  table-generation program.
- Ten records lack a valid stored score. `stored_score` is empty for them,
  `score_available=0`, and `effective_score=0` for end-to-end accounting.
- One count-aligned stored score conflicts with its requirement-status list.
  It is explicitly listed in the summary. Stored-score reproduction and a
  deterministic status-normalized sensitivity result are reported separately.
- Equal rubric/status counts are only a structural alignment condition. They
  do not certify semantic alignment or correctness. These diagnostics cover
  different eligible subsets for different models and cannot establish a
  fair cross-model rubric ranking.
- Observed coverage counts tasks accepted for at least one model by the
  existing automated scores. It is not an independent proof of answerability.

The CSV contains public case/task IDs, taxonomy, model names, binary scores,
rubric-entry counts and normalized requirement-status strings. It excludes
private source mappings, raw prompts, provider metadata, identities and paths.
Numerical reproducibility does not establish validity of every judge decision.

The older uncertainty tables inferred full-task counts from the original
rounded overall rates. Those main-table counts are superseded by this export;
the corrected uncertainty command now uses observed full-task counts. The
media-configuration counts remain separately identified as historical counts.

## Rubric diagnostics

[Readable diagnostic tables](RUBRIC_DIAGNOSTICS.md) present rubric satisfaction,
coverage, single-entry failures and success by serialized rubric count.
Machine-readable tables are [rubric_satisfaction.csv](rubric_satisfaction.csv)
and [success_by_rubric_count.csv](success_by_rubric_count.csv).
`reproduce_rubric_diagnostics.py` derives these directly from the score rows and
cross-checks them against the reconciliation; it is also included in the
unified `python tools/reproduce.py reconciliation` workflow.

## Single-requirement failure inspection

[Inspection guide](SINGLE_FAILURE_REVIEW.md),
[record index](single_failure_records.csv), and
[eight illustrative responses](single_failure_examples.jsonl) expose
existing automated boundary judgments. The 1,184 indexed task-model records
are not human labels. The examples include the released response, rubric
list, status vector and grading rationale. Reproduce with
`reproduce_single_failure.py` or the unified reconciliation command.
