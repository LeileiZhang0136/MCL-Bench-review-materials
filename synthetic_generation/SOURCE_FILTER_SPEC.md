# Deterministic Source Filter

The release source filter scans only the two allowlisted directories:
`slideVQA/` and `mmlongbench-doc/`.

Each leaf directory containing images is one candidate sample. Files are sorted
by a natural filename order. Supported formats are JPEG, PNG, and WebP.

## Formal candidate

A sample enters `formal_candidates.jsonl` when:

- it has at least four readable images;
- at least 90% of its image files are readable;
- every readable image is at least 640 pixels on both dimensions;
- the source dataset and sample-relative directory are recorded.

## Blueprint candidate

A readable sample that has at least three images but misses one formal threshold
enters `blueprint_candidates.jsonl`. It may be inspected manually but is not
used by the default 189-case selection plan.

## Rejected candidate

A sample with fewer than three readable images enters
`rejected_candidates.jsonl`.

These checks establish file quality and minimum multi-image structure. They do
not by themselves establish benchmark validity or multimodal necessity; those
properties are checked by the construction and release gates.

