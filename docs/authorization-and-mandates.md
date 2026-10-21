# Proposed purchasing authorization and mandate model

This is an original project-specific authorization contract informed by AP2, not AP2 implementation/compliance. No policy code, signing keys or SDK integration is created in milestone 0. Distinguish permission to purchase from a processor's financial authorization/hold.

## Human-approved first

1. Agent proposes a product and obtains an authoritative immutable quote.
2. Trusted backend creates approval request bound to user, registered agent/session, merchant/kiosk, product/quantity, total/currency, price/quote version, expiry and canonical quote hash.
3. Authenticated UI renders backend fields safely, including final total and “quote is not stock reservation” notice. Merchant text and model-generated summaries cannot replace these fields.
4. User explicitly approves on this trusted surface; backend stores an immutable one-use receipt, issuer/audience, nonce, validity and binding. Clicking an ordinary chat statement is not enough unless the trusted approval endpoint authenticates and binds it.
5. Execution revalidates price, stock, authority, expiry/revocation and identity under a transaction, consumes the approval for one stable execution, and persists stock/budget/order/job intent before payment IO.

If quote/price changes, human mode rejects stale approval and requests approval for a new quote—even if still under the user's original natural-language maximum. Exact approval and general preference are different authority scopes. Decline/reject leaves no new payment job.

## Delegated permission later

Proposed grant fields: grant_id/version, user_id, registered agent_id/key binding, allowed kiosk/merchant IDs, product IDs or server-verified category constraints, currency, per-purchase maximum, total budget, quantity/purchase-count limits, valid_from/until, revocation state/version, refund-budget restoration policy, issuer/audience/key ID, policy version and replay identity. Unknown constraints fail closed; model text cannot widen them.

Natural-language delegated intent must be displayed/confirmed as typed permission before activation. Product category/dietary labels come from trusted structured catalog policy or user-approved source; a product description cannot declare itself eligible. Ambiguous user preference causes clarification, not expanded permission. The first delegated version can use product allowlists rather than attempting unverifiable free-text rules.

For each execution, backend creates an exact purchase-bound authorization record referencing the active grant version and current quote hash. It atomically reserves usage against total/per-purchase/count constraints. A model can propose use of a grant but cannot issue/edit one or invoke its signing authority.

## Atomic policy and revocation semantics

Fixed local lock order: authority/budget→checkout→inventory rows sorted by kiosk/SKU→execution/order. Recheck identity, grant version/status/time, quote version/hash, price, quantity and available budget/stock. Insert unique usage/execution/nonce and outbox job intent together. If any check fails, rollback all local reservations and persist a separately safe denial audit. No remote call inside lock.

**Execution linearization point:** committed deterministic acceptance consumes/reserves authority for this one execution. A revocation committed before that point prevents acceptance. A revocation after acceptance prevents new executions and requests best-effort cancellation of accepted-but-undispatched work; it cannot retroactively prove a network payment stopped. Recheck revocation before dispatch, but document the inevitable race between that check and remote acceptance. Once an effect may exist, inquire/compensate by actual state; never label it safely canceled solely because a grant was revoked.

An already committed execution is authorized by the grant snapshot at acceptance; audit records revocation afterward. Do not promise “no financial effects after the user clicks revoke” across distributed systems. A stronger semantics would require provider-side revocation/conditional execution and a new contract. Expiry uses the same explicit acceptance/dispatch semantics; no new purchase begins under expired permission, while settlement/recovery of prior accepted work remains governed.

## Budget and reservations

Let available budget = grant cap − consumed charged usage − reserved pending/unknown usage. Use database integer arithmetic and unique execution usage rows, not model arithmetic or Redis locks. Reserve the exact all-in order total before dispatch. Known non-execution releases usage; unknown authorization retains it. Confirmed void before capture releases reserved usage according to policy. Confirmed capture moves reserve to consumed. Refunds do not automatically reopen a lifetime cap in the MVP; any later restoration is explicit, versioned and audited.

Two independent orders sharing a grant serialize against the same row even if they reserve different products. Pending human approval is not a budget reservation by default; UI availability can change before execution. Explain policy rejection rather than overspending to honor an old display.

## Tamper resistance and replay

Keep authoritative permissions/approvals server-side; clients/model carry opaque refs, not trusted editable JSON claims. Canonical versioned quote serialization and digest bind commercial facts. At service boundaries use established JWS/JWT libraries and allowlisted algorithms/issuer/audience/time/key IDs, with private signing keys accessible only to deterministic approval/execution service identities. A hash is integrity evidence relative to a trusted source, not a signature or proof of consent.

Single-use nonce/redemption uniqueness, semantic idempotency, grant-version checks and immutable execution identity are separate controls. A valid signature with a fresh timestamp is still replayable without consumption state. Store key-rotation/retention policies; do not design custom cryptography or give the LLM access to an unrestricted signing endpoint. No real keys are generated now.

## AP2 mapping and explicit limits

At the inspected AP2 commit, human-present flows approve closed checkout/payment mandates; human-not-present flows use open constraints and agent-bound closed mandates. The SDK has checkout/payment constraint verification and separate cryptographic layers. Constraint methods alone do not authenticate a signer, and decoding a checkout JWT is not verifying its signature. [Pinned analysis](reference-analysis.md).

Our exact approval resembles transaction-bound authority; our delegated grant resembles scoped open authority. We do not implement SD-JWT credential issuance, AP2 mandate chains, trust enrollment, payment credentials, protocol negotiation, cryptographic presentations, receipts or conformance in MVP. Optional interoperability requires a pinned protocol version, full applicable validation, negative tests and explicit evidence before any compatibility claim. AP2 examples do not remove our need for durable atomic budget/replay/revocation state.

## Acceptance evidence

Future policy tests: boundary amount/currency, total/count cap, concurrent usage, forbidden merchant/product, altered hash/price/quantity, expired/not-yet-valid grant, revoked version, nonce replay, same execution replay, wrong user/agent/audience, invalid signature, key rotation and revocation-vs-dispatch races. Denials occur at backend even if the model tries the forbidden action. AC-01/02/03/05/06/10 are mandatory.
