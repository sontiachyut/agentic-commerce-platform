# Proposed commerce domain and persistence

No domain entities, migrations or APIs are implemented. Seven concepts remain distinct even if one UI displays them together.

| Concept | Meaning and proposed state |
| --- | --- |
| User intent | Tentative extracted preferences plus original user text, clarification state and validated structured constraints; not permission |
| Purchasing authority | One-use exact approval or delegated scoped grant; ACTIVE/EXPIRED/REVOKED/EXHAUSTED; versioned policy and trusted signer/issuer |
| Inventory reservation | Durable quantity claim at kiosk; HELD/COMMITTED/RELEASED/RESOLUTION_REQUIRED; expiry does not override in-flight uncertainty |
| Checkout/order | Frozen commercial terms and one business purchase; DRAFT/AWAITING_APPROVAL/READY/EXECUTING/COMPLETED/CANCELED/RECOVERY_REQUIRED |
| Payment | Observed provider/Java state and operation identities; ACCEPTED/UNKNOWN/AUTHORIZED/CAPTURED/CANCELED/PARTIALLY_REFUNDED/REFUNDED/DECLINED as appropriate; source owns truth |
| Fulfillment | NOT_STARTED/DISPATCHING/UNKNOWN/DISPENSED/FAILED_CONFIRMED; a timeout cannot become confirmed failure |
| Agent execution | Graph run QUEUED/RUNNING/WAITING_HUMAN/WAITING_SOURCE/COMPLETED/FAILED/CANCELED; graph completion is not order completion |

## Proposed records

All rows use opaque IDs, trusted owner/tenant scope, created/updated time and version where mutable. Public IDs are not authorization credentials.

| Record | Fields and constraints |
| --- | --- |
| purchase_session | id, user_id, agent_id, original_request, typed_intent/version, status, active_run; request idempotency and clarification links |
| agent_run | id, session_id, graph/prompt/tool/model versions, checkpoint_thread, status, budget/round counters, owner/fence; one active run per session revision |
| kiosk / catalog_product | merchant/kiosk/product IDs, structured attributes, synthetic descriptions, active status and catalog version; descriptions untrusted |
| inventory_level | kiosk_id, sku_id, stocked_quantity, reserved_quantity, version; unique kiosk/SKU; 0≤reserved≤stocked; no backorders MVP |
| quote / quote_line | id, kiosk/merchant, SKU/quantity/unit/total/currency, price_version, tax/fee policy, expires_at, canonical_hash; immutable versions |
| purchase_authority | id, user, agent, kind, exact_quote_hash or delegated constraints, currency/caps, valid_from/until, revocation_version, status, policy_version, signing_key_id/ref |
| authority_usage | grant_id, execution_id, reserved_minor, consumed_minor, state, grant_version; unique grant/execution; atomically bounded aggregate budget |
| approval_receipt | id, approval_request_id, authenticated actor, quote hash/version, decision, time, issuer/audience, one-use nonce/digest; immutable unique request/nonce |
| checkout | id, session/business_intent, quote/version, authority_id, expected_version, status; one canonical checkout execution identity for same purchase intent |
| order / order_line | id, checkout_id, user/kiosk, immutable approved monetary/item snapshot, status/version; unique checkout_id; line identity and quantity fixed at execution |
| reservation | id, execution/order, kiosk/SKU/quantity, state, original expiry, resolution hold reason; unique execution/SKU; stock changes under row lock |
| checkout_execution | id, checkout_id, semantic request hash, state, payment_business_reference, dispense_command_id, next_action, version | Stable command identity; unique checkout finalization; current saga owner |
| payment_operation_link | execution_id, payment_id, operation_id, kind, stable idempotency key hash, source/version, observation | Unique execution/kind/business action; transport attempts separate; no copied payment engine |
| dispense_command / observation | stable command_id, execution/order, immutable item/quantity digest, state, provider receipt, observed_at | One physical-simulation effect per command; duplicates return existing result; unknown retained |
| business_job / inbox / outbox | durable action identity/generation, due/lease/fence, source/event/digest, schema/version | At-least-once scheduling/events with atomic local effects and quarantine |
| audit_record | user/agent/service actor, session/order/execution/grant, action/reason, quote digest, prior/new version, correlation and time | Append-only logical decisions, denied actions and compensation history |

Graph checkpoint tables remain package-owned in a separate schema. They cannot replace order/execution/payment-link/dispense records, and saver writes are not automatically in the commerce transaction.

## Money, scope and business invariants

USD integer minor units initially, signed 64-bit overflow validation, positive item quantity (one MVP), no floating point. Total = sum of authoritative line subtotals plus explicit fees/taxes under a versioned policy; MVP fee/tax zero is explicit, not inferred. Payment amount/currency must equal frozen order total/currency. Price changes create a new quote/hash; never edit approved terms in place.

Available inventory = stocked−reserved. Reserve under lock only if sufficient; dispensing confirmation decrements stocked and reserved once. Confirmed failed-before-dispense releases reservation; unknown dispensing keeps stock quarantined until authoritative resolution. A reservation sweeper must inspect execution state, not blindly release every elapsed TTL.

One approval nonce and one business execution per intended checkout; retry/replay returns same execution/order/payment links. Same key/changed quote or quantity conflicts. A new session/user request that happens to repeat text is not automatically a duplicate—obtain explicit intent/approval rather than guessing semantic dedup.

Grant availability includes reserved/unknown usage as well as charged usage. Concurrent purchases serialize against the grant/budget row; independent grant/SKU locks follow one order to avoid deadlock. Refunds do not automatically replenish lifetime delegated spending budget; restoration requires an explicitly defined policy/version to avoid buy/refund/rebuy bypass.

Payment and fulfillment are not one Boolean. An order is COMPLETED only after required dispense and capture confirmation; dispensing success with capture failure/unknown is RECOVERY_REQUIRED and never repeated dispensing. Refunded/canceled orders preserve original fulfillment observations. Agent output uses these fields, not its remembered narrative.
