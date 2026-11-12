# External Asset Attachment

The release archive contains 24 video files. Video files are not stored as
ordinary Git blobs. Their original
repository-relative paths are preserved in a separate archive so they can be
restored with:

```bash
tar -xf MCL-Bench_video_assets.tar -C /path/to/MCL-Bench
```

After extraction:

```bash
python evaluation/scripts/validate_examples.py --examples examples
```

The archive SHA-256 is stored next to the archive outside the Git repository.
The manifest keeps redistribution-status metadata separate from the technical
integrity checks documented here.
