# Provider Runtime

This directory contains the command-line implementation used to run model
inference and rubric-based evaluation.

## Public configuration

Copy the empty configuration template and fill in only local credentials and
provider endpoints:

```bash
cp evaluation/runtime/app_config.env.example \
  evaluation/runtime/app_config.env
```

The `CLBENCH_*` environment-variable prefix is retained for backward
compatibility with the evaluation implementation. Real credentials, endpoints,
response IDs, account metadata, logs, and outputs must not be committed.

Install dependencies:

```bash
python -m pip install -r evaluation/runtime/requirements.txt
```

## Single-case dry run

```bash
bash evaluation/runtime/run_backend.sh \
  examples/synthetic/03_Evidence/04_Layouts_and_Maps/MCL-0143_synthetic/case.json \
  examples/synthetic/03_Evidence/04_Layouts_and_Maps/MCL-0143_synthetic/assets \
  --dry-run
```

## Inference and primary judging

```bash
bash evaluation/runtime/run_backend.sh CASE_JSON ASSET_DIRECTORY \
  --stage full \
  --infer-model "GPT 5.2" \
  --judge-model "GPT 5.2" \
  --apply-history \
  --history-media-policy full
```

`run_batch.py` contains the eight evaluated-model names. Its default judge list
contains only the paper's primary judge, GPT-5.2. Other compatible judges may
be passed explicitly with `--eval-models`, but such auxiliary runs must not be
described as part of the paper's primary-score protocol unless their results
are reported separately.

The runtime parser preserves the raw judge fields. The stricter public
post-processing gate in `../scripts/aggregate_judgments.py` additionally checks
the number and values of rubric decisions and recomputes the all-or-nothing
score before aggregation.
