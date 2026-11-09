# Sponzey Edge Proxy

[한국어](README.ko.md)

Sponzey Edge Proxy is a self-hosted reverse proxy and edge gateway for operators
who need to publish web services safely without making every routing change a
manual proxy-configuration exercise. A Rust/mio data plane handles traffic; an
optional Admin Web UI provides a client for the versioned Admin API.

## Purpose And Users

The project serves small web-service operators, Docker Compose teams, self-hosting
users, and operators managing several domains and upstream services. They need to
change routing, understand failures, and recover configuration and service data
without disrupting working traffic or exposing administrative access and secrets.

The long-term goal is a predictable edge gateway whose configuration, visibility,
and recovery remain understandable as its capabilities grow. NGINX-style web-service
operation, HAProxy-style availability, Traefik-style discovery, and Caddy-style ease
of administration inform that direction; they are not a promise of feature parity.

## Product Goals And Success Criteria

- Operators can publish and maintain services through the UI or the same validated
  API, while the proxy continues to work without the UI.
- Invalid or rejected configuration preserves the working runtime; revisions and
  rollback make changes traceable and recoverable.
- Bounded connections, buffers, timeouts, and backpressure keep resource use and
  failure behavior predictable under the tested workloads.
- Health, logs, metrics, audit, and diagnostic bundles let operators locate failures
  without exposing credentials or traffic payloads.
- Installation, upgrade, rollback, and encrypted recovery are reproducible against
  one identified release artifact, with functional and performance evidence.

Correctness → safety → operability → simplicity → performance → feature count.
Rust memory safety and historical benchmarks do not replace runtime verification.

The immediate focus is a reliable **single-node product**, beyond the original MVP.
The product candidate targets Linux `amd64` through Docker Compose and systemd.
Build artifacts for other architectures or operating systems do not establish
operational support. All active product documents and the project plan use `main`
as the implementation baseline, confirmed on 2026-11-09. See
[current state](docs/current-state.md) for source identities, evidence limits,
and the tag/package-version mismatch.

## Core Operator Flow

1. Install a pinned binary/image and complete the protected Admin setup, or use
   the headless configuration/API path.
2. Define a domain/path and upstream, adding manual certificates and managed
   private trust when HTTPS or client-certificate authentication is required.
3. Validate and review the change, then apply it through the acknowledged config
   lifecycle. Failed activation retains the previous state.
4. Inspect health, resource status, logs, metrics, and audit; collect a bounded
   support bundle when diagnosis is needed.
5. Roll back a configuration or use the offline backup/upgrade/recovery workflow
   to restore operation and verify forwarding and Admin access.

## Implemented Capabilities

The following capabilities exist in the source. Their presence is distinct from
release qualification; the [current-state record](docs/current-state.md) separates
implementation, historical checkpoints, and remaining productization evidence.

### Reverse Proxy And Routing

- HTTP/1.1 and HTTPS reverse proxy on a unified mio runtime
- Host, exact path, and path-prefix routing
- HTTP-to-HTTPS redirect
- `X-Forwarded-*` and hop-by-hop header handling
- chunked responses, request/response timeouts, slow-client handling, and backpressure
- WebSocket upgrade and bidirectional tunnel

### Upstreams And Availability

- single or multiple upstreams per service
- deterministic round-robin selection
- active HTTP/HTTPS health checks and passive transport-failure ejection
- administrative drain with generation fencing
- one safe retry for eligible GET/HEAD requests
- explicit `502`, `503`, `504`, and timeout behavior

### TLS And Private Trust

- rustls TLS termination and SNI certificate selection
- manual/file-backed certificates and certificate hot install for new connections
- self-signed and Root/Intermediate private-PKI validation
- strict private upstream HTTPS with managed Root trust, verified SNI, and explicit HTTP Host
- required inbound mTLS with managed client Root trust
- generation-atomic config, TLS, and health activation with rollback compensation

Certificate operation currently uses manual/file-backed certificates and private
PKI. Let's Encrypt, ACME, HTTP-01/DNS-01, and automatic renewal remain on hold
until the user explicitly reopens that scope. Existing adapter/test code does not
make external certificate automation a supported operator workflow.

### Support Bundle

Authenticated Admin users can create a bounded diagnostic bundle from the Admin UI or
`POST /api/v1/support-bundles` with CSRF protection. The request accepts no path or
artifact selection. It produces a fixed-path private tar archive and exposes only a
secret-free receipt (archive ID, digest, artifact summary, omissions, and size).
Private keys, secrets, headers, cookies, bodies, queries, and filesystem paths are not
included in the API/UI result. This is not a backup replacement.

### Configuration And Administration

- declarative TOML configuration
- parse, normalize, validate, diff, plan, apply, revision commit, audit flow
- safe apply and rollback that preserve the previous runtime state on failure
- optional same-origin Admin Web UI
- authenticated Admin API with setup, login/logout, CSRF protection, Proxy Host CRUD,
  configuration lifecycle, certificate/trust management, health, metrics, logs, and audit search
