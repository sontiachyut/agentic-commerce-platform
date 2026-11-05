# Protocol contracts and compatibility

## Version selection

| Component | Research baseline | Selection rule |
| --- | --- | --- |
| AP2 | v0.2.0, `b4587ac1d055888a73b4b21750973cffba961793`; current head `e1ea56db72a6385bce3e5c1112b3a56ce60acb43` | Use exact mandate types and tagged SDK/spec; sampled previously inspected SDK files match the tag |
| MCP Python SDK | 2.3.0, `2118f14f8a19bc158d8a1cf90af58d85d187f849` | Use tagged documentation; test modern 2026-07-28 and legacy 2025-11-25 |
| UCP | v2026-08-25, `87dd4b1fcff9105d68173120897237fa784c74ef` | Freeze release schemas; current head has changes in 63 retained paths, so do not mix them silently |
| ACP | spec/2026-04-17 at `7fdd78df677a94dce04c770644b0fbbb1401272b` | Pin that schema/API version rather than copying the older commercial integration guide |
| Shopify Shop | 1.2.0, `70017fb4def4f2fdff8537625a1fb88a338cb0ef` | Reference public client contract/safety guidance; managed checkout/wallet backend is not included |
| TAP | Merchant specification retrieved 2026-11-04; RFC 9421 basis | Freeze a content hash and a supported local verification profile; no Visa enrollment claim |

## AP2

AP2 v0.2 defines closed and open Checkout and Payment Mandates. Exact versioned types include `mandate.checkout.1`, `mandate.checkout.open.1`, `mandate.payment.1` and `mandate.payment.open.1`. Unknown types/constraints fail closed. A closed checkout is bound to the merchant-signed checkout JWT; the Payment Mandate's transaction reference binds to that same checkout. A valid signature alone does not establish trusted issuer, intended audience, current authority, budget or transaction outcome. [Specification](https://ap2-protocol.org/ap2/specification/), [authorization framework](https://ap2-protocol.org/ap2/agent_authorization/).

Use the Trusted Agent Provider model first: a deterministic trusted surface obtains consent and controls issuer signing. Human-present direct closed mandates precede constrained autonomous open-to-closed delegation. Agent signing keys belong to deterministic execution code and must not become a free-form model signing tool. Open mandates require holder-key binding and all fixed claims/constraints must survive closing. General agent-to-agent intermediate delegation is a separate profile, not implied by supporting one open-to-closed hop.

AP2's SDK exposes separate cryptographic chain, checkout constraint and payment constraint helpers. `CheckoutMandateChain.verify()` parses the checkout and evaluates constraints; its name does not mean it verifies the merchant JWT signature. Application code must independently verify that signature, exact signed bytes, issuer/key trust and expected checkout binding. The SDK's optional x5c resolver must not be used with an implicit trust-all root configuration.

Select ES256 for merchant Checkout JWT signing while the v0.2 algorithm/entropy ambiguity remains unresolved upstream. Its authoritative specification requires a nondeterministic signature scheme; another security section permits sufficient payload entropy. UCP documents this inconsistency. This profile can avoid it without weakening either side by using ECDSA for checkout and distinct Ed25519 keys for HTTP recognition. [UCP AP2 extension](https://ucp.dev/specification/payment/extensions/ap2-mandates/).

Signed checkout/payment receipts bind their reference to the presented closed mandate. A receipt is validated against expected issuer, reference and business identity; it does not become evidence for a new purchase. Store verified receipt metadata and protected original artifacts separately from model-visible state. Mandatory source confirmation remains independent of the agent's final message.

Recurring permission needs explicit recurrence/budget semantics and authoritative usage history. An internal multi-purchase grant is not automatically an AP2 recurring mandate. Start with a narrowly documented ON_DEMAND/count/budget profile, reject unsupported recurrence modes, serialize overlapping presentations and preserve unresolved holds. The spec's general autonomous-flow wording and explicit recurrence constraints require a documented supported interpretation and negative tests.

## UCP and the AP2 extension

Implement discovery at `/.well-known/ucp`, a versioned platform profile, capability intersection, a supported checkout REST service and its declared payment handler. UCP's pinned response includes a protocol envelope and authoritative checkout terms. Operation-specific request/response schemas are projections using `ucp_request` annotations; validating a create request against the unprojected master schema is incorrect. Generate/bundle projections with pinned `ucp-schema` 1.4.1 and validate offline at runtime. [Overview](https://ucp.dev/specification/overview/), [checkout REST](https://ucp.dev/specification/shopping/checkout/rest/).

The AP2 extension is security-locked once negotiated: completion cannot drop the mandate or silently downgrade to an unprotected flow. Merchant authorization uses detached JWS over JCS-canonicalized checkout content excluding the top-level `ap2` object. Reconstruct the exact compact checkout JWT for AP2 binding. Hashing raw JSON, a detached signature string or a differently serialized checkout is not equivalent. [Extension](https://ucp.dev/specification/payment/extensions/ap2-mandates/).

Important states: `incomplete`, `requires_escalation`, `ready_for_complete`, `complete_in_progress`, `completed`, `canceled`. Completed checkout means an order was placed, not that delivery happened. Accepted asynchronous completion has no order field. Keep external checkout, internal order, financial and fulfillment states distinct. UCP may require buyer handoff; do not fabricate an automated success if a required action is unsupported.

## ACP

The pinned ACP OpenAPI specifies five checkout operations: create, retrieve, update, complete and cancel. It uses underscore paths such as `/checkout_sessions` and POST update, unlike UCP's hyphenated paths and PUT update. Preserve its full response schema and error contract. All POSTs require an idempotency key scoped to authenticated identity and endpoint; the pinned contract distinguishes missing key, in-flight processing with Retry-After and conflicting payload. Key lengths differ from the internal API, so an adapter must map identities without truncation/collision. [Pinned OpenAPI](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/blob/7fdd78df677a94dce04c770644b0fbbb1401272b/spec/2026-04-17/openapi/openapi.agentic_checkout.yaml).

The dated repository schema and the public Instant Checkout integration guide differ in status/header examples. The local adapter targets the pinned repository version and records those differences; it must not combine convenient pieces from incompatible revisions. Implementing an open protocol does not enroll the application in ChatGPT Instant Checkout. [Commercial integration guide](https://developers.openai.com/commerce/specs/checkout).

## Retry policy is part of the adapter

| Boundary | Recovery policy |
| --- | --- |
| Internal stateful source | Inquire by original action; confirmed absence permits the same command identity |
| Pinned UCP | Get Checkout with bounded backoff first; only a narrowly permitted identical-body/same-key retry when inquiry cannot establish processing; never repeat completion to poll |
| Shopify Shop client | Its published transaction guidance forbids repeating checkout completion even with the same key; reconcile by reading checkout |
| ACP | Honor its keyed response/in-flight/conflict contract and authoritative retrieval; do not create a replacement purchase to recover uncertainty |

A fresh authenticated HTTP signature/nonce can wrap the same business request/key. Transport replay protection and business idempotency solve different problems. A lost response does not justify switching merchants, instruments, purchase paths or keys. [Shopify transaction guidance](https://github.com/Shopify/shop/blob/70017fb4def4f2fdff8537625a1fb88a338cb0ef/skills/shop/references/transactions.md).

## Compatibility statement required at release

Publish supported version, role, transport, operations, credential/trust profile, test fixtures and exclusions. Local cryptographic verification is not network enrollment. Passing JSON schema is not complete business/protocol conformance. The existing v0.1 app remains unchanged by this research and has not acquired these external capabilities yet.
