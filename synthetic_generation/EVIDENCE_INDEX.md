# Method-to-Evidence Index

| Method claim | Template / prompt | Machine object | Executable evidence | Required release artifact |
|---|---|---|---|---|
| Source samples are traceable | `SOURCE_FILTER_SPEC.md`, `templates/source_card.json` | `SourceCard` | `filter_sources.py`, asset/hash checks | candidate JSONL, source card, asset hashes |
| GPT-5.5 API is used | all stage prompts | `RunMetadata` | `generate_case.py` | internal response IDs, model identifier, config hash |
| Self-Construct is grounded | `prompts/01_self_construct.md` | `ConstructedCase` | coverage and DAG validators | evidence graph, rule program, hidden gold |
| Self-Evolve is controlled | `prompts/02_self_evolve.md` | `EvolvedCase` | mutation invariant checks | mutation log and recomputed gold |
| Self-Improve repairs defects | `prompts/03_self_improve.md` | `ImprovedCase` | defect and repair checks | repair log with before/after hashes |
| The case needs images and local rules | `prompts/04_ablation_audit.md` | `AblationReport` | model audit plus deterministic completeness checks | exactly four decisions per task: full/no-visual/no-rules/no-prior-state |
| Rubrics are complete and non-leaking | `prompts/05_release_critic.md` | `QualityReport` | rubric traceability validator | rubric-to-gold mapping |
| Acceptance of newly generated cases is independent | human review template | `HumanReview` | `validate_release.py` | two reviews and adjudication |
| All 189 share the reported generation model and construction method | `MANIFEST_POLICY.md` | `manifests/historical_189_public_manifest.csv` | public manifest count and ID checks | method-level manifest with public case IDs, taxonomy, counts, model, and construction method |

The final row records the author-confirmed model and construction method for
the paper's synthetic subset without exposing private contributor or legacy
directory mappings.

The files in this package provide the versioned, executable evidence used for
release.
