# ADR 008 — Standalone commerce and local subscription inference

**Status:** accepted for v0.1 implementation, 2026-11-04.

## Context

The owner wants to build commerce before the complementary Java platform, has an existing Codex subscription, and has not authorized separately billed model APIs, cloud deployment or live payments. The original design already allowed independent sources behind a payment port. A client demonstration must show transaction behavior and recovery, not imply that a checkout API wrapper is a deployed financial system.

## Decision

Build Python/FastAPI and PostgreSQL as a modular application, with an independent PostgreSQL database and HTTP process for simulated payment/fulfillment effects. Keep human approval, scoped delegated authority, inventory, order, execution, jobs and graph checkpoints distinct. The agent proposes candidates; only trusted backend transactions accept a purchase.

Use LangGraph for bounded intent/discovery/selection/approval/execution orchestration. Use the documented local `codex exec` interface behind a narrow Python adapter for structured decisions. It uses native signed-in authentication, ephemeral runtime threads, an empty temporary directory, stdin input and strict output schemas. General shell, web and plugin capabilities are disabled. The app does not copy or read the Codex auth cache. This local adapter can be replaced with a separately configured inference provider later.

The deterministic rule baseline is explicitly labeled and used for normal automated tests. It does not establish LLM quality. Cap actual subscription calls durably before dispatch and stop automatic retries on model/auth/quota failures. Do not infer exact billing from returned token counts.

Use a PostgreSQL checkpointer in a separate schema. Serialize graph writes with a process-local lock plus one database session advisory lock. Checkout advancement uses persisted jobs, leased claims, stable source commands and stage/version guards. This release favors a small number of workers over distributed graph takeover.

The frontend uses React/TypeScript and regular CSS. Tailwind is not required to implement the design. Local trace export avoids a hosted telemetry account; Langfuse is deferred. Java integration and broker deployment are optional later profiles, not standalone release gates.

## Consequences

The local project can demonstrate complete approved purchases, delegated limits and transaction faults without Java, API keys or real funds. It cannot be offered as a hosted service using one personal Codex login. Enterprise identity, supported hosted inference, real payment onboarding, tenant isolation review, production deployment and protocol conformance remain release gates for client operation.

## Alternatives

- Build Java first: delays the commerce product without improving the narrow payment contract.
- Duplicate a financial engine in Python: creates two owners for routing/reconciliation and expands scope unnecessarily.
- Use only a mock returning success: cannot prove lost-response or restart behavior.
- Wrap a model API directly: requires separate API access; keep it as a future interchangeable adapter.
- Begin with distributed agents, Kafka and Kubernetes: adds operational dependencies before the core invariants are verified.

References: [Codex noninteractive mode](https://learn.chatgpt.com/docs/non-interactive), [Codex integration](https://learn.chatgpt.com/docs/app-server), [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html).
