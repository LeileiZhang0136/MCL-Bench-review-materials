# Evaluation reconciliation

The original overall rates match first-turn scores, not all 1,080 tasks.
Stored score reproduction below includes missing-score tasks as end-to-end failures.

| Model | First-turn pass / 344 | First-turn % | All-task pass / 1,080 | All-task % |
|---|---:|---:|---:|---:|
| Claude-Opus-4.6 Thinking | 40 | 11.63 | 135 | 12.50 |
| Claude-Opus-4.6 | 38 | 11.05 | 114 | 10.56 |
| Claude-Sonnet-4.6 Thinking | 41 | 11.92 | 141 | 13.06 |
| Claude-Sonnet-4.6 | 43 | 12.50 | 140 | 12.96 |
| Gemini-3.1-Pro-Preview (High) | 42 | 12.21 | 104 | 9.63 |
| GPT-5.2 | 44 | 12.79 | 116 | 10.74 |
| Doubao-Seed-2.0-pro | 29 | 8.43 | 82 | 7.59 |
| Gemini-2.5-pro | 37 | 10.76 | 79 | 7.31 |

## Thinking comparison

Paired case-cluster bootstrap; 10,000 resamples, seed 23049.
- Claude-Opus-4.6 Thinking minus base: 1.94 percentage points, 95% interval [0.27, 3.74].
- Claude-Sonnet-4.6 Thinking minus base: 0.09 percentage points, 95% interval [-2.00, 2.07].

## Data boundaries

Ten rows have no valid stored score and are counted as failures.
One count-aligned Gemini-2.5-pro row has score 1 with a failed requirement; see summary.json.
Keeping stored scores gives 79/1,080 (7.31%); deterministic status normalization gives 78/1,080 (7.22%).
Neither policy is silently substituted for the historical scores.
Rubric summaries cover model-specific count-aligned subsets, not all criteria or an identical cross-model subset.
No human labels, judge-human agreement or independent answerability validation are inferred from these scores.
