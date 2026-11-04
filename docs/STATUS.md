# Implementation status

Updated 2026-11-04. Branch `feat/pharmacy-family-pickup-v1`. Original retail engine is preserved remotely at `4e077c9` and tag `checkpoint/retail-engine-before-pharmacy-2026-11-04`. Current product: **Asterfield Pharmacy — Family Pickup**, a working local synthetic customer/staff candidate, not a publicly deployed or certified pharmacy service.

## Current pharmacy product

- Original pharmacy design/data: four approved family members, fixed existing-refill/OTC saved routines, three fictional locations. No copied retailer branding or live affiliation.
- Text and real local voice input converge on a persisted LangGraph request. A tool-disabled local Codex interpreter returns aliases/limits; deterministic backend code owns eligibility, quote, authority and execution.
- Explicit caregiver access separate from standing/exact purchase permission. Whole-basket nearest eligible location, confirmed synthetic prices, strict/inclusive limits and no automatic medication substitution.
- Atomic inventory/refill/budget holds, immutable quote/access/price snapshots, duplicate acceptance returning one order, and competing refill requests allowing one reservation.
- Source authorization → facility staff review/preparation → capture → ready → customer-code handover. Unknown responses are inquired with stable identities; readiness and collection are never inferred from model prose.
- Customer history, facility-scoped staff queue, revocable sessions/CSRF and optional local OIDC. Sensitive saved-item details are masked from customers after caregiver access is revoked.
- Local whisper.cpp v1.9.5 recognition and **Qwen3-TTS 0.6B CustomVoice 8-bit / MLX Audio 0.6.4** natural speech with supplied Ryan/Aiden presets. No voice cloning, hosted speech API or API key. The optional neural runtime targets Apple Silicon. Its authenticated speech endpoint accepts only an owned request's current state and builds the sentence from backend facts.
- Read-only pharmacy MCP tools: `get_family_regulars`, `get_family_pickup_status`. Preserved protocol adapters are not yet the pharmacy batch execution path.
- Repeatable isolated customer/staff recording, synthetic microphone fixture, neural narration, actual app speech capture and H.264/AAC video rendering. Client demonstration is a mandatory deliverable for this and future product slices. [Walkthrough and capture](pharmacy/demo-guide.md).

## Current verification

- **99 backend tests passed in 29.86 seconds**, including 12 pharmacy cases: full handover, clinical/coverage blockers, concurrent duplicate/competing acceptance, requested budget, revoked access/permission, source response loss, identity/CSRF/cancellation and authoritative speech boundaries.
- **4 pharmacy browser tests passed in 40.3 seconds**: customer/staff collection, strict budget and missing members, five-screen/dialog automated accessibility plus mobile overflow check, and genuine browser recorder → local recognition → workflow → Qwen3-TTS WAV response and browser playback confirmation. These are bounded Chromium checks, not every browser/device or a complete accessibility audit.
- Natural speech smoke: 7.2 seconds of generated Ryan-preset confirmation in 9.047 seconds of synthesis after model loading; a separate local recognizer read back the expected Cedar Square and $40.98 confirmation. This is one sample, not a latency percentile or human naturalness score.
- Updated non-root/read-only-root-filesystem pharmacy container built. Startup, product discovery and bundled recorder asset passed over HTTP. This packaged profile uses the rule baseline without the host speech/Codex environments; no packaged inference or pharmacy-load benchmark is claimed.
- Complete real-Codex client video: **3m57s**, H.264/AAC, real browser capture and neural spoken updates. Two authored cases: $35 budget stop and $40.98 authorized family pickup through staff handover. The independent source journal recorded exactly one authorization, one capture and one handover command for the completed order. Model interpretations took 4.502 and 4.453 seconds; not a latency percentile or accuracy benchmark. [Sanitized evidence](../results/pharmacy/2026-11-04-local.json).
- The updated migration downgrade/upgrade/metadata checks and two-database restore rehearsal passed with matching fingerprints (29 commerce tables/826 rows; 2 source tables/48 rows at that snapshot). The preserved retail browser suite passed all six cases in 12.7 seconds.

## Preserved retail interoperability foundation

The pre-pivot branch/tag has 87 backend/six browser tests and passing remote CI. It retains exact/delegated purchasing, atomic stock/budget holds, independent source inquiry/recovery, Keycloak Code + PKCE, official MCP SDK 2.3.0 transport, a narrow AP2 ES256 profile, local RFC 9421 Ed25519 TAP-style recognition and pinned UCP/ACP five-operation synthetic contract adapters. External enrollment/conformance and shopper routing remain explicit boundaries. [Support matrix](protocol-support.md).

## Measured decisions

- Original 100-case synthetic rule-baseline corpus: **100/100 passed**. Twenty grouped families; not representative real-world accuracy.
- First real-Codex three-case batch: **1/3 passed**; two cases returned an empty kiosk and safely stopped. Those failures remain recorded.
- After making the trusted default kiosk explicit, the same three regression cases: **3/3 passed**, 20.467 seconds in aggregate decision time. This is a small regression sample, no longer an unseen holdout claim.
- Workflow ordering is controlled by the graph; no model tool-selection accuracy percentage is claimed. Evaluation sessions reserve the normal durable model-call allowance without creating purchase jobs.

## Remaining gates

1. Complete broader real-model adversarial/held-out evaluation, microphone/accent/device coverage, streamed speech latency work, workload benchmarks and the new pharmacy monitoring/alert exercise. Current local acceptance is not a production capacity or clinical-safety claim.
2. Pharmacy batch quotes do not yet use the preserved AP2/TAP-style/UCP/ACP adapters. Real pharmacy, payer, merchant and payment contracts and independent peer conformance remain separate work. Native OIDC MCP client-browser authorization is also outstanding.
3. Complete production identity/administration, secret/key lifecycle, audit retention, public abuse controls, operational SLOs and a broader security/accessibility review before a public service. Identity-provider/configuration recovery has not been rehearsed.
4. Choose a distribution license and commercial support model. A local Codex subscription is not a hosted customer inference API. Native CarPlay requires its own entitled native client and approval. Public hosting, billable services and real transactions are not enabled.

No Java payment platform, paid model API, cloud account, Kafka or Redis is required for this local product. Historical interview narrative metrics and reference research are not implementation evidence.
