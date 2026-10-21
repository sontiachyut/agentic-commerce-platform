# Risks and open design decisions

All proposed mechanisms need future tests. No accuracy, cost, scale, adoption, security certification or protocol compliance is claimed.

| Risk | Mitigation / review gate |
| --- | --- |
| Agent confuses intent with consent | Trusted exact human approval and backend policy; AC-01/03/09 |
| Signed permission replay or concurrent overspend | Durable nonce/execution identity plus DB usage reservation; crypto alone insufficient |
| Revocation races an in-flight effect | Acceptance linearization, best-effort undispatched cancel, actual inquiry/compensation; no retroactive no-charge promise |
| Product category/price manipulated | Trusted structured catalog, immutable authoritative quote, exact approval and transactional revalidation |
| Last stock sold twice | Row lock/conditional reservation with order/usage commit; AC-04 |
| Reservation TTL releases possibly dispensed stock | Execution-aware resolution holds and source inquiry; no blind expiry |
| Authorized payment but failed dispense | Avoid capture/cancel supported hold; captured fixture refund by deterministic policy |
| Dispense succeeded, capture fails/unknown | Financial recovery with original identity, no redispense or new unapproved charge |
| Unknown dispensing causes double item/refund | Independent durable dispense receipt/inquiry; unknown is not failed |
| Checkpoint replay repeats business effects | Persisted execution/operation/dispense identities and unique guards independent of graph |
| Stale owner writes saver through another connection | Serialized runner until transactional saver fence/current-owner checks proved; scale-out gated |
| Provider call duplicated/billed after ambiguous timeout | Logical call records, caps, actual/unknown cost accounting; no exactly-once billing promise |
| Model prompt injection / misleading report | Fixed scoped tools, independent policy, source-bound reporting and separate adversarial metrics |
| Protocol/source maturity or licensing overstated | Pin versions, label samples/specs/static tests; no code port or compliance claim |
| Complexity outpaces learning | One user/kiosk/currency/SKU quantity, one agent, exact filtering, simple DB runner first |
| LLM used as load generator | Separate deterministic simulator capacity lane and finite approved model eval |

Open: exact model/provider/prices and embedding need; runtime/dependency/saver versions; whether Celery/Redis earns adoption; exact auth issuer/key rotation in shared deployment; optional protocol target/conformance; source-specific Stripe support; cloud/observability storage/cost/retention; stronger external compensation guarantees. Each belongs to a reviewed milestone. Model/Stripe/cloud calls and deployment remain separately authorized; none occurs in milestone 0.
