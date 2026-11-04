# Verification report — historical v0.1 and local hardening

The original v0.1 record below is preserved. Current candidate evidence: 87 backend tests passed in 17.36 seconds; six browser tests passed (including real local OIDC and four-screen automated accessibility checks); the non-root packaged HTTP smoke completed in 2.597 seconds with synthetic response-loss recovery and duplicate execution resolving to one ID. The updated migration chain also passed fresh upgrade, downgrade-to-base, upgrade and metadata checks, and both commerce/source restores matched their table fingerprints. Identity-provider/configuration recovery remains a separate exercise. These timings are individual local observations, not latency percentiles or capacity claims. The older Docker ARM guest required the documented portable OpenSSL CPU profile. See [current status](STATUS.md) and [identity/packaging](local-identity-and-packaging.md).

Decision results are retained under results/evaluations: rule baseline 100/100; original Codex batch 1/3; corrected three-case regression 3/3. The original failures were not removed. No 100-case real-model accuracy, external merchant certification, deployed monitoring or production throughput is established.


Recorded 2026-11-04 on macOS. This report covers the standalone local implementation, not a deployed customer service. All purchases, products and provider effects are synthetic.

## Environment and commands

Python 3.12.7; uv 0.5.24; Node 23.9.0; PostgreSQL 17 from the digest pinned in Compose; Codex CLI 0.163.0. Python and npm dependency locks are committed with the implementation. The documented Node baseline and configured Linux CI use Node 22+. Linux CI has not been executed remotely in this work.

| Check | Observed result |
| --- | --- |
| `uv run ruff check src tests tools migrations` | Passed |
| `uv run ruff format --check src tests tools migrations` | Passed |
| `uv run pytest -q --cov=commerce` | **54 passed**, 10.73 seconds in the recorded final backend run |
| Statement coverage | **1,153 / 1,331**, 86.63% (displayed as 87%); not a branch-coverage claim |
| `uv run alembic check` | No new upgrade operations detected |
| `npm run build --prefix web` | TypeScript compilation and optimized Vite build passed |
| `npm run test:e2e --prefix web` | **4 passed**, 11.9 seconds in the recorded browser run |
| Python dependency audit | pip-audit 2.10.1: no known vulnerabilities in the installed locked application/dev environment after an unused vulnerable dependency was removed |
| npm dependency audit | Zero known vulnerabilities reported at verification time |
| Restore/migration rehearsal | Fresh upgrade, metadata check, downgrade to base, upgrade and check passed in a disposable database |
| Two-database restoration | Commerce: 14 tables/379 rows; source: 2 tables/28 rows at backup time. Restored per-table row counts and SHA-256 fingerprints matched |

Times describe these local runs, not performance budgets. Dependency audits are point-in-time advisory checks, not proof that dependencies contain no vulnerabilities. CI is configured in `.github/workflows/verify.yml` and must run after a separately authorized push before being described as green.

## Core acceptance evidence

| Scenario | Executed coverage | Limit |
| --- | --- | --- |
| AC-01 human approval | No approval/forged approval denied; graph resume cannot confer authority; full captured-and-delivered purchase | Synthetic identity and provider |
| AC-02 delegation | Concurrent requests compete against one held-plus-spent budget; revoked/out-of-scope grants denied | Small bounded local workload |
| AC-03 stale terms | Changed product price/version rejected before reservation or payment | Not an external merchant webhook integration |
| AC-04 last item | Two separate PostgreSQL connections race; one accepted, one out-of-stock | One-SKU race, not a capacity benchmark |
| AC-05 duplicate checkout | 50 concurrent submissions through eight threads yield one execution/order and three distinct normal saga commands | Does not prove universal exactly-once delivery |
| AC-06 expired/revoked authority | Inactive approval and grant checks fail closed | Production issuer/key trust not implemented |
| AC-07 failed fulfillment | Cancellation/refund paths and lost compensation response; delivered-but-capture-declined remains review | No real acquirer or physical dispenser |
| AC-08 recovery | Independent source commits before lost authorize/dispense/capture response; worker recreation/expired lease; real PostgreSQL graph checkpoint reconnection | Not arbitrary database-partition fencing or regional failover |
| AC-09 malicious content | Compromised planner/injected product cannot authorize an ineligible purchase | Not a repeated real-model adversarial evaluation |
| AC-10 forbidden scope | Wrong user/product/merchant rejected; forbidden kiosk stops before quote/execution | Not an enterprise IAM audit |

Additional tests cover CSRF/origin checks, request idempotency, malformed MCP inputs, model invocation/schema failures, durable quota reservations, completed-session admission, unknown source statuses, source-observation binding and telemetry redaction. Test fixtures refuse to recreate tables outside the named dedicated test databases.

The browser suite covers exact approval and persistent history, lost payment response recovery, ambiguity without purchase, and a 390-pixel viewport without horizontal overflow. Screenshots were visually inspected. This is not a complete accessibility audit or every browser/device matrix.

## Real Codex integration smoke

At 2026-11-04 19:45:27 UTC, `tools/smoke.py --provider codex` completed one purchase against the real local CLI adapter and independent HTTP source. The user-facing result was COMPLETED with CAPTURED payment and DISPENSED fulfillment. A duplicate checkout returned the identical execution ID. The source deliberately lost its authorization response after commit and the worker recovered by inquiry.

The two recorded model decisions took 4.920 and 4.270 seconds. End-to-end smoke elapsed time was 12.105 seconds. The CLI reported 12,874 input tokens and 99 output tokens in total. These are observed runtime fields, not a separately billed API cost calculation. Earlier adapter integration attempts exposed strict-output schema requirements; those failures were corrected and are covered by tests.

This establishes that the real signed-in adapter works for that scenario. It does **not** establish 97/100 accuracy, 20/20 ambiguity handling, model safety across arbitrary prompts, a latency percentile or a production throughput figure. Those historical narrative targets have not been relabeled as measurements.

## Operational evidence and unresolved work

The application/source were stopped and restarted without removing their volume; completed business state remained available. Restore rehearsals ran only in uniquely named scratch databases, then removed those databases. Private dumps, raw smoke output, coverage and audit evidence remain ignored under `.local/`; they are not published artifacts. The public report deliberately contains only synthetic aggregate evidence.

External AP2/TAP/UCP/ACP conformance, full MCP transport compatibility, real-model held-out evaluation, hosted inference, production identity, real payments, deployment/load/SLO/alerting, broader accessibility/security review and commercial licensing remain open gates. Read [status](STATUS.md), [protocol support](protocol-support.md) and [threat model](threat-model.md).
