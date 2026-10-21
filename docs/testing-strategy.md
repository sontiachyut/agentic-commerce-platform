# Proposed commerce and agent validation strategy

No automated tests or load/evaluation runs exist. [AC-01–AC-10](production-scenarios.md) define mandatory acceptance cases; [evaluation](evaluation-plan.md) defines probabilistic metrics and hidden labels. Source tests were inspected, not executed or inherited.

## Deterministic tests accompany every slice

Pure pytest tests: money/overflow/currency, quote canonicalization/hash, eligibility, grant/approval scope/time, reservation arithmetic, saga transition and final-report state policy. Pydantic/API tests: valid/invalid shape plus semantic ownership, stable errors, bounded payloads, same-key replay/conflict. PostgreSQL/Testcontainers: unique checkout/order/nonce/usage, stock and budget row coordination, rollback, stale versions, committed acceptance and restart persistence. Mocks cannot prove database lock/isolation behavior.

Thin payment/dispenser contract tests run against independently stateful simulators, then optional Java adapter. Confirm effect before response-loss and recovery by stable ID. Hidden simulator oracle is test-only, unavailable to tools/model. Do not reset external effect state during worker restart tests.

Concurrent tests use barriers and separate connections/processes: two agents/last SKU, shared grant/different SKUs, duplicate execution, price/revocation races, repeated compensation, paused old owner and reservation-expiry sweeper. Assert stock/reserved/consumed amounts, usage, order/operation/dispense counts and source observations, not merely HTTP success.

## Crash and replay matrix

Interrupt before/after local acceptance; external payment dispatch/effect/observation save; dispense effect/response; capture/refund request/result; job publication/marker; inbox DB effect/offset; tool result/checkpoint; report save/checkpoint; approval decision/resume intent; ownership lease/connection loss. Kill and process pause are separate faults. Unknown payment/dispense retains holds and source inquiry; compensation is new durable work, not rollback.

One active graph invocation per run. Saver ownership must be tested at checkpoint/pending-write mutation boundary before parallel takeover; otherwise retain serialized execution and document limits. Business unique guards must protect effects even if graph state is missing/replayed. Model calls may repeat after ambiguity and must appear in cost accounting.

## Security and reporting

Backend tests deny absent/stale/forged/replayed permission, wrong user/agent/merchant/SKU, expired/revoked grant, budget overspend, tampered quote, arbitrary tool/URL/SQL, signing access and raw financial/dispense calls. Inject untrusted instructions in product text, tool errors, status payloads and UI content. Synthetic secret-like canaries must not reach model/trace surfaces. A valid schema or signature alone is not consent/usage enforcement.

Typed reporting gate rejects false purchase/payment/dispense/refund claims and preserves UNKNOWN/recovery status. Human review/rubric measures preference and explanation quality; cannot replace authoritative effect assertions.

## Four separate lanes

1. No-provider correctness/security/recovery: deterministic fakes, virtual clock and actual DB semantics.
2. Low-volume Stripe sandbox integration: supported test payment/refund/dispute/webhook behavior only, source IDs/versions retained; owner authorizes setup/credentials separately.
3. Deterministic capacity: k6 and local source/payment/dispenser/fake-model simulators; no Stripe/LLM load traffic.
4. Approved real-model quality/cost: labeled corpus/baselines, finite budgets and actual usage/failure results.

Capacity reports record commit/runtime/container versions, machine, DB/dataset/indexes, arrival model/seed, simulator timing assumptions, worker/pool limits, duration/warmup/stop bounds. Report offered/accepted/rejected/completed/unknown, queue/active/wait latency, p95/p99, stock/budget/effect reconciliation after drain and source lag. Fake-model throughput is not LLM capacity; sandbox timing is not production processor timing.

## Completion evidence

Approved milestone, actual commands/outcomes, scenario/config/policy/model/graph versions, redacted trace/failure, reviewed repair and remaining limits. Both independent demos plus integrated contract corpus must pass their respective gates. CI, infrastructure and performance tests will be implemented only in later approved scopes; none are configured or run now.