- headless operation without the Admin Web UI

### Operations And Recovery

- Product, Field Debug, and Development log modes
- process-wide connection and in-flight payload admission with explicit pressure/cleanup accounting
- optional loopback-only Prometheus metrics and authenticated Admin metric summary
- bounded, restart-safe, file-backed audit ledger with authenticated Admin search
- encrypted offline backup, authenticated verification, fresh restore, replace, rollback,
  and crash recovery
- backup schema v1/v2 compatibility and schema v3 trust/audit preservation
- operational liveness/readiness probes and bounded SIGTERM drain
- Docker Compose and systemd packaging with journaled offline upgrade/recovery helpers

### Scope Boundaries And Future Direction

Current productization excludes HTTP/2, HTTP/3, gRPC, TCP proxying, Kubernetes,
multi-node control, WAF, cache/static hosting, advanced balancing, and a plugin
marketplace. Service discovery, identity integration, richer protocols, and
multi-node management remain possible later extensions, not committed deliveries.
They must preserve the independent data plane and validated configuration boundary.

Optional/client-identity mTLS, outbound client-certificate mTLS, TLS passthrough,
remote telemetry/audit storage, and multi-user RBAC/OIDC are not current features.
Commercial editions, pricing, and a hosted control plane are not defined product
commitments. The existing code and documentation use the MIT license below.

## Service Form And Technology

The operator runs the proxy on their own host. The static Admin UI is optional
and uses `/api/v1`; separate UI/control-plane deployment is an architectural
direction, not a claim that a distributed management product already exists.

| Component | Current implementation and role |
| --- | --- |
| Proxy runtime | Rust 2021 and mio, explicit socket/TLS/timeout state machines |
| TLS | rustls in adapters; manual certificates and explicit private trust |
| Control plane | Framework-free Rust Admin API; HTML/CSS/JavaScript UI |
| Configuration and state | Typed TOML config, file-backed revisions, certificate/trust/secret stores |
| Recovery and audit | age encryption, tar archives, SHA-256 integrity and a file-backed audit ledger |
| Packaging | Binary, Docker/Compose, and Linux systemd helpers |
| Test tooling | Rust workspace/memory harness; Node.js upstream and separate k6 load generator |

The core hot path uses mio rather than Tokio. Async dependencies in an outer
adapter do not change that runtime contract. See [architecture](docs/architecture.md)
and [dependency boundaries](docs/dependencies.md).

## Installation

### Build From Source

Requirements:

- a Rust toolchain with Cargo
- macOS or Linux

Build the release binary:

```bash
cargo build --release -p edge-proxy
```

The binary is created at:

```text
target/release/edge-proxy
```

### Docker Compose

Requirements:

- Docker
- Docker Compose

Official releases run a published Linux image identified by both a SemVer tag and
its immutable manifest digest. From the extracted release package, install and
start it with:

```bash
sudo ./compose/install.sh \
  --image-tag vX.Y.Z \
  --image-digest RELEASE_MANIFEST_IMAGE_SHA256_WITHOUT_PREFIX
sudo docker compose --project-directory /etc/sponzey-edge/compose \
  --env-file /etc/sponzey-edge/compose/runtime.env \
  --file /etc/sponzey-edge/compose/docker-compose.yml up -d --wait
```

For local source development only, use the explicit override:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile local-build up --build
```

See [`docs/install.md`](docs/install.md) and [`docs/deployment.md`](docs/deployment.md) for
runtime paths, permissions, backup, supported-platform boundaries, and deployment details.

### Reusable Test Container

Start the isolated test container once and reuse its Cargo dependency and target caches:

```bash
docker compose -f docker-compose.test.yml up -d --build
docker compose -f docker-compose.test.yml exec edge-test \
  bash -c 'cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace -- --test-threads=1'
```

The test container exposes no host port and does not mount runtime data or secrets. See
[`docs/testing.md`](docs/testing.md) for focused tests, lifecycle commands, and safety boundaries.

### Reusable Nextcloud Integration

The same test Compose file also has a persistent `nextcloud-e2e` profile that
routes `nextcloud.test` (and the local browser hosts `localhost` and `127.0.0.1`)
through a loopback-only Edge listener. Initialize it once, then run the verification
without creating a new Compose stack:

```bash
docker compose --profile nextcloud-e2e -f docker-compose.test.yml build edge-nextcloud
docker compose --profile nextcloud-e2e -f docker-compose.test.yml up -d --wait
node tests/integration/nextcloud/verify.mjs
```

See [`docs/testing.md`](docs/testing.md#reusable-nextcloud-through-edge-integration)
for port override, persistence, and explicit reset instructions.

### Release Performance Test Environment

The long-lived Compose performance boundary is separate from `edge-test`: it builds the production
`edge-perf` image and sends k6 traffic through it to a deterministic Node.js upstream. Start with
the functional gate:

```bash
node tests/performance/bin/run.mjs smoke
```

The default local build is characterization. Candidate performance evidence requires an explicit
locally available digest-pinned published image; see the candidate commands in the testing guide.

Run a real profile only from a clean Git worktree; the runner rejects source changes before it
creates artifacts, prepares PKI, builds images, or changes Compose services. The runner recreates
only the performance services, generates ignored test PKI, and publishes raw
results under `artifacts/performance/<run-id>/`. It exposes only the read-only Node dashboard at
`127.0.0.1:3000`; Edge Admin has no host port and Docker socket access is never mounted into a
container. See [`docs/testing.md`](docs/testing.md#release-performance-test-environment) before
running the longer baseline, stress, or soak profiles.

## Usage

### 1. Prepare An Upstream

The sample configuration expects an HTTP service at:

```text
http://127.0.0.1:3000
```

### 2. Review The Sample Configuration

[`examples/minimal.toml`](examples/minimal.toml) listens on `0.0.0.0:8080`, matches the
`localhost` Host, and forwards requests to the upstream on port `3000`.

```toml
schema_version = 1

