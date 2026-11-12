# Reproduction and Validation Tools

The primary entry point is:

```bash
python tools/reproduce.py
```

It reaggregates the released 60-example results, recomputes the uncertainty and
open-weight evidence, and runs repository checks without calling an API or
rewriting tracked files. See `../REPRODUCE.md` for the ordered workflow and
individual subcommands.

Run the complete technical and anonymity gate from the repository root:

```bash
python tools/reproduce.py validate \
  --video-archive ../MCL-Bench_release_assets/MCL-Bench_video_assets.tar
```

The command validates the 60 example cases, the 1,392 prediction/judgment
pairs, JSON fields, local paths, credentials, contributor-code leakage, image
metadata, Git file sizes, asset hashes, and all 24 externally packaged videos.
By default it is read-only. Release maintainers can append
`--write-validation` after all other changes are final to write:

- `REPOSITORY_VALIDATION.json`, containing the machine-readable gate result;
- `SHA256SUMS`, covering files in the ordinary repository tree.

A technical `PASS` covers repository integrity and anonymity checks. The asset
manifest retains source-status fields for traceability, but those fields are
not used as a technical publication gate.
