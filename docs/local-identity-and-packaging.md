# Local identity and packaging

The default setup remains loopback-only, synthetic, and usable without a paid API. Native Codex inference uses the owner's existing sign-in. The distributable service image contains no Codex executable or authentication cache; its local demo runs the explicit rule baseline.

## Identity

After the normal database migration/setup:

```bash
uv run python tools/identity.py init
uv run python tools/identity.py up
uv run python tools/stack.py down
uv run python tools/stack.py up --provider baseline
```

`init` writes owner-only local credentials/configuration and selects OIDC in `.env`. Read `.local/identity/credentials.json` locally to sign in as alex, sam, operator or taylor. Taylor is in a different synthetic tenant. Never commit or paste these credentials. Keycloak listens only on 127.0.0.1:8850 and uses its own database role/database. This is a development-mode identity provider, not a production identity deployment. Application logout revokes the application session; Keycloak's SSO session may still exist.

For MCP, `commerce-tools` is a public Code + PKCE client with the fixed loopback callback http://127.0.0.1:8859/callback. Access tokens need the http://127.0.0.1:8510/mcp audience and commerce:read scope. Browser session cookies are not accepted as MCP authorization. Synthetic demo mode supports an explicit opaque bearer credential for local tests only.

## Runtime database permissions

```bash
uv run python tools/stack.py down
uv run python tools/database.py configure
uv run python tools/database.py check
uv run python tools/stack.py up --provider baseline
```

Provisioning preserves the original admin URLs in `.local/database/admin.env`, creates separate application/source runtime roles and grants SELECT/INSERT/UPDATE on their required tables. Runtime startup no longer creates schemas or runs checkpoint/source migrations. For subsequent schema changes use `uv run python tools/database.py migrate`; it runs migrations as the admin and reapplies the runtime grants. Direct Alembic against runtime credentials intentionally lacks migration privileges.

## Packaged local demo

```bash
uv run python tools/package_local.py
docker compose -p agentic-commerce --profile packaged build packaged-api
docker compose -p agentic-commerce --profile packaged run --rm --no-deps packaged-seed
docker compose -p agentic-commerce --profile packaged up -d packaged-api
```

Open http://127.0.0.1:8520. API and source run as UID 10001 with read-only root filesystems, dropped capabilities, no-new-privileges and bounded memory. The source has no host port. Private configuration gives each service only its required database credential. The exact protocol key is copied into a private state volume by an offline initialization container; it is not baked into the image. A changed key fails initialization rather than silently invalidating stored mandates. The owner-only signing key and protocol-key file must be retained with configuration backups; a database dump alone cannot recover encrypted authority artifacts.

This packaged demo shares the existing synthetic commerce/source databases, so purchases consume the same stock. Stop it with `docker compose -p agentic-commerce --profile packaged stop packaged-api packaged-source`; do not remove data volumes. Graph workers claim only sessions matching their configured model provider. Prefer one active user-facing stack for routine demonstrations.

The tested older Docker Desktop ARM guest terminated when loading the cryptography wheel's OpenSSL code (exit 132). For this host profile, the preparation tool sets `OPENSSL_armcap=0`; imports and signed checkout then passed. This is a CPU-acceleration compatibility setting, not a change of signing algorithm. It is not baked into the generic image or a production performance claim. [OpenSSL's documented override](https://docs.openssl.org/master/man3/OPENSSL_armcap/), [cryptography wheel packaging](https://cryptography.io/en/50.0.2/installation/).

## Monitoring and evidence

A separate COMMERCE_METRICS_TOKEN authorizes GET /internal/metrics and grants no application/operator access. It exports aggregate state counts, oldest unresolved execution/queue ages and durable source/policy event counts, without customer or purchase identifiers as labels. The alert and dashboard definitions in infra/monitoring are provisioning artifacts. A running Prometheus/Grafana stack and alert-delivery exercise are still pending; existence of JSON/YAML is not a verified monitoring deployment.

Record real runs with `tools/evaluate.py`; the original failed model batch remains next to the corrected regression batch under results/evaluations. Three corrected model cases are a smoke-sized regression sample, not 100-case model accuracy. The 100-case result belongs to the rule baseline.

Run `uv run python tools/browser_check.py` for browser acceptance in disposable databases. The earlier OIDC browser run was exercised separately against the local Keycloak profile; the disposable suite uses synthetic demo login.
