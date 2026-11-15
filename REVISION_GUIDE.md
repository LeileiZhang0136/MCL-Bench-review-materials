# Manuscript revision guide

This short index accompanies the revised manuscript with changes highlighted in
deep blue. Page numbers refer to the **35-page highlighted revision**, not the
34-page submitted version. The revised PDF is provided through the submission
system; this repository provides the supporting records and reproduction code.

| Topic | Revised manuscript location | Supporting materials |
|---|---|---|
| Aggregation formula and complete-task scoring | Section 3.3, pp. 6–7; Appendix B.1, pp. 15–16 | [Aggregation records and reproduction](evidence/evaluation_reconciliation/README.md) |
| Corrected success rates and rankings | Table 2, p. 7; corresponding statements in the abstract, introduction, results and conclusion, pp. 1–2 and 7–9 | [First-turn and all-task success counts](evidence/evaluation_reconciliation/SUMMARY.md) |
| Source-track counts and Figure 6 reconciliation | Appendix B.1, Table 5, p. 15; Figure 6, p. 18 | [Task-level records](evidence/evaluation_reconciliation/main_model_task_scores.csv). Figure 6's all-task source-track results remain unchanged. |
| Partial correctness and requirement-count effects | Appendix B.1, Tables 5–6, p. 15 | [Rubric-level and rubric-count diagnostics](evidence/evaluation_reconciliation/RUBRIC_DIAGNOSTICS.md) |
| Existing author review and single-requirement failures | Appendix B.1, pp. 15–16 | [Judge-review scope](evidence/judge_calibration/README.md); [single-failure records and examples](evidence/evaluation_reconciliation/SINGLE_FAILURE_REVIEW.md) |
| Consistent downstream comparisons | Figure 4, p. 8; Appendix D and Figures 7–8, pp. 18–19; Kimi comparison, p. 25; corrected success panels in Figure 13, p. 26 | [Reconciled scores and paired Thinking comparison](evidence/evaluation_reconciliation/SUMMARY.md); [Kimi evaluation](evidence/open_weight_models/README.md) |
| Anonymous material access | Introduction, p. 3; Appendix B.1, p. 16 | [Repository overview](README.md) |

The main eight-model comparison now uses all **1,080 tasks per model**. Its
highest success rate is **13.06% (141/1,080)** for Claude-Sonnet-4.6 Thinking.
Thinking gains are **1.94 percentage points for Opus** and **0.09 for Sonnet**.
These are reconciliations of existing scores. The author-review account and
single-failure records are distinguished from newly collected human labels;
no new judge–human agreement estimate is claimed.
