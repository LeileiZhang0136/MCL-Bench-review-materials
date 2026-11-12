# Full-task and historical-media Wilson intervals

## Analysis contract

- Main authority: released full-task score rows in evaluation_reconciliation; media: historical figure counts.
- Interval: two-sided 95% Wilson score interval.
- Unit: saved model-task evaluation.
- Main-table inferred counts have been superseded by observed full-task counts; see evaluation_reconciliation.
- These intervals do not estimate run-to-run generation variability or case-cluster uncertainty.

## Main model results

| Model | Successes/tasks | Full-task rate | 95% Wilson CI |
|---|---:|---:|---:|
| Claude-Opus-4.6 Thinking | 135/1080 | 12.50% | [10.66, 14.61] |
| Claude-Opus-4.6 | 114/1080 | 10.56% | [8.86, 12.53] |
| Claude-Sonnet-4.6 Thinking | 141/1080 | 13.06% | [11.18, 15.20] |
| Claude-Sonnet-4.6 | 140/1080 | 12.96% | [11.09, 15.10] |
| Gemini-3.1-Pro-Preview (High) | 104/1080 | 9.63% | [8.01, 11.53] |
| GPT-5.2 | 116/1080 | 10.74% | [9.03, 12.73] |
| Doubao-Seed-2.0-pro | 82/1080 | 7.59% | [6.16, 9.33] |
| Gemini-2.5-pro | 79/1080 | 7.31% | [5.91, 9.02] |

## Media-configuration results

| Configuration | Cases | Tasks/model | Successes/evaluations | Paper rate | 95% Wilson CI |
|---|---:|---:|---:|---:|---:|
| Single-video | 17 | 38 | 46/304 | 15.1% | [11.54, 19.59] |
| Multi-video | 12 | 37 | 27/296 | 9.1% | [6.34, 12.95] |
| Image+video | 12 | 34 | 21/272 | 7.8% | [5.10, 11.51] |

## Interpretation boundary

The media groups differ in case composition and difficulty. Their intervals support a descriptive comparison only; they do not identify a causal effect of media configuration. The model intervals quantify task-level uncertainty and are not pairwise significance tests.
