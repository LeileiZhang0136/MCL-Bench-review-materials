# Rubric-level and rubric-count diagnostics

## Rubric satisfaction

This table includes nonempty records with equal serialized rubric and status counts.
Coverage is model-specific; it is not an identical shared subset or a ranking.

| Model | Eligible tasks | Satisfied / eligible entries | Satisfaction | Single-entry failed tasks |
|---|---:|---:|---:|---:|
| Claude-Opus-4.6 Thinking | 855 | 3611/5487 | 65.81% | 206 |
| Claude-Opus-4.6 | 865 | 3219/5547 | 58.03% | 151 |
| Claude-Sonnet-4.6 Thinking | 867 | 3646/5553 | 65.66% | 214 |
| Claude-Sonnet-4.6 | 865 | 3347/5533 | 60.49% | 164 |
| Gemini-3.1-Pro-Preview (High) | 869 | 2973/5578 | 53.30% | 93 |
| GPT-5.2 | 869 | 3346/5572 | 60.05% | 158 |
| Doubao-Seed-2.0-pro | 869 | 2812/5559 | 50.58% | 99 |
| Gemini-2.5-pro | 867 | 2841/5542 | 51.26% | 99 |

## Task success by serialized rubric count

All 1,080 tasks per model enter this breakdown. Counts are serialized entries,
not an independently reconciled number of logical criteria.

| Model | Entries per task | Passed / tasks | Success |
|---|---|---:|---:|
| Claude-Opus-4.6 Thinking | 1-4 | 14/121 | 11.57% |
| Claude-Opus-4.6 Thinking | 5-8 | 99/668 | 14.82% |
| Claude-Opus-4.6 Thinking | 9-12 | 19/273 | 6.96% |
| Claude-Opus-4.6 Thinking | 13+ | 3/18 | 16.67% |
| Claude-Opus-4.6 | 1-4 | 18/121 | 14.88% |
| Claude-Opus-4.6 | 5-8 | 80/668 | 11.98% |
| Claude-Opus-4.6 | 9-12 | 14/273 | 5.13% |
| Claude-Opus-4.6 | 13+ | 2/18 | 11.11% |
| Claude-Sonnet-4.6 Thinking | 1-4 | 21/121 | 17.36% |
| Claude-Sonnet-4.6 Thinking | 5-8 | 100/668 | 14.97% |
| Claude-Sonnet-4.6 Thinking | 9-12 | 19/273 | 6.96% |
| Claude-Sonnet-4.6 Thinking | 13+ | 1/18 | 5.56% |
| Claude-Sonnet-4.6 | 1-4 | 18/121 | 14.88% |
| Claude-Sonnet-4.6 | 5-8 | 87/668 | 13.02% |
| Claude-Sonnet-4.6 | 9-12 | 33/273 | 12.09% |
| Claude-Sonnet-4.6 | 13+ | 2/18 | 11.11% |
| Gemini-3.1-Pro-Preview (High) | 1-4 | 17/121 | 14.05% |
| Gemini-3.1-Pro-Preview (High) | 5-8 | 83/668 | 12.43% |
| Gemini-3.1-Pro-Preview (High) | 9-12 | 4/273 | 1.47% |
| Gemini-3.1-Pro-Preview (High) | 13+ | 0/18 | 0.00% |
| GPT-5.2 | 1-4 | 16/121 | 13.22% |
| GPT-5.2 | 5-8 | 84/668 | 12.57% |
| GPT-5.2 | 9-12 | 13/273 | 4.76% |
| GPT-5.2 | 13+ | 3/18 | 16.67% |
| Doubao-Seed-2.0-pro | 1-4 | 13/121 | 10.74% |
| Doubao-Seed-2.0-pro | 5-8 | 65/668 | 9.73% |
| Doubao-Seed-2.0-pro | 9-12 | 4/273 | 1.47% |
| Doubao-Seed-2.0-pro | 13+ | 0/18 | 0.00% |
| Gemini-2.5-pro | 1-4 | 15/121 | 12.40% |
| Gemini-2.5-pro | 5-8 | 60/668 | 8.98% |
| Gemini-2.5-pro | 9-12 | 4/273 | 1.47% |
| Gemini-2.5-pro | 13+ | 0/18 | 0.00% |

## Definitions and scope

- Satisfaction is yes statuses divided by entries in count-aligned records, pooled within each model.
- Equal counts are a structural screen and do not certify semantic alignment or correct judgments.
- Single-entry failed tasks have effective score zero and exactly one non-yes status in the eligible subset. This is not a human error label.
- Count-stratified success is successful tasks divided by all tasks in that bucket. Missing scores remain end-to-end failures, consistently with the score export.
- Stored-score and status-normalized results differ for one Gemini-2.5-pro task; the stored-score policy is used here and the reconciliation documents its sensitivity.
- Rubric count is associated with task family and difficulty; these strata do not identify a causal effect of requirement count.
- These are existing-record diagnostics, not new model calls or human evaluations.

## Reproduce

```bash
python evidence/evaluation_reconciliation/reproduce_rubric_diagnostics.py --output-dir reproduced/rubric_diagnostics
```
