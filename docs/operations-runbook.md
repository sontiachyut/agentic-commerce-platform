# Operations runbook — local v0.1

## Supported environment

One owner-operated loopback application, one PostgreSQL instance, separate commerce/source databases and two worker threads. Python 3.12 and Node 22+ are the supported setup. The verified developer machine used macOS, Python 3.12.7 and Node 23.9.0; Linux CI is configured but must run before claiming cross-platform verification.

Do not expose ports through a tunnel or change the bind address for a customer demo. Persona login is synthetic, not enterprise authentication. No real card, health or customer data belongs in this environment.

## First boot

1. Install Python 3.12, uv, Node and Docker/Compose. Start Docker.
2. Run `uv sync --locked` and `uv run python tools/dev.py init` from the repository root. Init creates owner-only `.env` secrets without printing or overwriting them.
3. Run `docker compose -p agentic-commerce up -d postgres`. The pinned image initializes `commerce`, `commerce_sources`, `commerce_test` and `commerce_sources_test` on its first empty volume.
4. Run `uv run alembic upgrade head`. Commerce tables are migration-owned. The simulator initializes its separate schema; the graph saver initializes its checkpoint schema at API startup.
5. Run `npm ci --prefix web` then `npm run build --prefix web`.
6. Run `uv run python tools/stack.py up --provider baseline` for deterministic development, or `--provider codex` for signed-in local inference.
7. Open `http://127.0.0.1:8510`. The API reference is at `/docs`.

Local ports are 8510 (workspace/API), 8511 (synthetic source) and 55439 (PostgreSQL). Compose binds PostgreSQL to 127.0.0.1. API/source also bind loopback. Do not use the published synthetic Compose password in any nonlocal environment.

## Lifecycle and health

```bash
uv run python tools/stack.py status
uv run python tools/stack.py down
uv run python tools/stack.py up --provider codex
```

Run `docker compose -p agentic-commerce stop postgres` only after stopping application processes. Restart with `up -d postgres` and the stack command. No `down -v`, volume deletion or inventory reset is part of normal operations.

`/health/live` checks API liveness. `/health/ready` checks database reachability and reports the selected provider and checkout-worker thread. It does not verify Codex account allowance, source availability or end-to-end purchase health. Use the operator view and a finite synthetic smoke for those boundaries.

The stack tool records its own PIDs in `.local/stack.json` and verifies module and repository working directory before stopping them. If startup fails, inspect only `.local/api.log` or `.local/source.log`; do not kill unrelated Python or Codex processes.

## Codex runtime

Install/sign in to the supported Codex CLI yourself; the application reuses native local authentication without copying credentials. The verified adapter used CLI 0.163.0. The runtime invokes `codex exec` in an empty temporary directory with an ephemeral thread, strict output schema, read-only sandbox, ignored user configuration and shell/web/plugin tools disabled. Test the adapter after upgrading Codex; CLI options are an integration contract.

Default caps are 20 pre-dispatch call reservations per UTC day for this installation, four per shopping session and five active sessions per user. A normal eligible purchase uses two decisions. Reservations persist even when inference fails, which bounds retries conservatively. The app does not buy API credits or change a subscription. A quota/auth/timeout failure requires an explicit user retry and does not enter an automatic model retry loop.

The rule baseline is for tests and diagnosis. It is visibly labeled and cannot replace evidence about the real model. Use a supported inference provider arrangement before hosting a service for customers; local subscription authentication is not that arrangement.

## Recovery decisions

| Observation | Safe action | Do not do |
| --- | --- | --- |
| Source timed out after authorization, dispense or capture | Keep the same execution/action; worker inquires and retries the same command when absent | Start another checkout or assume failure |
| Source remains unavailable | Keep stock/budget held; inspect operator events and source health | Release holds based only on elapsed time |
| Synthetic `source_unavailable` fault has been resolved | Use operator Retry original action; it clears that synthetic outage only | Change amount, quote, command identity or approve again |
| Delivery confirmed, capture declined | Keep `RECOVERY_REQUIRED`; inspect the recorded financial/delivery facts | Dispense another item or report paid |
| Delivery failed and authorization not captured | Await confirmed cancellation before resolving | Claim canceled on an uncertain response |
| Captured fixture followed by confirmed delivery failure | Await confirmed refund; preserve lifetime grant spend | Treat a requested refund as a completed one |
| Quote expired/price changed | Submit a fresh request and review a new exact quote | Extend or edit the old approval |
| Model unavailable | Check sign-in/allowance locally, then explicitly retry | Loop automatic calls or give the model payment authority |
| Source binding/status conflict | Stop at review, retain unresolved holds and investigate | Accept an unverified success payload |

The generic manual financial-resolution workflow is intentionally not implemented. The operator cannot fabricate source outcomes or release unknown holds. Those are production product decisions, not an SQL workaround to include in a demo.

## Logs, audit and privacy

Business events are stored in `audit_events`; the UI shows relevant identities and confirmed states. `.local/traces.jsonl` contains whitelisted OpenTelemetry attributes, with 10 MiB rotation and two backups. Prompts, credentials and candidate payloads are excluded from that exporter. `.local/api.log` and `.local/source.log` are private development logs and still require review before sharing. The raw shopping request and business audit history remain in PostgreSQL; redacted traces are not a data-retention policy for the whole product.

Use operator-authenticated `/metrics` for HTTP counts and latency. This release has no hosted dashboard, alert delivery, Langfuse integration or measured SLO. Request IDs and execution IDs help correlate a report; asynchronous workers correlate by execution ID rather than full cross-process trace parents.

## Backup and restore

For a consistent local backup, stop API and source writes first. Keep both commerce (including `agent_checkpoints`) and source effects; saving commerce alone can lose knowledge of completed external commands. Store backups only in ignored owner-only `.local/backups`, not public artifacts.

```bash
uv run python tools/stack.py down
mkdir -p .local/backups
chmod 700 .local/backups
umask 077
docker compose -p agentic-commerce exec -T postgres pg_dump -U commerce -Fc commerce > .local/backups/commerce.dump
docker compose -p agentic-commerce exec -T postgres pg_dump -U commerce -Fc commerce_sources > .local/backups/sources.dump
```

Run `uv run python tools/rehearse_restore.py` with the stack stopped to rehearse fresh migrations, downgrade/upgrade and both database restores into uniquely named disposable databases. It compares every application/checkpoint table fingerprint and removes only its own scratch databases. Private backup artifacts remain under `.local/`. Restore first into separate empty validation databases, never automatically over the live demo. Use matching schema/software versions, verify record counts, source command identities and grants, then rehearse reconciliation before resuming writes. A backup file existing is not proof of restoration. The [verification report](verification-report.md) records whether a restore rehearsal was actually executed.

For real providers, stopping this application does not stop effects at the provider. A production restoration needs provider reconciliation before new financial work. Key rotation, point-in-time recovery, encrypted backup retention and RPO/RTO are outstanding production work.

## Production gate

Before a commercial runtime: real identity/RBAC and tenant isolation review; supported hosted inference; external protocol profiles and provider onboarding; least-privilege principals and secrets management; migration/restore rehearsals; workload/evaluation targets; monitoring/alerts; support/incident ownership; accessibility and security review; distribution/dependency licensing decisions. No current measurement establishes production readiness or regulatory certification.
