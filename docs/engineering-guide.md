# Engineering walkthrough

Use this as a code-reading route. Run the system and tests while reading; design explanations alone are not implementation evidence.

## 1. Follow one purchase

Start at `web/src/App.tsx` and `PurchaseReview.tsx`. The user submits a request, reviews a backend quote, then explicitly approves it. `src/commerce/api.py` derives actor/CSRF context and routes commands. Open `service.py` to trace `create_session`, `quote`, `approve` and `accept`.

In `accept`, identify the transaction boundary: quote/authority validation, stock and delegated-budget holds, order/execution identity and job creation all commit before a remote effect. Find the unique database constraints in `models.py` and the Alembic migration. Explain why an in-memory lock would not protect two API processes.

Exercise: approve a quote, change the product price from the operator view, then attempt acceptance. Identify the precise revalidation that prevents using stale terms. A previously accepted purchase keeps its accepted snapshot; a later price update is not permission to change that purchase.

## 2. Separate the agent from authority

Read `agent.py`: interpret → discover → select → quote → approval → execute. LangGraph persists node progress and pauses at `interrupt`. The resume payload is not an approval receipt; execution reloads trusted records. `planner.py` validates structured intent/selection and rejects invented candidates before backend revalidation.

The current agent follows a bounded graph with deterministic tool order. Codex decides interpretation and candidate selection, not arbitrary next-tool planning. It is not a free-running autonomous browser. Exact tool order is therefore an orchestration property; it must not be misreported as a measured model tool-selection accuracy score.

Read the real adapter invocation and its tests. Explain why running Codex from an empty directory, disabling tools and validating output reduces exposure. Also explain why those local controls do not make an arbitrary hosted process sandbox safe or grant production credentials.

Exercise: inspect the compromised-planner test. The backend rejects an ineligible ID even when the model component proposes it. That proves a tested policy boundary, not universal resistance to prompt injection.

## 3. Follow a lost response

Read `worker.py`, `payments.py` and `simulator.py`. The source has its own database and command record. The worker snapshots a stage/version, makes a call outside the commerce transaction, validates the observation and advances only if that stage/version is still current.

The request key, business quote identity, job claim token and source command ID solve different replay problems. A graph checkpoint cannot replace any of them. “Exactly once” describes a tested business invariant within these boundaries; it is not a claim that messages or processes execute once.

Exercise: run the lost-authorization/dispense/capture tests. Find where the effect is committed before the injected response failure, and where inquiry recovers it. Compare source-unavailable, confirmed delivery failure and capture-declined-after-delivery. Explain why only some paths can release stock or cancel/refund.

## 4. Reproduce concurrency

Read the stock and budget race tests in `tests/test_checkout.py`. They use separate PostgreSQL connections, not mocked repositories. Row locks serialize competing acceptance; constraints protect invariant violations. The 50-request retry case checks one order/execution and the expected distinct source commands, not 50 paid operations.

Exercise: draw the acceptance and finalization lock order. Explain how it reduces deadlock risk, why network calls stay outside those locks, and why retries still need stable business identities.

## 5. Understand workers and operations

Jobs persist before processing. Claims use `FOR UPDATE SKIP LOCKED`, expiring leases and claim tokens. Graph invocations are globally serialized with a PostgreSQL advisory lock; checkout has a separate worker so a slow model does not block already accepted purchases. This favors bounded local correctness over throughput.

The graph lock is not arbitrary-partition fencing. Model calls can be repeated after a crash between inference and checkpoint, so persisted call reservations cap attempts conservatively. Model failures require explicit retry. Financial sources need independent idempotency because a worker can lose its lease after an effect.

Read `observability.py`, the threat model and the runbook. Trace metadata is redacted; database requests/audit records still need a production retention policy. HTTP latency metrics are not a complete SLO or an agent-quality evaluation.

## 6. Know what remains

Read [protocol support](protocol-support.md), ADR 008 and [status](STATUS.md). Internal authority does not establish AP2 wire conformance; local identity is not Visa TAP registry trust; typed internal endpoints are not UCP/ACP negotiation. The current MCP endpoint is a read-only subset. Java integration remains optional.

Before selling a deployed service, define a workload/SLO and a held-out repeated model evaluation; implement commercial inference, real identity/tenant administration and provider contracts; rehearse migration/restore; review security/accessibility/operations and distribution licensing. Do not reuse interview-document target numbers as measurements.
