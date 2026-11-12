# Scoped Analysis Summary

## Synthetic versus expert-collected cases

Across the eight main-paper model settings:

- expert-collected: 155 cases, 325 tasks per model, 22.42% task success,
  case-cluster bootstrap 95% CI [17.38, 27.65];
- synthetic: 189 cases, 755 tasks per model, 5.43%, 95% CI [4.25, 6.77];
- expert minus synthetic: 16.99 percentage points, 95% CI [11.81, 22.32].

Bootstrap settings: 10,000 case-cluster resamples, seed `23049`.

Interpretation: this is a descriptive difference associated with source track
and case composition. A lower synthetic pass rate does not establish
answerability, rubric correctness, or case validity.

## Paired multimodal-evidence ablation

Scope: 138 synthetic cases, 551 tasks per model, and 4,408 paired model-task
evaluations across eight models.

- with multimodal evidence: 6.15%, paired case-cluster bootstrap 95% CI
  [4.57, 7.93];
- without that evidence: 2.52%, 95% CI [1.79, 3.31];
- paired difference: 3.63 percentage points, 95% CI [2.02, 5.50].

Bootstrap settings: 10,000 paired case resamples, seed `23049`.

Interpretation: within this paired subset, retaining the multimodal evidence is
associated with higher task success. The result does not establish that all
344 benchmark cases require multimodal evidence.
