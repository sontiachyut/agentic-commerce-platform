# Proposed product requirements

**Planning baseline:** 2026-10-21. No application exists; milestone 0 only.

## Users and primary workflow

A shopper delegates selection at a virtual kiosk. A trusted approval surface displays exact purchase terms. An operator can inspect denials, uncertain payments, failed dispensing and compensation. An engineering reviewer can run a reproducible end-to-end demonstration and inspect the evidence behind the final result.

Example: “Find a protein bar under $4 at Kiosk A and buy it.” The agent extracts preferences, queries authoritative catalog/quote/stock, proposes a candidate, obtains trusted approval, requests approved checkout execution, monitors payment/dispense status, and reports confirmed or unresolved outcome.

## Functional requirements

| Requirement | Deterministic owner | Mandatory scenarios |
| --- | --- | --- |
| Discover/filter a small kiosk catalog and compare eligible items | Catalog/query tools; agent interpretation remains tentative | AC-01/03/09/10 |
| Authoritative versioned quote with money/currency, item, merchant, quantity and expiry | Commerce pricing | AC-01/03 |
| Exact human approval through authenticated UI, bound to quote digest | Authorization service, not model text | AC-01/03/06 |
| Delegated scoped purchase permission after human flow works | Policy engine with budget/merchant/product/time constraints | AC-02/06/10 |
| Concurrent stock reservation and one canonical order per checkout intent | Commerce transaction | AC-04/05 |
| Stable execution identity and payment adapter; authoritative inquiry | Checkout coordinator | AC-05/08 |
| Idempotent software dispense after appropriate payment state | Simulated kiosk and fulfillment coordinator | AC-07/08 |
| Deterministic void/capture/refund compensation based on confirmed payment and fulfillment | Commerce coordinator plus Java financial policy | AC-07 |
| Durable sessions, jobs, agent checkpoints, review/resume and replay recovery | Application state and graph orchestration separately | AC-05/08 |
| Denials/audit, adversarial tool handling and verified final reports | Security/policy/reporting gates | AC-06/09/10 |

## MVP and advanced scope

One synthetic user, one kiosk, USD, small catalog, quantity one per purchase, fake payment provider and simulated dispensing. Human approval precedes every initial purchase. A quote is not a stock promise; final execution reserves available stock atomically. The agent cannot change approval by paraphrasing it.

Milestones 1–4 establish foundations/discovery; no purchase tool is enabled without the milestone-5 policy gate. Milestone 6 completes human-approved standalone checkout. Delegated authority is milestone 7, durability/concurrency milestone 8, Java integration/compensation milestone 9, full evaluation/observability/deployment milestone 10. Security/evaluation design begins now and tests accompany every slice. Optional milestone 11 explores standards/identity/isolation only after core correctness.

Advanced: richer merchant/catalog discovery, quantities and baskets, additional currencies/taxes/shipping with revised quote semantics, interoperable protocol adapters, external identity registry and stronger runtime isolation. Each requires new invariants and evaluation, not a larger prompt.

Excluded: real hardware control through payment terminals, live funds/cards, user payment credentials accessible to LLM, general payment engine duplication, unlimited external URLs/tools, autonomous signing/permission changes, generic chatbot scope, unsupported AP2/UCP/ACP/TAP certification, and production deployment claims.

## Nonfunctional requirements and success criteria

Proposed hard gates: no backend-authorized purchase outside scope; no oversold stock; no budget overspend including pending/unknown attempts; one order and intended financial effect per execution identity; no repeat dispense under uncertainty; no “purchased” response without required authoritative states. These are future corpus acceptance gates, not achieved claims.

Bound requests, tool output, graph rounds, tokens/cost, execution time, queues and provider concurrency. Initial model workflow hypothesis: ≤10 tool calls and ≤3 decision rounds before completion/clarification/escalation; human wait and payment-resolution wait are persisted, not blocking workers. Tune after measured baseline. Context/model prices and exact model choice remain unselected.

Accepted execution must survive process restart; database loss recovery needs separate backup validation. One transaction protects local policy/budget/stock/order/job intent, not external payment/dispense. Source outages preserve unknown state instead of fabricated success. Every consequential action records actor, grant/version, quote/hash, execution/payment/dispense identity and reason.

Privacy/security: synthetic-only data, scoped tools and identities, no secrets or full prompts by default in traces, approved artifact retention. Langfuse/OTel are observability, never authorization or source of truth. Quality metrics distinguish selection/intent mistakes from backend policy enforcement.

The product succeeds when both independent mode and optional Java mode reproduce AC-01–AC-10, including failures, with inspectable authoritative state and honest evaluation. Proposed throughput scenarios are simulator experiments; an LLM shopping loop is not the benchmark driver.
