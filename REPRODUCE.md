# Reproducing the Released MCL-Bench Results

This document gives the execution order for the anonymous research artifact. The
default workflow is offline, deterministic, and does not call a model API.

## 1. Environment

Requirements:

- Python 3.9 or later;
- approximately 400 MB for the ordinary repository;
- an additional approximately 762 MiB if the external video archive is downloaded.

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Only Pillow is needed for the offline package validator. Provider-specific
dependencies are listed separately in
`evaluation/runtime/requirements.txt`.

## 2. Optional External Videos

Images are stored in the ordinary repository. The 24 videos are distributed in
the separately checksummed archive:

```text
../MCL-Bench_release_assets/MCL-Bench_video_assets.tar
```

The integrity checker reads this archive directly; do not extract it into the
ordinary Git working tree before validation. Extraction is unnecessary for the
released numerical summaries. For a live API rerun of a video case, extract
the archive into a disposable copy of the repository so the case-local paths
are restored without changing the validated source tree.

## 3. One-Command Offline Reproduction

Run:

```bash
python tools/reproduce.py
```

This is equivalent to `python tools/reproduce.py offline`. It runs the
following stages in order and writes fresh outputs under `reproduced/`:

| Stage | Public input | Reproduced output | Expected result |
|---|---|---|---|
| Released examples | `examples/`, `evaluation/released_examples/*.jsonl` | `reproduced/released_examples/` | 60 cases, 174 tasks, 8 models, 1,392 predictions and judgments |
| Wilson intervals | Observed full-task counts and historical media counts in `evidence/uncertainty/reproduce_wilson_ci.py` | `reproduced/uncertainty/` | Byte-identical reference JSON, CSV, and Markdown tables |
| Open-weight supplement | `evidence/open_weight_models/open_model_task_scores.csv` | `reproduced/open_weight_models/` | 344 cases and 1,080 paired task rows |
| Full-task reconciliation | `evidence/evaluation_reconciliation/main_model_task_scores.csv` and Kimi scores | `reproduced/evaluation_reconciliation/` | 8,640 model-task rows and paired comparisons |
| Package check | Cases, results, assets, schemas, and manifests | Terminal report only | `technical_status: PASS` |

The last stage uses check-only mode and does not rewrite
`REPOSITORY_VALIDATION.json` or `SHA256SUMS`.

## 4. Reaggregate the 60-Example Main-Model Results

Inputs:

- `examples/**/case.json`;
- `evaluation/released_examples/predictions.jsonl`;
- `evaluation/released_examples/judgments_gpt5.2.jsonl`.

Run:

```bash
python tools/reproduce.py released-examples
```

The underlying script is
`evaluation/scripts/reproduce_released_examples.py`. It verifies:

- exactly 174 public tasks and eight main-paper model settings;
- exactly 1,392 unique task-model predictions and judgments;
- one-to-one prediction/judgment coverage;
- GPT-5.2 as the judge for every released record;
- binary all-or-nothing scoring for completed judgments;
- explicit handling of inference and judge API errors; and
- equality between the recomputed and committed summaries.

The 19 API-error records, one case-text terminology repair, and two
deterministic judgment-field corrections are listed in
`evaluation/released_examples/evaluation_errors.jsonl` and
`evaluation/released_examples/correction_log.json`.

Some multiline logical rubrics occupy multiple serialized array entries.
Therefore the released judgments retain both
`serialized_rubric_entry_count` and `logical_rubric_count_at_judging`.

## 5. Recompute Paper-Result Uncertainty

Run:

```bash
python tools/reproduce.py uncertainty
```

This recomputes task-level Wilson 95% intervals from observed full-task model
counts and separately identified historical media-configuration counts.
Main counts agree with the full-task score export, not the original
first-turn rates or the 60-example subset. Generated
files are checked byte-for-byte against `evidence/uncertainty/`.

## 6. Recompute the Kimi K2.6/K3 Supplement

Run:

```bash
python tools/reproduce.py open-weight
```

This recomputes overall success rates, Wilson intervals, paired counts,
source-track results, and the 10,000-replicate case-cluster bootstrap from
`evidence/open_weight_models/open_model_task_scores.csv`. Generated outputs are
checked against the committed reference summaries.

## 7. Validate Assets and Update SHA-256

A read-only check is:

```bash
python tools/reproduce.py validate \
  --video-archive ../MCL-Bench_release_assets/MCL-Bench_video_assets.tar
```

Release maintainers should update the machine-readable validation report and
root checksums only after every other file is final:

```bash
python tools/reproduce.py validate \
  --video-archive ../MCL-Bench_release_assets/MCL-Bench_video_assets.tar \
  --write-validation
```

Then perform the independent checksum checks:

```bash
shasum -a 256 -c SHA256SUMS
(cd ../MCL-Bench_release_assets && \
  shasum -a 256 -c MCL-Bench_video_assets.tar.sha256)
```

## 8. Optional API Dry Run and Live Evaluation

Install the provider runtime dependencies:

```bash
python -m pip install -r evaluation/runtime/requirements.txt
cp evaluation/runtime/app_config.env.example \
  evaluation/runtime/app_config.env
```

Populate the local, Git-ignored configuration file, then inspect a request
without sending it:

```bash
python tools/reproduce.py api-dry-run
```

For a live single-case run:

```bash
bash evaluation/runtime/run_backend.sh \
  examples/synthetic/03_Evidence/04_Layouts_and_Maps/MCL-0143_synthetic/case.json \
  examples/synthetic/03_Evidence/04_Layouts_and_Maps/MCL-0143_synthetic/assets \
  --stage full \
  --infer-model "GPT 5.2" \
  --judge-model "GPT 5.2" \
  --apply-history \
  --history-media-policy full
```

Live API outputs can differ from the released records because model endpoints
may be nondeterministic or updated. They must not be mixed silently with the
released evaluation snapshot.

## 9. Optional Synthetic-Case Construction

The synthetic package is independent of the offline result reproduction. Its
starting point is:

```bash
python -m pip install -r synthetic_generation/requirements-lock.txt
PYTHONPATH=synthetic_generation/scripts \
  python -m unittest discover -s synthetic_generation/tests -v
```

Then follow `synthetic_generation/README.md` for source filtering,
Self-Construct, Self-Evolve, Self-Improve, validation, and public export. This
workflow uses the GPT-5.5 API only when generation is explicitly requested.

## Reproduction Boundaries

- The 60-example outputs reproduce only the released subset, not the full
  eight-model result table.
- Main intervals use observed full-task counts; media intervals retain historical figure counts.
- The Kimi supplement provides full 344-case binary task scores but not private
  provider logs or free-form outputs.
- The 60 representative examples are not treated as a random human-validity
  audit of the historical synthetic cases.

## Full-task reconciliation

Run `python tools/reproduce.py reconciliation`. This reproduces anonymous
eight-model scores and first-turn versus all-task aggregates. Missing scores
are retained as end-to-end failures. One stored score conflicts with its
status list; both stored-score and normalized sensitivity results are shown.
Rubric diagnostics use count-aligned records only. See
[evaluation_reconciliation](evidence/evaluation_reconciliation/README.md).
The older inferred main-table counts are superseded; this is numerical
reproduction rather than an independent judgment-validity study.
