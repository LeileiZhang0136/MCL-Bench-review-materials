# MCL-Bench Reviewer Examples

This anonymized package contains **60 representative example cases** spanning all four major categories and all 20 subcategories of MCL-Bench. It is an example package, not the full 344-case benchmark.

- Synthetic cases: 17
- Expert-collected cases: 43
- Tasks: 174
- Included serialized rubric entries: 1,163

Each example includes its complete case JSON and all task-level rubric text.
Case-local images are stored under each case's `assets/` directory. Videos keep
the same case-local paths but are distributed as the separately checksummed
external asset attachment documented in `../assets/EXTERNAL_ASSETS.md`.
Redistribution status is tracked in `../assets/asset_manifest.csv`; technical
availability is not presented as a license determination. The corresponding
anonymized eight-model outputs and GPT-5.2 judgments are stored separately in
`../evaluation/released_examples/`. API credentials, response identifiers, raw
provider directories, and legacy contributor names are excluded.

The authoritative taxonomy is stored in `case_metadata.json`, `manifest_public.csv`, directory names, and subcategory `index.json` files. Historical placeholder fields `context_category` and `sub_category` are omitted from task metadata.
