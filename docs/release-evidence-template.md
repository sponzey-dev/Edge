# Product Release Evidence Template

Use this template for a candidate built from the current source tree. A release is
not complete until every required field has concrete evidence. Historical Phase
evidence and removed helper names are archive-only: they document prior work but
are not current commands or approval substitutes.

Certificate scope is manual certificates and private PKI only. External ACME or
Let's Encrypt issuance and renewal are deferred; do not collect, initialize, or
claim certificate-automation evidence unless the user explicitly reopens that
scope.

## Release Identity

```text
release_id:
semver_tag:
commit_sha:
source_tree_sha256:
utc_started_at:
utc_completed_at:
operator:
reviewer:
```

## Published Artifacts

```text
github_release_url:
linux_amd64_archive_sha256:
linux_arm64_archive_sha256_unverified_optional:
sha256sums_sha256:
spdx_sbom_sha256:
ghcr_image_repository:
ghcr_manifest_digest:
oci_revision_label:
```

The tag, commit, archive checksums, SBOM, OCI label, and immutable image digest
must identify the same release. A mutable tag without its matching digest is not
sufficient.

## Historical Promotion Evidence JSON

The SemVer workflow creates a prerelease candidate only. The following schema v1
is retained for historical inspection. It cannot authorize promotion: it records
status strings without binding the underlying evidence. A replacement contract
is under development; do not submit this example as promotion evidence. Its former
index filename was `promotion.json`.

```json
{
  "schema_version": 1,
  "tag": "vMAJOR.MINOR.PATCH",
  "commit": "40-lowercase-hex-commit",
  "image": "ghcr.io/sponzey-lab/sponzey-edge:vMAJOR.MINOR.PATCH@sha256:64-lowercase-hex",
  "source_quality": "passed",
  "support_bundle": "passed",
  "manual_or_private_pki_only": true,
  "certificate_automation_deferred": true,
  "matrix": [
    { "deployment": "compose", "platform": "linux-amd64", "status": "passed" },
    { "deployment": "systemd", "platform": "linux-amd64", "status": "passed" }
  ]
}
```

The validator's explicit `--inspect-legacy` option can inspect this historical
shape and returns `promotion_eligible: false`. The promotion workflow does not
use that option and rejects schema v1. The replacement must bind the immutable
candidate to independently checked source, operational and performance evidence.

## Schema v2 Evidence and Inspection

Schema v2 is inspection-only: source and operational result observations are
not yet independently validated against substantive original outputs. `--inspect-v2`
returns `promotion_eligible: false`; promotion remains fail-closed even for committed records.
The index is a secret-free `promotion.json` with `schema_version: 2`, the
candidate `tag`, `commit`, digest-pinned `image`, the two certificate-scope
booleans, and a `records` object containing exactly:

- `source_quality`, `support_bundle`, `compose`, and `systemd`: each references
  a bounded JSON receipt by relative `path` and lowercase `sha256`.
- `c8_reference`, `c8_candidate`, and `soak`: each maps the exact original
  performance filenames to their relative `path` and lowercase `sha256`.
  Baselines require `metadata.json`, `state.json`, `summary.json`,
  `edge-resource-samples.json`, and `baseline-1.json` through `baseline-3.json`;
  soak requires the first four and `soak-1.json`.

