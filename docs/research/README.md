# Implementation research dossier

Research date: **2026-11-04**. Baseline application: v0.1, commit `0857b87`. This dossier supports the authorized interoperability and hardening build. It is an engineering research record, not a claim that the next release has been implemented or certified.

Read in this order:

1. [Product and system boundaries](01-product-and-boundaries.md)
2. [Protocol contracts and compatibility](02-protocol-contracts.md)
3. [Identity, cryptography and tool security](03-identity-and-security.md)
4. [Evaluation and reliability](04-evaluation-and-reliability.md)
5. [Platform, operations and accessibility](05-platform-and-operations.md)
6. [Implementation work packages](06-implementation-backlog.md)
7. [Executed experiments](07-experiments.md)

The [source lock](sources.lock.json) records exact revisions, selected inspected files, hashes and primary-document URLs. Full upstream research snapshots and raw experiment output remain private and ignored. [Earlier reference analysis](../reference-analysis.md) preserves the original commerce and Shopify investigation. No private payment reference is part of this dossier or public implementation.

## Findings that change the build

| Finding | Consequence |
| --- | --- |
| MCP Python SDK 2.3.0 supports modern 2026-07-28 discovery and legacy negotiation | Use the released SDK and test both modes; do not extend the hand-written JSON-RPC subset |
| AP2 binds mandates to merchant-signed checkout bytes | Local JSON quote hashing remains an internal invariant; add distinct signed external artifacts and verify their chain/bindings |
| UCP's AP2 extension uses detached JWS over canonical checkout data | Reconstruct the signed compact JWT correctly; do not hash the detached signature string or reuse a different serialization |
| UCP and Shopify have different uncertain-completion retry rules | Recovery behavior belongs to each adapter; no universal retry policy across merchants |
| AP2 SDK tests show two intermediate-hop expectation failures | Investigate and constrain the supported profile; never substitute an SDK method name for verified security behavior |
| Published AP2 dependency pins have advisory findings | Do not add the pinned upstream dependency set to the application; use audited compatible dependencies and re-run interoperability tests |
| Current intent loses strict/inclusive budget semantics | Fix this before publishing model-quality scores or connecting external checkout |
| Current screens have automated contrast failures | Fix and retest before the next client-demonstration acceptance gate |

## Research method and limits

Official specifications were checked against pinned SDK/schema/source releases and actual tests. Research includes AP2, MCP, UCP, ACP, Shopify Shop, RFCs, identity-provider documentation, reliability/evaluation implementations and accessibility standards. Selection favors the parts that affect this product's trust and transaction boundaries.

Executed checks include upstream AP2 tests under two dependency sets, UCP schema/documentation validation, an authenticated real-HTTP MCP spike, HTTP signature tamper cases, dependency resolution/auditing and automated accessibility checks against the running application. Exact results are in the experiment record. These checks do not establish external merchant enrollment, payment-network trust, public deployment, market demand or full protocol conformance.

Research is sufficient to define the local implementation sequence, not to promise that every external integration is settled. Open issues have explicit tests or external prerequisites. No real payments, merchant checkout, new cloud resources or paid model APIs were used in this research.
