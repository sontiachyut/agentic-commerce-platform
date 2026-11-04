# Implementation status

Updated: 2026-11-04. Release: **v0.1 — local synthetic demonstration**. Branch: `feat/local-commerce-v1`.

Follow-up work is on `feat/interop-hardening-v2`. The owner authorized the locally feasible interoperability, identity, evaluation and operational work, and then requested deeper research before implementation. The [research dossier](research/README.md) records pinned contracts, executed feasibility experiments, current gaps and the next acceptance gates. These research results do not change the v0.1 application capability claims below.

## Authorized target

Build a standalone client-demonstrable commerce application and its engineering documentation. Local signed-in Codex inference is authorized. Java payment integration is deferred. No paid model APIs, real funds, billable infrastructure or public runtime deployment are authorized.

## Implemented and verified

| Capability | Current evidence |
| --- | --- |
| Persistent sessions, catalog and exact quote approval | FastAPI, PostgreSQL migrations, signed synthetic identities/CSRF, browser approval/history journey |
| Agent orchestration | LangGraph with PostgreSQL checkpoints; structured local Codex interpretation/selection; real signed-in smoke completed |
| Atomic acceptance | Quote/authority/stock/budget validation, one order/execution/job transaction; real-PostgreSQL stock and budget races |
| Delegation | Scoped products/kiosks, expiration, revocation, per-purchase and lifetime limits including pending holds |
| Retry/recovery | Fifty concurrent acceptance retries resolve to one execution; independent source inquiry; response-loss, compensation, expired-lease and checkpoint-recreation tests |
| User and operator experience | React/TypeScript shopping, exact approval, history, grants, activity and failure lab; four browser tests |
| Security/visibility | Loopback restriction, actor scope, source-binding validation, model caps, redacted local OTel and operator HTTP metrics |
| Operations | Reproducible locked dependencies, local lifecycle, migration and two-database backup/restore rehearsal |
| Engineering artifacts | Runtime architecture, ADR, threat model, API/OpenAPI, runbook, client demonstration and code walkthrough |

**54 backend tests passed; four browser tests passed.** Measured statement coverage: 86.63% (rounded 87%). The frontend build and Alembic metadata check passed. Python and npm dependency audits reported no known vulnerabilities after removing an unused dependency flagged by the audit. CI is configured; no remote CI run is claimed.

A real Codex request completed interpretation, selection, exact user approval, synthetic payment response-loss recovery and confirmed delivery. The repeated checkout returned the same execution ID. This is one integration smoke, not a 100-case model-quality evaluation or throughput benchmark. See [verification](verification-report.md).

## Remaining release gates

1. **External interoperability:** pinned AP2 wire/signature/issuer verification, Visa TAP enrollment/signatures, UCP/ACP merchant adapters and their conformance fixtures. Internal contracts do not constitute these protocols. Current MCP is read-only subset behavior.
2. **Measured model quality:** versioned held-out requests, repeated real-model runs, valid-set/clarification/constraint metrics and operational outcome scoring. The graph controls tool order; no model tool-selection accuracy claim is established.
3. **Client operation:** production identity/tenant administration, supported commercial inference, actual provider onboarding, least-privilege service/database credentials, deployment, workload/SLO/load measurement, alerting and support ownership.
4. **Release review:** accessibility/security review, distribution/dependency licensing decisions, retention and broader incident/restore exercises. No regulatory or network certification is claimed.

No payment platform, cloud service, Redis/Kafka broker, hosted telemetry account or model API key is required for this local release. The Java platform remains an optional adapter target.

## Read next

- [Run the application](../README.md)
- [Client walkthrough](client-demo.md)
- [Runtime architecture](runtime-architecture.md)
- [Protocol matrix](protocol-support.md)
- [Runbook](operations-runbook.md)
- [Code learning route](engineering-guide.md)

Earlier documents preserve the broader design baseline. ADR 008 supersedes historical planning-only authorization and mandatory-Java dependencies. Evidence here takes precedence over old milestone labels and over unmeasured numbers in interview narratives.