Each receipt has `schema_version: 1`, its `kind`, the exact candidate identity,
the complete named `checks`, and a digest-bound `trace`. A trace contains the
same identity and one observation per check; each observation binds a safe,
secret-free original JSON output by path and digest. For source quality, each
output records `command` as an exact argument array, `source_commit`, integer
`exit_code`, and string `stdout` and `stderr`; the validator checks the fixed
commands and a successful exit against the candidate commit. The expected check
names and commands are defined in the validator. Do not include cookies,
credentials, request bodies, private keys, or raw sensitive logs.
For source quality, `tools/release/collect_source_quality.py` can create a new
evidence root and its receipt, trace and original command outputs. Supply
`--workspace`, `--output`, `--tag`, `--commit` and the digest-pinned `--image`.
It requires a clean checkout of that commit before and after the fixed commands;
failed commands, oversized output or detected sensitive content prevent
publication. Review all output before committing: automatic detection is not
exhaustive. Add the other evidence under the same root; the printed receipt
reference belongs in `records.source_quality`. Running this collector runs the
full source-quality commands, including `cargo audit`, and is not itself a
candidate release or clean-host test.
Support authentication observations record only HTTP status codes: unauthenticated
401 and authenticated 200, and a separate missing-CSRF 403 with authenticated
200. The `allowlist_and_bounds` observation references the original uncompressed
support tar and its API response by relative path and SHA-256. The inspector
checks the receipt digest, member allowlist and types, content byte bound,
manifest and secret indicators without extracting the tar. `log_observation`
records Unix collection and source modification times plus the archived product
log SHA-256; their difference must be 0–86400 seconds. Those timestamps remain
reported observations and need a trustworthy collection procedure. Unsafe-path
rejection is checked against a separate archive and response showing the symlinked
fixture was omitted; the source type remains a reported observation. Deployment
evidence also needs further original verification before
promotion can be enabled. Do not commit an archive
until its owner has reviewed it for secrets; automatic detection is not exhaustive.

Compose/systemd inspection compares structured observations: forwarding must
return HTTP 200 with the SHA-256 of `sponzey-release-fixture\n`; the host-side
Admin listener must use a loopback IP and refuse a remote probe. Preservation
records hashes of selected config, certificate, data and the *original audit
prefix* before upgrade, after upgrade and after rollback, so appended audit
events do not appear as loss. Install/upgrade/rollback records also cross-check
their candidate and predecessor observations; restart, SIGTERM and cleanup have
separate observations. To cross-check the systemd executable against local
candidate release assets, pass `--release-artifacts <directory>` to the v2
inspector. It snapshots and validates the manifest, checksums and SBOMs, then
compares the executable inside the amd64 archive with the installation and
upgrade observations. The result reports `archive_binding_verified`; it remains
false when that option is omitted. This offline check does not establish that
the directory was obtained from GitHub. The promotion workflow downloads the
candidate's listed assets directly from its GitHub prerelease into a temporary
directory before validation. When every v2 check and archive binding succeeds,
inspection reports `evidence_contract_valid: true` and `promotion_eligible: false`;
without archive binding the contract-valid flag is false. These flags describe
the G01 contract for supplied records, not proof that observations were actually
collected or that G05–G07 are complete. Product promotion remains disabled until G07.
These records describe observed results; hashes and recorded command outputs
establish consistency, not cryptographic proof that an untrusted operator ran them.