[admin]
bind = "127.0.0.1:9443"
enabled = true

[logging]
mode = "product"

[storage]
data_dir = ".sponzey"

[runtime]
max_connections = 1024
max_inflight_payload_bytes = 134217728
upstream_read_timeout_ms = 30000

[[listeners]]
name = "http"
bind = "0.0.0.0:8080"
protocol = "http"

[[services]]
name = "example"

[[services.upstreams]]
url = "http://127.0.0.1:3000"

[[routes]]
name = "example"
hosts = ["localhost"]
paths = ["/"]
service = "example"
```

### 3. Start The Proxy

Run from source:

```bash
SPONZEY_DATA_DIR=.sponzey \
SPONZEY_CONFIG_FILE=examples/minimal.toml \
SPONZEY_ADMIN_BIND=127.0.0.1:9443 \
SPONZEY_LOG_MODE=product \
cargo run -p edge-proxy
```

Or run the release binary:

```bash
SPONZEY_DATA_DIR=.sponzey \
SPONZEY_CONFIG_FILE=examples/minimal.toml \
SPONZEY_ADMIN_BIND=127.0.0.1:9443 \
SPONZEY_LOG_MODE=product \
target/release/edge-proxy
```

Environment variables are bootstrap-only. After startup, change runtime configuration through
the Admin Web UI or the validated Admin API config lifecycle.

### 4. Verify Proxy Routing

```bash
curl -i -H 'Host: localhost' http://127.0.0.1:8080/
```

### 5. Open The Admin Web UI

Open:

```text
http://127.0.0.1:9443/
```

On a fresh data directory, complete the initial Admin setup and log in. Use Proxy Hosts to
create or update domains, paths, upstreams, health checks, and HTTPS policy. The UI applies
changes through `/api/v1`; opening `apps/admin-web/index.html` directly does not operate the
proxy.

### 6. Apply Headless Configuration

The primary configuration file is an initial seed for an empty revision repository. After a
current revision exists, use the Admin API validate, diff, apply, and rollback endpoints rather
than editing the seed file or changing process environment variables.

Configuration fields and API examples are documented in:

- [`docs/config-schema.md`](docs/config-schema.md)
- [`docs/admin-curl.md`](docs/admin-curl.md)
- [`docs/admin-api.md`](docs/admin-api.md)
- [`docs/nginx-migration.md`](docs/nginx-migration.md)

## Documentation

Start with the [document map](.docs/README.md) and [project plan](.docs/plans/plan.md)
for goals, sequence, dependencies, and acceptance criteria.

| Need | Document |
| --- | --- |
| Product purpose, users, direction, and scope | This README; [한국어](README.ko.md) |
| Implementation, source baselines, evidence, and remaining qualification | [Current state](docs/current-state.md) |
| Engineering rules and design boundaries | [AGENTS.md](AGENTS.md), [architecture](docs/architecture.md), [ADRs](docs/adr/) |
| Configuration and control-plane contracts | [Config schema](docs/config-schema.md), [Admin API](docs/admin-api.md), [curl workflow](docs/admin-curl.md) |
| Installation and operations | [Install](docs/install.md), [deployment](docs/deployment.md), [backup/restore](docs/backup-restore.md), [troubleshooting](docs/troubleshooting.md) |
| Observability and security | [Observability](docs/observability.md), [threat model](docs/threat-model.md), [private PKI](docs/private-pki-testing.md) |
| Verification and release evidence | [Testing](docs/testing.md), [release gate](docs/release-gate.md), [evidence template](docs/release-evidence-template.md) |

Phase-specific design and completion records preserve historical decisions and
evidence. Their original baselines, script names, or proposed features do not
override current scope or establish qualification for a different source identity.

## License

The project source and accompanying documentation are licensed under [MIT](LICENSE).
Third-party dependencies retain their own licenses; see [dependencies](docs/dependencies.md).
