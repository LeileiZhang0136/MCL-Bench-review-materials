# Reporting one primary judge with auxiliary checks

Three judges were used in the existing evaluation records. Main scores are
reported under GPT-5.2, with Claude-Opus-4.6 Thinking and
Gemini-3.1-Pro-Preview (High) available for cross-checking and disagreement
analysis. This is a reporting policy, not a claim that only one judge was run.

## Comparable coverage and scoring scale

The eight-model file inventory contains 2,752 GPT-5.2 case-model files,
2,623 Claude files and 2,488 Gemini files. The corresponding maximum is
344 cases times eight inference models. File presence is not equivalent to
valid task-score coverage; missing scores are handled explicitly.

A single reporting judge keeps the scoring scale consistent across tasks and
inference models. The matched sample demonstrates differences in strictness.
Neither taking the most favorable judge nor interpreting majority vote as
human ground truth resolves those differences. The released auxiliary scores
allow readers to inspect sensitivity rather than conceal it.

The historical targeted author-review account describes explicit-requirement
disagreements, but neither that account nor a stricter pass rate proves
population-level judge accuracy. No claim of a prospectively randomized judge
selection or a pre-registered selection study is made here.

## Operational cost of extending evaluation

For each additional inference model, 1,080 tasks require 1,080 task-level
judgments under one judge, or 3,240 under three judges, excluding retries.
For the original eight inference models this is 8,640 versus 25,920 judgments.
Using two additional judges on 100 responses adds 200 judgments instead of
17,280 for two complete additional sweeps.

These are workload scenarios for future evaluation, not reconstructed API
bills or a claim that historical auxiliary coverage was restricted to 100
responses. Actual cost and latency depend on model prices, tokens, concurrency
and retries; a threefold request count need not mean threefold monetary cost.