Inspection checks every file's digest and safe path, rejects missing or extra
records, recomputes summaries from original k6 results and samples, applies the
existing C8 evaluator, and checks the approved reference source, host/config
identity, and the 30-minute soak. The Node.js verifier is required and failure
to run it is a rejection. `--require-tracked` also requires the index and all
referenced files to be committed and unchanged. The promotion workflow uses that
option. Historical source-build metadata cannot prove a published image was
measured. Candidate baseline and soak must contain runner-recorded digest,
revision/version labels and matching inspected/container image IDs; use the
explicit candidate mode documented in [testing.md](testing.md#release-performance-test-environment).
The approved historical reference predates config hashes: only its exact approved
commit and tree use the hash of the configuration at that commit.

## Source-Level Gate

Record the complete output and exit code for each command executed against the
release identity:

```bash
cargo fmt --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace -- --test-threads=1
```

```text
cargo_fmt_check_exit:
cargo_clippy_exit:
cargo_test_exit:
architecture_api_contract_exit:
documentation_contract_exit:
```

The reusable `edge-test` container may provide Linux source-level evidence, but
it does not replace production-image or clean-host evidence.

## Compose Clean-Host Evidence

Use only a verified published image tag and its immutable digest. Do not replace
this with a local build, dummy image, or unverified tag.

Before installation, verify that the image's
`org.opencontainers.image.version` label exactly equals the release tag,
including its `v` prefix, and that `org.opencontainers.image.revision` equals
the candidate commit. The release workflow labels the image with the exact Git
tag and commit; record these values in the secret-free candidate observation.

```text
host_os_and_architecture:
docker_version:
compose_version:
image_tag:
image_digest:
install_command_transcript_ref:
readiness_probe_result:
proxy_smoke_result:
admin_loopback_result:
upgrade_result:
forced_rollback_result:
data_preservation_result:
cleanup_result:
secret_exclusion_review:
```

Record each command, its result, the input configuration digest, and the final
cleanup result. The Admin API must remain loopback-only. This candidate supports
Linux amd64 only; a published arm64 artifact is unverified and not a substitute.

## Systemd Clean-Host Evidence

```text
host_os_and_architecture:
systemd_version:
archive_sha256:
install_start_probe_result:
sigterm_restart_result:
uninstall_result:
upgrade_result:
forced_rollback_result:
data_preservation_result:
cleanup_result:
secret_exclusion_review:
```

The host must run systemd as PID 1. Container simulation is not systemd
evidence.

## Support Bundle Verification

```text
support_bundle_api_or_ui_result:
archive_id:
archive_digest:
allowlist_bounds_result:
secret_scan_result:
path_and_symlink_rejection_result:
```

The receipt must not expose archive paths, private keys, secrets, request or
response bodies, authorization material, cookies, or full queries.

## C8 Performance Evidence

```text
reference_baseline_artifact:
candidate_baseline_artifact:
reference_commit:
candidate_commit:
matching_host_identity_result:
c8_compare_command:
c8_compare_result:
median_rps_ratio:
median_p95_ratio:
median_p99_ratio:
median_error_rate_delta:
```

The comparator rejects incomplete, pre-host-identity, or mismatched-host artifacts.
Its accepted limits are no more than 5% median RPS loss, no more than 10% median
p95/p99 increase, and no median error-rate increase.

## Known Limits

```text
manual_or_private_pki_only: true
certificate_automation_deferred: true
official_clean_host_evidence_pending:
unsupported_platforms: macOS, Windows, Linux arm64
```

## G05 Acceptance Index (A09)

The G05 acceptance index is a separate, secret-free integrity and candidate
consistency record for A01 through A08. It is not `promotion.json`, does not
replace the release evidence above, and does not authorize G07 product
promotion. Do not combine observations from different tags, commits, OCI index
digests, or Linux amd64 image config digests.

The index uses schema version 1 and contains exactly `schema_version`, `goal`,
`candidate`, and `criteria`. The candidate contains the exact `tag`, full
lowercase `commit`, `oci_index_digest`, and `linux_amd64_config_digest`. It
contains each of `G05-A01` through `G05-A08` exactly once. Each criterion is
`PASS` and references exactly one relative observation JSON path and SHA-256.
Each observation contains exactly `schema_version`, `criterion_id`, the same
candidate, non-empty `expected` and `actual` observations, and `decision: PASS`.
Keep the source command transcript and original operational evidence under the
same evidence root, with their own documented references where applicable.

Run the structural and digest inspection with:

```bash
python3 tools/release/validate_g05_acceptance_index.py \
  --evidence-root <evidence-directory> \
  --index g05-acceptance-index.json
```

The inspector rejects missing or duplicate criteria, candidate mismatches,
incorrect digests, symlinks and paths outside the evidence root, duplicate JSON
keys, unexpected fields, and oversized records. A successful result verifies
index structure, file integrity, and recorded identity only. It does not
independently interpret the referenced operations or prove how observations
were collected. Review each `expected`/`actual` pair against its original
evidence before recording `PASS`; omit secrets, private keys, credentials,
cookies, and raw sensitive logs. A complete A01–A08 index is still only the G05
acceptance input and cannot enable product promotion before G07.

## Review Sign-Off

```text
source_gate_verified_by:
artifact_identity_verified_by:
compose_evidence_verified_by:
systemd_evidence_verified_by:
security_reviewed_by:
release_approved_by:
approval_utc:
```

## Rejection Criteria

Reject the candidate if any source-level gate fails, any artifact identity is
missing or inconsistent, an image digest is mutable or absent, either required
clean-host path lacks evidence, Admin is publicly reachable, an upgrade/rollback
cannot preserve required data, or any evidence includes secret or private key
material. Historical archive-only evidence cannot waive these requirements.
