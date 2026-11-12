# Evaluation Protocol

This directory exposes both the command-line implementation and the
provider-independent validation utilities for the paper's evaluation
protocol.

## Paper main configuration

The paper's main benchmark evaluation covers the following eight model settings:

1. Gemini-2.5-pro
2. Gemini-3.1-Pro-Preview (High)
3. GPT-5.2
4. Doubao-Seed-2.0-pro
5. Claude-Sonnet-4.6
6. Claude-Sonnet-4.6 Thinking
7. Claude-Opus-4.6
8. Claude-Opus-4.6 Thinking

GPT-5.2 is the primary judge for the paper's main task-success results. The
machine-readable configuration is in `configs/paper_main_protocol.json`.
Compatible auxiliary-judge paths remain available in the runtime, but they are
not silently pooled with the primary score.

## Inference inputs

The runtime does not inject a benchmark-wide system prompt. It preserves the
message sequence stored in each case. Provider-specific role conversion is
performed only when required by a provider API.

Each `case.json` is a list of ordered task records. The runtime first uses
`metadata.context_id` and `metadata.turn_index` to recover sequence membership
and order, with a task-ID suffix fallback when those fields are absent. After
turn \(t\), the same model's actual output replaces the corresponding
assistant message before turn \(t+1\) is generated. Outputs from another model
must never be inserted.

The main-evaluation history policy is `full`: preceding user text and media remain
available together with the replaced assistant answers. The runtime also
implements explicit fallback profiles for provider payload limits; any such
fallback is recorded in the saved output.

`scripts/materialize_sequential_inputs.py` is a provider-independent review
helper for inspecting this same-model history transformation:

```bash
python evaluation/scripts/materialize_sequential_inputs.py \
  --case examples/synthetic/03_Evidence/04_Layouts_and_Maps/MCL-0143_synthetic/case.json \
  --history predictions/MCL-0143.history.json \
  --output requests/MCL-0143.requests.jsonl
```

## Media preprocessing

- Input images use an initial maximum side length of 2,000 pixels. Re-encoding
  starts at JPEG quality 90 when an image exceeds the 4.5 MiB threshold.
- For non-Doubao model paths, local videos are converted to JPEG frames using
  nominal 2 FPS sampling and at most 50 frames per video. The primary OpenCV
  path samples uniformly over the full duration and encodes frames at JPEG
  quality 80.
- Doubao receives up to 10 native video parts. Additional local videos are
  converted at 0.2 FPS with at most 8 frames per video.
- The OpenAI-compatible path initially targets at most 50 image parts and the
  Claude path at most 100. When a provider image-count limit is exceeded,
  images are pairwise tiled rather than silently dropped.

These transformations are implementation details of provider adaptation; they
are not additional benchmark tasks or scoring rules.

## Primary judge contract

The GPT-5.2 judge receives one user-role grading message containing only:

1. the ordered, enumerated task-level rubrics; and
2. the evaluated model's response.

It does not receive the original conversation, original system message,
images, videos, or inference-model identity. The judge therefore evaluates
the response against the explicit rubric rather than independently resolving
the original multimodal task.

The exact grading instruction is stored in
`prompts/task_level_judge.md` and embedded verbatim in
`runtime/run_backend.py`. It requests one `yes`/`no` decision per rubric, a
grading rationale, and an overall binary score.

The paper's task-success rule is strict and all-or-nothing:

```text
score = 1 if every explicit rubric requirement is satisfied
score = 0 otherwise
```

Rubric-level decisions are diagnostic outputs; they are not averaged into the
primary task-success score.

## Runtime and public QA

The executable provider runtime is in `runtime/`. See
`runtime/README.md` for setup and dry-run commands. Credentials, private
endpoints, provider account metadata, response IDs, request logs, and
non-anonymized provider directories are excluded.

## Released 60-example records

`released_examples/` contains the anonymized outputs and GPT-5.2 judgments for
the eight main-paper model settings on the 60 public examples. It includes
1,392 predictions and 1,392 judgments, explicit API-error records, a
deterministic correction log, committed reference summaries, and a
reaggregation script.

Run:

```bash
python evaluation/scripts/reproduce_released_examples.py \
  --output-dir reproduced/released_examples
```

The script checks all 174 tasks × 8 models, prediction/judgment pairing,
GPT-5.2 judge identity, error handling, and the strict all-or-nothing score
rule. These subset results are not substituted for the full 344-case
leaderboard.

The schemas under `schemas/` define public prediction and judge-result
records. The public post-processing gate adds stricter checks than the raw
provider parser: `aggregate_judgments.py` rejects missing rubric decisions,
non-binary values, duplicate task/model records, and scores inconsistent with
the all-or-nothing rule.

Use `reproduce_released_examples.py`, rather than the generic aggregator, for
the committed 60-example snapshot. It additionally verifies complete
prediction/judgment pairing and accounts for multiline logical rubrics that
occupy more than one serialized case-JSON entry.

```bash
python evaluation/scripts/validate_examples.py --examples examples
python evaluation/scripts/aggregate_judgments.py \
  --cases examples \
  --judgments path/to/judgments.jsonl \
  --output path/to/summary.json
```

## Interpretation boundary

Task-level success measures end-to-end performance under actual sequential
interaction. Because preceding model outputs are reused, it may include both
independent task failures and later failures associated with earlier model
states. The paper's aggregate rate is not presented as a causal
decomposition of those two mechanisms.

The released implementation makes the evaluation procedure inspectable.
Sequence-level associations are not presented as causal estimates of error
propagation.
