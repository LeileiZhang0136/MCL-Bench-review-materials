# MCL-Bench Anonymous Research Artifact

This anonymous repository accompanies the ICLR submission of
Multimodal-CLBench. It contains inspectable benchmark examples, evaluation
records, reproduction code, prompts, statistical evidence, and the executable
synthetic-case construction framework. Start with the offline command below;
it does not call any model API.

## What is a paper result and what is supplementary?

| Scope | Cases | Tasks | Role in this artifact |
|---|---:|---:|---|
| Paper benchmark and main evaluation | 344 | 1,080 | Benchmark totals, main eight-model protocol, and reconciled full-task scores |
| Inspectable example release | 60 | 174 | Complete case JSON, all task rubrics, 1,646 images, and 24 separately packaged videos |
| Stored main-model outputs for the examples | 60 | 174 per model | 1,392 model outputs and 1,392 GPT-5.2 judge records for exact subset reaggregation |
| Reasoning-style transparency examples | 4 (1 overlaps above) | 16 stored outputs | One labeled Turn 1 example per style, complete cases, exact prompts, and all four GPT-5.2 turns |
| Supplementary Kimi K2.6/K3 evaluation | 344 | 1,080 per model | Paired anonymized task scores and reproducible supplementary statistics |

The full benchmark contains 7,309 rubrics. The 60 inspectable examples contain
1,163 serialized rubric entries and comprise 17 synthetic and 43
expert-collected cases, with three examples from each of the 20 subcategories.

## Evaluation reconciliation notice

The original eight-model overall rates correspond to the 344 first-turn
tasks. They must not be interpreted as success across all 1,080 tasks.
[The reconciliation supplement](evidence/evaluation_reconciliation/README.md)
provides 8,640 anonymous task-model rows, corrected full-task aggregates,
paired Thinking comparisons, rubric-count diagnostics and explicit missing or
inconsistent-score handling. The old inferred main-table Wilson counts have
been superseded. These are existing-score analyses, not a rerun or a new
independent validation study.

The [targeted judge-review summary](evidence/judge_calibration/README.md)
distinguishes three-judge agreement from judge-human agreement and now includes
a separately sampled 100-response matched comparison with public score rows
and illustrative grading rationales. An
[inspectable worked solution](evidence/reference_walkthroughs/README.md)
links local rules and visual evidence to a representative task's requirements.

For construction checks and a concrete evidence-to-answer derivation, see the
[synthetic-construction evidence index](evidence/synthetic_validity/README.md).

## Quick Start

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/reproduce.py
```

The last command performs the offline workflow in this order:

1. validates and reaggregates the stored results for the 60 examples;
2. recomputes Wilson intervals for reconciled full-task results and
   media-configuration analysis;
3. recomputes the supplementary Kimi K2.6/K3 statistics;
4. reproduces the full-task reconciliation and paired Thinking comparison; and
5. runs repository integrity and anonymization checks without rewriting
   tracked files.

Expected subset coverage is 60 cases, 174 tasks, eight main-paper model
settings, 1,392 predictions, and 1,392 GPT-5.2 judgments. Recomputed files are
written under the ignored `reproduced/` directory.

To also verify the 24 external videos, place the archive beside the repository
and run:

```bash
python tools/reproduce.py validate \
  --video-archive ../MCL-Bench_release_assets/MCL-Bench_video_assets.tar
```

See [`REPRODUCE.md`](REPRODUCE.md) for every input, command, expected output,
optional API rerun, and the synthetic-generation workflow.

## Reproduce Results

| Goal | Command | Reference output |
|---|---|---|
| Reaggregate the stored eight-model results for the 60 examples | `python tools/reproduce.py released-examples` | `evaluation/released_examples/summary.json` |
| Recompute uncertainty for the paper results | `python tools/reproduce.py uncertainty` | `evidence/uncertainty/` |
| Recompute the supplementary Kimi K2.6/K3 statistics | `python tools/reproduce.py open-weight` | `evidence/open_weight_models/` |
| Reconcile all eight models | `python tools/reproduce.py reconciliation` | `evidence/evaluation_reconciliation/` |
| Check repository integrity | `python tools/reproduce.py validate` | `REPOSITORY_VALIDATION.json` |
| Inspect an API request without sending it | `python tools/reproduce.py api-dry-run` | terminal validation output |

The stored 60-example records support exact reaggregation for that subset.
Full-benchmark anonymous score rows now separately support reaggregation of
the eight-model results. The original overall rates match first-turn scores,
not full-task rates; see the reconciliation notice below.

## Repository Map

- [`examples/`](examples/README.md): 60 complete anonymized cases and local
  assets.
- [`evaluation/released_examples/`](evaluation/released_examples/README.md):
  main-model outputs, GPT-5.2 judgments, error records, correction log, and
  reference aggregates for the 60 examples.
- [`evaluation/`](evaluation/README.md): provider runtime, exact judge prompt,
  same-model sequential-history handling, schemas, and aggregation code.
- [`evidence/`](evidence/README.md): score reconciliation, targeted review, reference reasoning, scoped analyses,
  and the full-benchmark Kimi K2.6/K3 supplement.
- [`reasoning-style analyses`](<evidence/analysis/reasoning-style analyses/README.md>):
  reasoning-style codebook, exact labeling prompts, and four complete
  representative cases with stored GPT-5.2 responses.
- [`synthetic_generation/`](synthetic_generation/README.md): prompts, schemas,
  validators, and executable GPT-5.5 API reference implementation.
- [`assets/`](assets/README.md): asset manifest and external-video packaging.
- [`tools/`](tools/README.md): unified reproduction entry point and
  repository-wide validation.
- [`documentation/`](documentation/README.md): paper-aligned technical notes.
- [`RELEASE_STATUS.md`](RELEASE_STATUS.md): completed materials and claim
  boundaries.

## Evaluation Principle

A task receives one only when every logical task-level rubric decision is
`yes`; otherwise it receives zero. GPT-5.2 is the primary judge for the
paper's main eight-model evaluation. It receives the ordered rubrics and model
response, but not the original multimodal conversation or inference-model
identity.

The stored subset retains 19 inference or judge API errors as explicit error
records and counts them as end-to-end task failures. The correction log records
one terminology repair in `MCL-0087_T1` and two deterministic normalizations of
malformed stored judgment fields.

## Claim Boundaries

- The 60 cases are representative inspectable examples, not a random or
  human-validated audit sample.
- Their aggregate results must not be substituted for the full 344-case main
  result table.
- Wilson intervals quantify task-level uncertainty and not run-to-run model
  variation.
- The media comparison is observational and does not identify a causal effect
  of media configuration.
- The Kimi K2.6/K3 results are supplementary and are not retroactively inserted
  into the paper's eight-model main table.
- The synthetic package is an executable reference implementation; running it
  creates new cases and is separate from offline result reproduction.

## Double-Blind Anonymization

The repository uses public `MCL-xxxx` identifiers and anonymous expert codes.
Author identities, private source mappings, provider request identifiers,
credentials, account metadata, and machine-local paths are excluded. See
[`ANONYMITY.md`](ANONYMITY.md) for the complete policy.
