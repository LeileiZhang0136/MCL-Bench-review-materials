# Reproducible Synthetic-Case Construction

This package is the executable reference implementation of the synthetic-case
construction pipeline for Multimodal-CLBench. It calls the GPT-5.5 API through
the Responses API. The configuration identifies the model as `gpt-5.5`; no
dated model snapshot is claimed.

The source allowlist contains:

- SlideVQA
- MMLongBench-Doc

In the manuscript, the construction pipeline is described as four outer
workflow steps: source curation, quality filtering, case-specific context
construction, and task/rubric generation. The `Self-Construct`,
`Self-Evolve`, and `Self-Improve` labels in this package describe iterative
operations within that outer workflow, not a competing three-step account.
`Self-Construct` drafts the grounded case program and its initial tasks and
rubrics; `Self-Evolve` changes the challenge structure while preserving source
facts; and `Self-Improve` performs validator-routed revisions.

All 189 synthetic cases in the paper were generated with the GPT-5.5 API through
a common synthetic-case method, using source material from the SlideVQA and
MMLongBench-Doc dataset families. This package exposes the prompts, schemas,
validators, configuration, and runnable reference code for that method.

The manuscript phrase “public and author-collected multimodal sources” refers
to materials that the authors curated and locally materialized from these two
public dataset families. It does not denote a third undisclosed source dataset.

## Pipeline

```text
Source Lock
    |
    v
Self-Construct --grounding failure--> reconstruct or reject source
    |
    v
Self-Evolve ----shortcut failure----> evolve again
    |
    v
Self-Improve ---rubric/gold failure--> targeted repair (up to 3 attempts)
    |
    v
Independent Release Gate
    | pass
    v
Accepted new case + immutable audit trail
```

The operational contract and failure routing are defined in
[`METHOD_CLOSED_LOOP.md`](METHOD_CLOSED_LOOP.md). Prompt files are under
`prompts/`, machine-readable objects are defined in `scripts/models.py`, and
release checks are implemented in `scripts/validate_release.py`.

## Environment

Python 3.12 is the tested runtime. Install the exact tested dependency set:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
cp .env.example .env
```

`requirements.txt` records compatible ranges; `requirements-lock.txt` records
the tested versions. Set `OPENAI_API_KEY` in the shell or local `.env`. Never
commit the key.

Check the installed SDK interface without making an API call:

```bash
python scripts/check_api_interface.py
```

## Reproduce one new case

Prepare a candidate JSON file that points to locally materialized source
assets:

```bash
python scripts/generate_case.py \
  --candidate examples/candidate.example.json \
  --source-root /path/to/case数据集 \
  --output-dir runs/example
```

Then run deterministic release checks. Relative media paths are resolved
against the same source root:

```bash
python scripts/validate_release.py \
  --bundle runs/example/release_bundle.json \
  --source-root /path/to/case数据集
```

For every stage, the internal run bundle saves:

- configured model identifier and API parameters;
- rendered prompt and its SHA-256 hash;
- input asset hashes;
- parsed structured output;
- response identifier and token usage;
- validation failures and retry routing.

The generated `release_bundle.json` is an internal audit artifact. Before
public release, use `scripts/export_release.py`. The exporter rewrites media
paths, removes response identifiers from the public copy, and strips
machine-local prompt, asset, and output paths.

## Reproduce source filtering and reference case generation

```bash
python scripts/filter_sources.py \
  --source-root /path/to/case数据集 \
  --output-dir manifests/source_filter_v1

python scripts/prepare_release_candidates.py \
  --formal-candidates manifests/source_filter_v1/formal_candidates.jsonl \
  --source-root /path/to/case数据集 \
  --output-dir manifests/reference_reexecution_189
```

Run a smoke test before executing the complete reference plan:

```bash
python scripts/run_batch.py \
  --manifest manifests/reference_reexecution_189/reference_reexecution_189_manifest.csv \
  --source-root /path/to/case数据集 \
  --runs-dir runs/reference_reexecution_189 \
  --limit 10
```

After inspecting the machine reports, resume:

```bash
python scripts/run_batch.py \
  --manifest manifests/reference_reexecution_189/reference_reexecution_189_manifest.csv \
  --source-root /path/to/case数据集 \
  --runs-dir runs/reference_reexecution_189 \
  --resume
```

This deterministic plan exercises the public reference implementation across
189 candidates. Outputs from this execution are stored as new run artifacts
under the selected `runs/` directory.

For a newly generated release candidate, API generation does not by itself set
`release_status=accepted`. Attach two human reviews and an adjudication with
`attach_human_audit.py`, then verify the bundle with `validate_release.py`.
This prospective human gate is separate from API generation and must be
completed before a newly generated candidate is marked `accepted`.

## 189-case method manifest

`manifests/historical_189_public_manifest.csv` inventories the unchanged
synthetic subset using only public `MCL-0001` to `MCL-0189` case IDs. It
records the taxonomy, task and rubric counts, generation model, and common
construction method without exposing the private legacy-directory mapping.

## Evidence and licensing

See [`EVIDENCE_INDEX.md`](EVIDENCE_INDEX.md) for the mapping from each method
claim to its prompt, schema, script, and audit artifact. Code and original
documentation in this package are licensed under [`LICENSE`](LICENSE).
Third-party datasets and assets remain governed by their upstream terms; see
[`DATA_SOURCES.md`](DATA_SOURCES.md).
