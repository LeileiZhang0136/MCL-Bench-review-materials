# Double-Blind Anonymization Policy

This repository has been anonymized and is distributed in accordance with
double-blind review requirements.

Excluded fields and files include:

- author or contributor names, initials, affiliations, and email addresses;
- private mappings between legacy source directories and public case IDs;
- local filesystem paths and machine usernames;
- API keys, response IDs, token logs, and provider account metadata;
- non-anonymized raw provider files, request logs, and legacy result
  directories;
- unfinished or AI-generated pre-audit sheets.

Public expert-contributor labels use anonymous codes such as `E01`. Synthetic
cases are labeled only as `synthetic`. These labels support source-track
analysis without revealing individual contributors.

The supplementary open-weight evaluation includes only binary task scores
exported under anonymous `MCL-xxxx/Tn` identifiers. The private crosswalk used
to create those identifiers remains outside this repository. The public score
table contains no legacy task IDs, contributor codes, original paths, model
outputs, or judge rationales.

The released 60-example evaluation contains anonymized model-output text and
GPT-5.2 judge rationales under public `MCL-xxxx/Tn` identifiers. Repeated
source messages, private crosswalks, provider request identifiers, account
metadata, legacy case names, and server paths were removed during export.

The public taxonomy is defined by `case_metadata.json`, directory names, and
the public manifest. Legacy placeholder task-metadata fields were removed
because they did not represent the benchmark taxonomy.

Image EXIF, XMP, author, editing-software, and document-identifier metadata are
removed from the anonymous copy. Images whose visible orientation depended on
EXIF are losslessly oriented before that metadata is removed. Filename
extensions are normalized to match decoded image formats, and case JSON
references are updated accordingly.

The public Git history uses the identity `Anonymous Authors
<anonymous@invalid.example>`. The artifact is distributed through an
anonymizing repository service so that the public view does not expose the
source account or author profile.

The full-benchmark reconciliation additionally releases anonymous task scores,
source-track and taxonomy labels, rubric-entry counts, and requirement-status
strings. It excludes original task names, contributor mappings, raw prompts
and provider records. The private export crosswalk is not distributed.
