# Inspecting single-requirement failures

## Located records

The count-aligned existing-score records contain 1184 failed task-model responses with exactly one non-yes status. These are response records, not distinct tasks or human-labeled errors.

| Inference model | Records |
|---|---:|
| Claude-Opus-4.6 | 151 |
| Claude-Opus-4.6 Thinking | 206 |
| Claude-Sonnet-4.6 | 164 |
| Claude-Sonnet-4.6 Thinking | 214 |
| Doubao-Seed-2.0-pro | 99 |
| GPT-5.2 | 158 |
| Gemini-2.5-pro | 99 |
| Gemini-3.1-Pro-Preview (High) | 93 |

[Complete record index](single_failure_records.csv) identifies the anonymous task, model and failed serialized-entry position.
[Illustrative responses](single_failure_examples.jsonl) include the full released response, rubric list, statuses and grading rationale.
Examples are selected as the first eligible public record per inference model in the index order.
They must have a failing public judgment, equal rubric/status counts and the indexed single failure.
This is an inspectable panel, not a statistical or human-validity sample.

## What to inspect

- Does the failed item express an explicit task requirement?
- Does the rationale identify a substantive rule, evidence or state-update violation?
- Does it instead penalize a meaning-preserving paraphrase, an undeclared formatting restriction or harmless background explanation?
- Are the serialized entry and the intended logical criterion actually aligned? Equal list lengths alone do not establish this.

## Relationship to existing author review

The [historical targeted author-review account](../judge_calibration/README.md#historical-targeted-author-review-account) reports 100 reviewed responses.
The new record index is not that historical review set. No human labels, judge-human agreement, or correctness decisions are inferred for the indexed responses.
The separate three-judge comparison is also not a substitute for human agreement.
These materials expose boundary cases for inspection without claiming that a single failed item is automatically a genuine error or an automatic misjudgment.

## Reproduce

```bash
python evidence/evaluation_reconciliation/reproduce_single_failure.py --output-dir reproduced/single_failure
```
