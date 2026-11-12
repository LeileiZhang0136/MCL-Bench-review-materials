# Release Package Status

## Completed and verified

- GPT-5.5 API reference implementation uses the Responses API and records the
  model identifier as `gpt-5.5`; no dated snapshot is claimed.
- Source allowlist is fixed to SlideVQA and MMLongBench-Doc.
- The reproducible filter snapshot contains 677 formal candidates:
  542 SlideVQA and 135 MMLongBench-Doc.
- A deterministic 189-case reference execution plan was generated with seed
  `23049`:
  95 SlideVQA and 94 MMLongBench-Doc.
- Taxonomy allocation is 48/47/47/47 across the four benchmark categories.
- The 189 candidate files reference 2,263 selected visual assets. All paths and
  SHA-256 hashes passed offline verification.
- Pydantic schemas, deterministic validators, human-review templates,
  three-attempt Self-Improve logic, four-variant ablation coverage checks,
  batch resume logic, and anonymizing release export are present.
- Offline tests cover the core validators, relative media resolution,
  four-variant ablation completeness, and anonymous public export.
- The OpenAI Python SDK interface is pinned to version 2.48.0;
  `responses.parse` supports the `model`, `input`, `text_format`, `reasoning`,
  and `store` arguments used by the runner.

## Additional execution status

- The deterministic reference manifest has not been run in this
  environment because `OPENAI_API_KEY` is not currently set; no re-execution
  candidate is marked `accepted`.
- Prospective human reviews and adjudications have not been collected for new
  reference execution candidates.
- Upstream/underlying-asset redistribution permissions still require a
  case-level review before assets are copied to a public GitHub repository.

## Next executable step

To run the reference execution, configure the API key, install
`requirements-lock.txt`, and run a ten-case smoke test:

```bash
python scripts/run_batch.py \
  --manifest manifests/reference_reexecution_189/reference_reexecution_189_manifest.csv \
  --source-root "/path/to/case数据集" \
  --runs-dir runs/reference_reexecution_189 \
  --limit 10
```

Inspect the ten `machine_validation.json` and `release_bundle.json` files before
resuming all 189 cases.
