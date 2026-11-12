# Three-judge evidence

## New matched comparison of existing judgments

The new analysis selects 100 responses across eight inference models and four
categories using a fixed hash order before inspecting score outcomes. It is
separate from the historical targeted author review below. For each item,
all three judges evaluated identical response text and identical rubrics.
Valid binary scores and nonempty binary status lists consistent with the
scores are required. Rubric/status count equality is not required, so this
compares task judgments rather than aligned rubric decisions.

- [Primary-judge reporting rationale and workload scenarios](PRIMARY_JUDGE_POLICY.md)
- [100 matched score rows](matched_three_judge_100.csv)
- [Sampling protocol and observed file coverage](matched_sample_protocol.json)
- [Comparison tables](MATCHED_SAMPLE.md)
- [Machine-readable statistics](matched_sample_summary.json)
- [Five illustrative responses and three-judge rationales](illustrative_matched_responses.jsonl)

Reproduce without any API calls:

```bash
python evidence/judge_calibration/reproduce_matched_sample.py --output-dir reproduced/judge_calibration
```

The paired sample contains 13 GPT-5.2 passes, 38 Claude passes and 28 Gemini
passes; all three agree on 71 responses. These results show judge-dependent
strictness, not which judge is correct. They do not establish human agreement,
ranking stability or population accuracy. The file-coverage inventory counts
case-model files, not valid task scores.

The five illustrations show unanimous failure, unanimous success, and each
observed disagreement pattern. Their response text matches already released
predictions; only the required task IDs, model response and sanitized judge
records are exported. Private source mappings remain outside this repository.

## Historical targeted author-review account


The authors report a targeted review of 100 model responses with complete
GPT-5.2, Claude-Opus-4.6 Thinking and Gemini-3.1-Pro-Preview (High) judgments,
followed by author inspection. This is a report of an existing review, not a
newly reconstructed independent annotation experiment.

| Selected stratum | Responses |
|---|---:|
| All three judges assigned failure | 80 |
| All three judges assigned success | 10 |
| Judges disagreed | 10 |

| Judge | Passed / 100 |
|---|---:|
| GPT-5.2 | 10 |
| Claude-Opus-4.6 Thinking | 17 |
| Gemini-3.1-Pro-Preview (High) | 16 |

All 10 disagreements were primary-judge failures accepted by at least one
auxiliary judge. The authors' inspection discussed explicit category labels,
format requirements, evidence roles and implicit versus complete satisfaction.
An inspectable disagreement example is
[MCL-0087](../../examples/synthetic/02_Temporal/04_Sports_Actions/MCL-0087_synthetic/case.json),
Turn 4. Its reported three-judge scores were 0/0/1 for the primary, Claude and
Gemini judges, respectively. This is an illustrative author-reported case;
complete three-judge records and per-sample human labels for the 100 responses
are not included in this package.

### Interpretation

The 90% complete agreement is a property of this deliberately composed sample.
The sample was selected partly by judge agreement, so this percentage is not
an unbiased estimate of agreement in the benchmark population. It is also not
judge-human agreement, a human solution success rate, or evidence of 90%
judge accuracy. No confusion matrix, kappa or single-failed-rubric human
agreement is inferred from these aggregate counts.

This targeted response review is distinct from a random case-validity audit.
It does not certify the answerability or rubric quality of all cases.

## Inspect single-requirement failures

A separate [inspection guide and record index](../evaluation_reconciliation/SINGLE_FAILURE_REVIEW.md)
locates 1,184 existing task-model failures with one unsatisfied entry and
provides eight public examples. These records are not the historical author
review sample and do not have newly inferred human correctness labels.
