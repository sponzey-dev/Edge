# n8n Gateway Smoke

Sponzey Edge can now run as a minimal HTTP reverse proxy in front of an n8n Docker container.

Current supported scope:

- HTTP listener
- config snapshot route selection
- deterministic round-robin across eligible `http://` upstreams
- request forwarding
- response forwarding
- request body forwarding
- WebSocket upgrade tunnel
- `X-Forwarded-For`
- `X-Forwarded-Proto`
- `X-Forwarded-Host`
- hop-by-hop header removal
- MVP config file parsing for `examples/minimal.toml`-style configuration

Current limitations:

- HTTPS termination has a local self-signed smoke gate, but the n8n compose smoke is still HTTP-only.
- WebSocket tunnel is implemented at a basic TCP tunnel level after `101 Switching Protocols`.
- The Admin API provides protected configuration and operational management; its
  current contract is in `docs/admin-api.md`. Certificate operation uses manual
  certificates/private PKI. External Let's Encrypt/ACME automation remains
  deferred; `docs/acme-staging.md` is an archival note, not a runbook.
- The n8n smoke compose uses explicit `SPONZEY_DEV_LISTEN` and `SPONZEY_DEV_UPSTREAM_URL` bootstrap overrides so the upstream can target Docker service DNS (`n8n:5678`). These are development smoke helpers, not the intended runtime config lifecycle.
- The packaged n8n example uses one upstream. Multi-upstream round-robin and
  active-health exclusion and conditional safe retry are implemented; this
  single-upstream example does not demonstrate retry across multiple targets.

## Run

From the repository root:

```bash
docker compose -f examples/n8n-gateway.compose.yml up --build
```

Open:

```text
http://localhost:8080
```

The traffic path is:

```text
browser
  -> Sponzey Edge :8080
  -> n8n :5678
```

## Runtime Environment

The Edge container uses bootstrap-only environment values. `SPONZEY_CONFIG_FILE` points to the packaged sample config; for this smoke, `SPONZEY_DEV_LISTEN` and `SPONZEY_DEV_UPSTREAM_URL` explicitly override the listener/upstream pair:

```text
SPONZEY_CONFIG_FILE=/etc/sponzey-edge/current.toml
SPONZEY_DEV_LISTEN=0.0.0.0:8080
SPONZEY_DEV_UPSTREAM_URL=http://n8n:5678
SPONZEY_ACME_CLIENT=fake
```

n8n is configured as a proxied service:

```text
N8N_HOST=localhost
N8N_PORT=5678
N8N_PROTOCOL=http
WEBHOOK_URL=http://localhost:8080/
N8N_PROXY_HOPS=1
```

Use HTTPS values only after installing a matching certificate and configuring an
HTTPS listener. The n8n compose smoke itself intentionally remains HTTP-only.

For the MVP release path, listener/upstream changes must go through config
validation, revision apply, and rollback rather than these smoke overrides.
