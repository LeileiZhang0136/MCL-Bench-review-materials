# Fixed Candidate Data Sources

## SlideVQA

- Upstream repository: <https://github.com/nttmdlab-nlp/SlideVQA>
- Reference implementation revision:
  `0d4168a935d60b0b218097205a02fb1133c8bead` (observed 2026-07-29).
- Release role: candidate presentation-slide images and paired textual
  annotations/questions.
- Required local record: dataset version or commit, split, sample identifier,
  selected image paths, source text fields, upstream URL, and access/license
  note.

## MMLongBench-Doc

- Upstream repository: <https://github.com/mayubo2333/MMLongBench-Doc>
- Reference implementation revision:
  `d73f0dc0be7e0a2ff6a403d5fe65fcd96461f384` (observed 2026-07-29).
- Release role: candidate long-document pages and paired question/evidence
  fields.
- Required local record: dataset version or commit, split, document/sample
  identifier, selected pages, rendered page hashes, source text fields,
  upstream URL, and access/license note.

These repository revisions pin source retrieval for the executable reference
implementation. Selected local assets are identified by their relative paths
and SHA-256 hashes, and the filtered candidate manifest is itself hashed.

## Redistribution rule

An upstream dataset being publicly accessible does not automatically establish
permission to redistribute every underlying document or image. The release
therefore records `license_or_access` and `redistribution_status` per source
sample. Restricted assets may be represented by retrieval instructions and
cryptographic hashes rather than copied into the repository.
