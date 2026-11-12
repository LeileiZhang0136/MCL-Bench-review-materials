# Supplementary Open-Weight Model Evaluation

This directory reports a completed supplementary evaluation of Kimi K2.6 and
Kimi K3. It is separate from the paper's main eight-model result table.

## Scope and protocol

Both models were evaluated on the same 344 cases and 1,080 ordered tasks. Each
case uses same-model sequential history: the model's actual response at an
earlier turn is reused at the next turn. GPT-5.2 is the primary judge, and a
task passes only when every task-level rubric is satisfied.

The public task table contains no model outputs, judge rationales, legacy case
names, contributor identifiers, private paths, service endpoints, or account
metadata. Case and task identifiers use only the anonymous `MCL-xxxx/Tn`
scheme.

## Main results

| Model | Passed / tasks | Success rate | Wilson 95% CI |
|---|---:|---:|---:|
| Kimi K2.6 | 139 / 1,080 | 12.87% | [11.00%, 15.00%] |
| Kimi K3 | 241 / 1,080 | 22.31% | [19.93%, 24.89%] |

Kimi K3 has the highest task-success rate among the ten model settings
evaluated to date. On the 1,080 matched tasks, 103 tasks are passed by both
models, 36 only by Kimi K2.6, 138 only by Kimi K3, and 803 by neither. The
paired difference is 9.44 percentage points, with a 344-case cluster-bootstrap
95% interval of [6.90, 11.90] percentage points.

The paper's eight-model point estimates remain unchanged and are reproduced
separately in `../uncertainty/paper_main_wilson_ci.csv`. The Kimi results are
reported as a supplementary evaluation rather than inserted retrospectively
into the paper's main result table.

The improvement appears in both source tracks:

| Source track | Kimi K2.6 | Kimi K3 | Difference |
|---|---:|---:|---:|
| Synthetic: 189 cases, 755 tasks | 7.28% | 17.62% | +10.33 points |
| Expert-collected: 155 cases, 325 tasks | 25.85% | 33.23% | +7.38 points |

## Interpretation boundary

The within-family paired gain supports the conclusion that MCL-Bench is
sensitive to meaningful capability differences rather than imposing a uniform
low-performance floor. Kimi K3 has also been reported in the frontier tier of
independent general-capability evaluations; see the
[Kimi K3 technical report](https://arxiv.org/abs/2607.24653) and the
[Artificial Analysis evaluation](https://artificialanalysis.ai/articles/kimi-k3-achieves-3-in-the-artificial-analysis-intelligence-index-comparable-to-opus-4-8-and-gpt-5-5/).
This contextual evidence and the MCL-Bench result are mutually consistent, but
they do not establish that a single general-intelligence score causally
determines MCL-Bench performance. Kimi K3 still fails 77.69% of tasks, leaving
substantial headroom.

## Files and reproduction

- `open_model_task_scores.csv`: anonymized paired task scores.
- `open_model_summary.csv` and `.json`: overall and grouped results.
- `paired_comparison.csv` and `.json`: paired counts, uncertainty, and source
  track analyses.
- `supplementary_kimi_protocol.json`: sanitized protocol record.
- `validation_report.json`: coverage and cross-model input checks.
- `reproduce_open_model_results.py`: standard-library reproduction script.

Run:

```bash
python evidence/open_weight_models/reproduce_open_model_results.py
```

The script uses 10,000 case-cluster bootstrap replicates with seed `23049`.
Tasks at turns 5 and 6 are retained in the overall result but should not be
interpreted separately because their sample sizes are only seven and one.
