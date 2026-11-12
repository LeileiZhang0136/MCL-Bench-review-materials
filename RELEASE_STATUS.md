# Artifact Status

## Paper-aligned materials

- The paper benchmark comprises 344 cases, 1,080 ordered tasks, and 7,309
  rubrics.
- The main evaluation protocol covers eight model settings and uses GPT-5.2 as
  the primary judge. Its machine-readable configuration is
  `evaluation/configs/paper_main_protocol.json`.
- The repository includes paper-result Wilson intervals and bounded scoped
  analyses. These are distinct from the stored 60-example outputs.

## Inspectable example release

- Sixty complete cases cover all 20 subcategories, with three examples per
  subcategory.
- The cases contain complete task messages and all associated rubrics.
- Previous-turn assistant positions contain only `[WAITING_FOR_FILL]`;
  evaluated outputs are stored separately from case definitions.
- The release includes 1,392 anonymized outputs and 1,392 GPT-5.2 judgment
  records for the eight main-paper model settings, plus an error list,
  correction log, reference summaries, and reaggregation script.
- `MCL-0087_T1` contains a logged terminology repair aligning the rubric label
  `peer-driven` with the task label `companion-driven`; this does not alter the
  intended category or released scores.

## Supplementary evidence

- The Kimi K2.6 and Kimi K3 evaluation covers all 344 cases and 1,080 tasks.
  Anonymized paired task scores, protocol details, uncertainty estimates, and a
  reproduction script are included. These results are supplementary rather
  than part of the paper's main eight-model table.
- The reasoning-style transparency package contains the codebook, exact
  prompts, and one complete representative case per category.
- The synthetic construction package provides prompts, schemas, validators,
  configuration, and an executable GPT-5.5 API reference implementation.

## Technical validation

- Repository-wide validation covers 60 cases, 174 tasks, 1,163 serialized
  rubric entries, 1,392 predictions, 1,392 judgments, 1,646 bundled images,
  and 24 externally packaged videos.
- Bundled images are checked for readable format, matching filename extension,
  and identity-bearing metadata.
- External videos and bundled assets are checked against
  `assets/asset_manifest.csv` and the published SHA-256 values.

## Claim boundaries

- The 60 examples are not claimed to be a random audit sample.
- No completed human-validity audit of the historical synthetic cases is
  claimed.
- Stored example outputs reproduce only the 60-case subset, not the full
  eight-model result table.
- The Kimi results are a separate supplementary evaluation.

## Asset packaging

Large videos are separated from the ordinary Git tree for hosting-size reasons.
The Git tree contains 1,646 images. The 24 videos are provided through the
separately checksummed archive described in `assets/EXTERNAL_ASSETS.md`.

The current machine-readable state is recorded in
`REPOSITORY_VALIDATION.json`. After any artifact change, maintainers should
rerun the validator and regenerate `SHA256SUMS` before publication.

## Anonymous distribution

The artifact is distributed through an anonymizing repository service for
double-blind review. Public case IDs, expert codes, file metadata, and Git
commit identity follow the policy in `ANONYMITY.md`.

## Evaluation evidence update

- Added 8,640 anonymized eight-model task-score rows and offline reconciliation.
- Located original overall rates as first-turn rates over 344 tasks, and
  supplied all-task aggregates over 1,080 tasks.
- Replaced inferred main-table Wilson counts with observed full-task counts.
- Documented ten missing scores and one score/status conflict explicitly.
- Added the bounded author-reported 100-response judge-review summary.
- Added a representative visually checked evidence-to-answer walkthrough.
- No new human labels, independent human baseline, or model rerun is claimed.
