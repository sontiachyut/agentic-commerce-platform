# Implementation work packages and release gates

This sequence implements the owner's authorized local scope. Each package adds code, migrations/configuration as necessary, targeted tests, operational documentation and measured evidence. It does not request repeated approval for already authorized work. Public deployment, real payments and paid services remain outside scope.

| Package | Deliverable | Required acceptance gate |
| --- | --- | --- |
| P0 — Constraint correctness | Explicit budget comparison/currency and supported-quantity handling | Exact-boundary, unsupported-currency/quantity and no-purchase clarification tests; quote/acceptance revalidation |
| P1 — Identity boundary | Server-side sessions, OIDC Code + PKCE, revocation and trusted tenant/role mapping | Real local Keycloak browser login/logout, invalid state/nonce/issuer/audience, expired/revoked sessions and cross-tenant tests |
| P2 — MCP transport | SDK 2.3.0 Streamable HTTP, typed tools and OIDC resource security | Black-box modern/legacy clients, metadata discovery, wrong audience/scope, per-request owner isolation, malformed/oversized requests |
| P3 — Evaluation foundation | Versioned original corpus, deterministic oracle, rule and real-model runners, append-only results | Label/schema validation, split-family separation, no oracle leakage, quota-aware restart; publish only executed model cases |
| P4 — Signing and replay | Reviewed JOSE/SD-JWT/RFC 9421 primitives, key/trust configuration and durable nonce ledger | Independent positive fixtures; wrong key/type/audience/nonce/digest/path/body, expiry, unknown constraints and concurrent replay rejected |
| P5 — AP2 direct profile | Merchant-signed checkout, exact consent, closed checkout/payment mandates and verified receipts | SDK/independent fixture interoperability, full backend invariant suite through signed acceptance, stale terms cannot be rebound |
| P6 — AP2 delegated profile | Narrow open-to-closed key binding with explicit count/budget/recurrence policy | Scope narrowing, all constraints, receipt sequencing, held-plus-spent race and revocation tests; unsupported delegation profiles rejected |
| P7 — UCP | Pinned discovery/capability negotiation, compiled schemas, REST checkout and negotiated AP2 extension | Request/response schema fixtures, security-lock downgrade rejection, canonical signature/hash binding, async status and lost-response policy tests |
| P8 — ACP | Pinned five-operation checkout adapter and idempotency/error/version mapping | External schema validation, in-flight/conflict/replay behavior, full authoritative response, retrieval and order-state mapping tests |
| P9 — Recognition integration | Local TAP-style registry/recognition boundary | Fresh transport signature on same business retry, replay/expiry/purpose/destination rejection; no Visa-enrolled claim |
| P10 — Visibility and operators | Workflow metrics, redacted traces, dashboards, tested alerts and bounded recovery tools | Induced source outage/stuck job appears in signals; scraper cannot mutate commerce; no private payloads exported |
| P11 — Packaging and measurement | Local service images/profiles, least-privilege roles, CI and isolated benchmarks | Clean-room setup, migration/restore, shutdown/restart, dependency/container checks, declared workload results |
| P12 — Client experience | Contrast/keyboard/status/error fixes, protocol demo, walkthrough and support matrix | Browser journeys and automated/manual accessibility checks; no speculative success or unsupported compatibility badges |

P1/P2 can progress together after interfaces are defined. Evaluation corpus/runner and accessibility fixes can progress while protocol work is investigated. Existing checkout invariants remain regression gates throughout; adding an adapter cannot bypass exact consent or stock/budget/source checks.

## Decisions frozen by research

- Keep one bounded agent graph and the modular commerce backend; no new broker/Kubernetes requirement.
- Use released SDKs/specifications and offline bundled schemas, with exact source/version manifests.
- Prefer ES256 for AP2 merchant checkout and separate Ed25519 recognition keys.
- Keep local model authentication native and separate from distributable services.
- Treat adapter retry semantics, external checkout status and internal fulfillment/payment facts separately.
- Do not import the AP2 SDK's vulnerable dependency pins or interpret passing schema checks as full conformance.

## Decisions that require a spike or external evidence

1. AP2 integration: the preferred initial route is a reviewed wrapper around the documented low-level SDK primitives, pinned by source revision with explicit modern dependency overrides. The complete candidate set resolved with these overrides. Its high-level presentation facade logs signed artifacts, and two intermediate-hop expectations fail; exclude that facade/general intermediate delegation until reviewed. Application negative fixtures and independent merchant-signature verification remain adoption gates.
2. TAP algorithm spelling and payment-container interoperability: preserve exact signed bytes and require external fixtures before a compatibility claim.
3. UCP/ACP external trust/merchant requirements: the local profile can test configured peers; it cannot assert acceptance by a network or merchant that has not participated.
4. Repeated real-model evaluation size: execute within verified allowance and record all failures/skips; do not invent completion to meet narrative targets.
5. Distribution license and client hosting/provider arrangement: prepare the technical seams, record the owner's commercial decisions when made.

## Completion definition

The local release is complete only when its declared operations, profiles and acceptance tests pass, its setup can be reproduced and its evidence/support matrix agree with the running code. Anything blocked by an external prerequisite is named precisely. Do not call every protocol complete because a schema exists, or every production concern solved because a dashboard starts.
