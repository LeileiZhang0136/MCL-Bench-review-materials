# Matched three-judge comparison

This is a new offline analysis of existing judgments, not the historical 100-response author review.
All judges saw identical response text and rubrics for each included item.

| Judge | Passed / 100 | Pass rate |
|---|---:|---:|
| GPT-5.2 | 13 | 13.0% |
| Claude-Opus-4.6 Thinking | 38 | 38.0% |
| Gemini-3.1-Pro-Preview (High) | 28 | 28.0% |

All three judges agree on 71/100 responses.

| Judge pair | Agreement | Cohen kappa |
|---|---:|---:|
| GPT-5.2 / Claude-Opus-4.6 Thinking | 75.0% | 0.392 |
| GPT-5.2 / Gemini-3.1-Pro-Preview (High) | 85.0% | 0.555 |
| Claude-Opus-4.6 Thinking / Gemini-3.1-Pro-Preview (High) | 82.0% | 0.597 |

## Per-model composition

| Inference model | Responses | GPT passes | Claude passes | Gemini passes |
|---|---:|---:|---:|---:|
| Claude-Opus-4.6 | 13 | 2 | 6 | 4 |
| Claude-Opus-4.6 Thinking | 13 | 4 | 10 | 7 |
| Claude-Sonnet-4.6 | 13 | 3 | 5 | 3 |
| Claude-Sonnet-4.6 Thinking | 13 | 0 | 6 | 5 |
| Doubao-Seed-2.0-pro | 12 | 1 | 4 | 1 |
| GPT-5.2 | 12 | 1 | 1 | 1 |
| Gemini-2.5-pro | 12 | 1 | 3 | 4 |
| Gemini-3.1-Pro-Preview (High) | 12 | 1 | 3 | 3 |

## Interpretation

This is a deliberately stratified sample; the reported values describe this sample rather than population-calibrated accuracy.
Agreement among automated judges is not judge-human agreement.
No ranking stability or independence of self-preference is inferred from 12–13 responses per inference model.
Complete pairwise tables, positive/negative agreement, and sample composition are provided in matched_sample_summary.json.
