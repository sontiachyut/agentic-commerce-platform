# Asterfield Pharmacy — Family Pickup

Decision: 2026-11-04. This original fictional brand, interface and synthetic dataset replace the virtual-kiosk use case as the default product. The previous implementation is preserved at GitHub commit 4e077c9 and the checkpoint/retail-engine-before-pharmacy-2026-11-04 tag. No CVS/Walmart branding, copied layouts, proprietary integrations or affiliation claims.

## Product and larger vision

A busy household organizer wants one reliable family pickup instead of separately finding each person's regular items, checking locations and paying. The standalone product connects customer requests to a pharmacy team's actual queue and confirmed pickup state. It is independently useful to a pharmacy client and forms the order/coordination component of a later voice-first, in-car family assistant.

The primary scenario is an authenticated customer leaving work: “Order the regular items for Dad, Mom, my sister and me from the nearest pharmacy to home. You can pay up to fifty dollars.” The system retrieves authorized saved routines, checks prescription eligibility and final prices, selects the nearest open location able to supply the entire basket, checks a previously configured purchasing permission and places one order. Pharmacy staff review/prepare it; the customer receives a separate ready notification and pickup reference. The voice confirmation names the location and truthful current status, without reading relatives' medication names by default.

“Under $50” is strict; “up to $50” includes $50. The user's large vision used both formulations. The implementation preserves whichever the actual request says; the standard demonstration uses “up to $50.” It never expands a lower request limit to the standing permission's maximum.

## First complete product

- Customer and pharmacy staff experiences, supported by persistent APIs and a durable workflow.
- Synthetic household with self, father, mother and adult sister. Approved caregiver access is explicit and independently revocable; family relationship alone gives no medical-data access.
- Saved, fixed regular-item packages covering existing prescription refills and OTC/personal-care items. No new prescribing, dose changes, medical advice or automatic therapeutic substitution.
- A prescription eligibility/pricing port with reproducible synthetic responses: ready to request, too soon, no refills, coverage unresolved, caregiver access revoked. Final confirmed copay and OTC totals determine the basket limit. Unresolved coverage is a blocker, not an invented price.
- Three fictional locations with hours, synthetic coordinates and location inventory. Choose nearest to the saved home among locations that can fulfill the complete eligible basket. Straight-line distance is labeled; no live traffic/route ETA claim.
- Immutable multi-item quote, permission scope and exact limits; atomic inventory/refill/budget holds; durable idempotency and independent synthetic payment inquiry.
- Accepted order, staff review/preparation, payment/source confirmation, ready for pickup and collected states kept distinct. No success message before its corresponding fact exists.
- Real local speech recognition and spoken responses alongside a keyboard interface. Recording controls, ambiguous requests and unavailable microphone/recognizer have clear fallbacks. Natural local Qwen3-TTS responses replace the system voice; written status remains available when speech cannot run. No paid speech/model API; signed-in Codex remains local and quota bounded.
- Order history, actionable blocker explanation and staff status changes with auditability. Demonstrate an uncertain payment without a duplicate charge.

## Modular boundaries

Identity/caregiver consent → saved routine and prescription eligibility → location/availability → quote and purchasing permission → order/payment orchestration → staff fulfillment and pickup → notification. Voice/text are interfaces to these services, not authorities. Keep adapters explicit so a future client pharmacy system, supported inference provider, notification channel and native CarPlay surface can replace synthetic implementations.

## Completion means a client can see it work

The product is not complete at screenshots or generated code. Deliver a repeatable seed/scenario, meaningful backend and browser checks, and a recorded client demonstration showing the running customer and staff applications. Include actual voice input through recognition, the grounded basket/location/limit, order placement, staff progression and customer confirmation. Include one short blocked or recovered case. Deliver a playable video plus a clear script and exact reproducibility notes. State synthetic services and prerecorded demo speech where used. Do not imply a real CVS/Walmart integration, live insurance adjudication, real payment or approved CarPlay application.

## Later products, not hidden requirements

Native CarPlay; real pharmacy/e-prescribing and payer integrations; prescriber outreach; multi-store split orders; live navigation; clinical decision support; real-money processing; public customer hosting. These need their own contracts, evidence and approvals. Build the current component so those can connect, without simulating their completion in the first product.
