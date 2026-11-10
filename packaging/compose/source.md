# Compose package assets

This directory contains the Linux release-archive assets that install the fixed
Compose upgrade-helper boundary. It is a packaging adapter, not a Core runtime
component; it must not introduce Docker socket mounts or arbitrary operator
arguments.

| Path | Responsibility | Boundary / side effects |
| --- | --- | --- |
| `docker-compose.yml` | Runs the official Linux image as a non-root, read-only service with loopback-only Admin bind, bounded `/tmp`, and a named data volume. | New runtime manifests select a local tag whose Docker image config ID is checked by the helper; the root-owned manifest also retains the OCI `tag@sha256:digest` provenance. Legacy manifests keep their digest reference fallback. Local builds require a separate explicit override/profile. |
| `compose-upgrade-helper` | Validates the fixed Compose project/file prefix and typed upgrade command allowlist. | Before Docker load, matches the requested OCI ref to a root-owned release manifest and verifies the image-save archive's config-file SHA-256 against its amd64 config ID; after load, checks version/revision labels and the daemon image ID again. Stages both local tag/config ID and immutable OCI provenance, checks the active image ID before start/rollback/recovery, healthchecks rollback, and rejects unsupported commands/arbitrary Docker arguments. OCI manifest digest and Docker image config ID are distinct values. |
| `install.sh` | Installs the packaged Compose files and helper into root-owned fixed host paths. | Requires the root-owned release manifest and exact pulled OCI reference, compares the platform config ID and labels, creates the admitted local tag, preserves an existing canonical config, and atomically initializes both image identities. |
| `prepare-upgrade.sh` | Updates only fixed Compose control-plane assets from a verified target archive. | Requires root and replaces the fixed Compose files and helper; the Compose template keeps the prior tag/digest manifest readable during the backup phase, and this script does not touch runtime image state, canonical primary config, or persistent data. |
| `docker-compose.upgrade.yml` | Fixed upgrade-only Compose override. | Runs only the short-lived backup/verify invocation as UID 0 with `DAC_OVERRIDE` and `FOWNER`, so it can read the root-owned owner-only passphrase and re-assert private mode on the edge-owned exclusive data lock; normal serving remains non-root and never uses this override. |
