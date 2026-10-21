# Proposed six-component architecture

All components are logical modules initially. The README diagram is planned, not implemented. A single FastAPI business application plus a separate graph/background runner is sufficient before measured scale requires more processes.

| Component | Owns | Must not do |
| --- | --- | --- |
| A Purchasing agent | Typed tentative intent, candidate comparison, tool plans, human pause, status monitoring and source-grounded reporting | Enforce budget with a prompt, approve/sign its own purchase or infer success from its prose |
| B Virtual kiosk/commerce | Catalog, versioned pricing, inventory/reservations, order/checkout and simulated dispense state | Duplicate Java payment engine or claim physical vending hardware integration |
| C Authorization/policy | Trusted human approval, agent/user binding, scope, expiry/revocation, one-use identity and concurrent usage reservations | Trust merchant text or agent-supplied claims as user authority |
| D Checkout/payment adapter | Stable execution/payment commands, immutable quote binding, source inquiry, deterministic saga/compensation | Blindly retry unknown payment or use a new key on graph replay |
| E Reliable execution | Durable business jobs, graph checkpoint/resume, ownership, deadlines, recovery and bounded concurrency | Treat checkpoint save as atomic with financial/dispense effects |
| F UI/observability | Trusted approval view, catalog/candidate display, separate order/payment/fulfillment status, action audit/evaluation | Display model narrative as final transactional truth |

## Process and storage boundaries

One commerce PostgreSQL database with explicit business schemas/roles; graph checkpoint tables are separately owned by the saver package. Java has its own database and API; no shared ORM/migrations/DB credential. A model/provider client is an external nondeterministic boundary. The standalone payment simulator implements a thin payment status/command port, not transaction routing/reconciliation.

T1 execution acceptance locks relevant permission/budget, quote/checkout and stock in a fixed documented order, rechecks every bound condition, reserves budget/stock, creates one order/execution, records consumed one-use approval and job intent, then commits. External payment and dispensing follow outside DB locks. Outcome observations and saga transitions are separate idempotent commits. Cross-system compensation can fail or remain unknown; it is not rollback.

## Technology adoption

| Technology | Purpose, introduction and alternative |
| --- | --- |
| Python 3.12/FastAPI/Pydantic | M1 validated API/contracts and explicit async IO; long work outside request handlers. Framework choice does not solve concurrency |
| PostgreSQL/SQLAlchemy/Alembic | M1 durable business state, transactions/constraints and schema evolution; migrations are owner/Codex work only after milestone approval |
| LangGraph | M3 stateful bounded selection/control; fake model first, real provider after separate spend approval; plain rule workflow remains baseline |
| OpenAI or Anthropic | Select one by task-specific evaluation and current limits/prices; no unsupported “best model” claim or immediate multi-provider complexity |
| PostgreSQL checkpointer | M8 persisted per-run graph state; application-effect identity and single-owner controls still required |
| Celery/Redis | Conditional M8 independent worker transport when DB runner is insufficient; DB job intent/reconciler remains authority. PostgreSQL-only scheduler is simpler initial choice |
| React/TypeScript/Tailwind | Minimal trusted approval UI by M5, broader workspace M10. Agent-generated HTML cannot become trusted approval content |
| pytest/Testcontainers | M1 onward: pure policy, actual PostgreSQL races, provider fakes and fault/replay tests |
| Langfuse | M3 metadata/traces/evaluation records if useful; consolidated M10. Keep synthetic/redacted payloads, deployment mode/cost decision explicit |
| OpenTelemetry | Correlation across API/job/tool/payment/dispense; low-cardinality operational metrics, optional Prometheus/Grafana shared with Java |
| k6 | M10 deterministic HTTP/load scenarios against simulators. Locust is viable if Python workload control proves useful; choose one primary load tool |
| Docker Compose | Reproducible local dependencies during approved development; no container/deployment files in planning |
| GitHub Actions | Later reproducible checks and eval gates after local baseline; no CI files now |
| AWS ECS | Optional M10 after explicit budget/deployment/security approval; no cloud account/resources needed to learn core system |

Optional full-text/pgvector only if exact catalog filtering and structured attributes fail measured discovery/retrieval needs. MCP is useful for independently deployed tool services, not necessary for functions within one app. OpenFGA becomes useful with a richer relationship model, not for one user/kiosk. Temporal is a possible future business-saga execution alternative if operational guarantees exceed a tested DB job runner; do not run two overlapping workflow authorities without a new design. Kubernetes agent-sandbox is optional isolation research, not initial infrastructure.

## Ownership, failure and scaling

Keep agent and commerce state independently recoverable: execution_id/order_id/payment_id/dispense_id persist before remote effects; graph can be rebuilt around them. Start one serialized graph runner and one active invocation per run. Leases alone do not fence checkpoint writes; parallel takeover requires validated owner/fence checks inside saver write transactions or a rigorously serialized execution boundary. Do not claim exactly-once model calls/billing.

Horizontally scaling API/worker processes must preserve inventory/budget constraints in PostgreSQL and respect provider budgets/pools. Measure hot SKU/grant contention before redesigning locks. Replicas/search indexes expose freshness; never use stale availability as a reservation guarantee. Readiness distinguishes business DB, one payment provider and model outages rather than restarting every process on one dependency failure.
