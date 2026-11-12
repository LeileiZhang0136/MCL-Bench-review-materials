# Package Validation

Validation date: 2026-07-29

## 189-case method manifest

- Synthetic-case method manifest: 189 rows.
- Public anonymized manifest rows: 189.
- Private legacy-directory mappings included: no.
- Released case content modified by this package: no.
- Public method fields: case ID, taxonomy, task/rubric counts, generation
  model, and construction method.

## Reference execution plan

- Planned cases: 189.
- Status for every planned case: `not_run_reference_reexecution`.
- Purpose: deterministic execution of the public reference implementation.
- Selected visual assets: 2,263.
- Relative asset paths and SHA-256 hashes verified during plan generation.

## Implementation checks

- Offline unit tests: 7 passed.
- Relative-media resolution against `source-root`: passed.
- Self-Improve retry budget and routing: passed.
- Four ablation variants for every task: enforced and tested.
- Public-bundle path and response-ID sanitization: passed.
- Locked OpenAI SDK interface check: passed with `openai==2.48.0`.
- Live GPT-5.5 API call performed during package validation: no.

## Release scan

- Public JSON files parse without errors.
- Dated GPT-5.5 snapshot strings: 0.
- Legacy API-pending reference-plan statuses: 0.
- Author-specific absolute home paths: 0.
- Secret-like API keys: 0.
- `.DS_Store`, `__pycache__`, and `.pyc` files: 0.

The checks above establish package consistency and inspectability.
