# Asset Handling

The example cases refer to case-local images and videos. Images and other
ordinary-size files currently present under `examples/` are part of the
anonymized repository. Videos are separated into an external release archive
so that the Git repository does not exceed GitHub's regular-file limits.

`asset_manifest.csv` records, for every case-local asset:

- repository-relative path;
- byte size and SHA-256;
- whether it is bundled in the ordinary Git tree;
- planned hosting route; and
- redistribution-review status.

Technical bundling does not itself grant redistribution permission. Every row
is initially marked `pending_case_level_review`. A final public release must
either replace that value with a documented permission decision or exclude the
asset while preserving an explicit exception record.

Allowed final values for `redistribution_status` are:

- `redistributable_verified`: the source terms and the specific use permit
  redistribution;
- `reference_only`: keep the manifest entry but do not publish the file;
- `permission_required`: publication requires permission not yet obtained;
- `excluded_no_permission`: the file has been removed from the public package;
- `pending_case_level_review`: no final decision has been made.

Do not convert a row to `redistributable_verified` merely because its source is
publicly accessible. Record the applicable dataset, document, or media license
outside the anonymous repository before changing the status.
