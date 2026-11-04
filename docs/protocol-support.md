# Protocol support and conformance boundaries

The product target includes AP2 purchase authority, Visa TAP agent verification, UCP/ACP commerce boundaries and MCP tool access. These responsibilities remain separate. A signed agent request does not itself authorize spending; successful checkout acceptance does not prove a payment or delivery completed.

## Current release

| Area | Implemented now | Remaining before an external compatibility claim |
| --- | --- | --- |
| Exact purchase authority | Immutable quote digest, authenticated approval, scope, expiry, consumed receipt and delegated budget holds | AP2 wire encoding, SD-JWT/disclosure validation, external issuer/key trust and pinned conformance fixtures |
| Agent identity and request binding | Local authenticated actor context; fixed shopping-agent identity; owner/merchant/product checks | Visa TAP HTTP signature profile, enrolled registry trust, audience/path/time/replay tests against the pinned specification |
| Merchant checkout | Typed internal catalog/quote/execution/status contracts and independent payment port | Versioned UCP/ACP adapters, capability negotiation and official schema/fixture validation |
| MCP | Authenticated read-only JSON-RPC tools at `/mcp`: initialize, ping, tools/list and tools/call | Complete Streamable HTTP transport/session behavior, broader SDK interoperability tests and version policy |
| Payments | Stateful synthetic authorization/capture/cancel/refund source, stable command IDs and inquiry | Actual PSP onboarding, payment-instrument handling, provider contract tests and applicable compliance review |

The v0.1 application must not display AP2-compliant, TAP-certified, UCP-compatible or ACP-compatible badges. Its internal contracts are not relabeled external protocols. The MCP endpoint implements a deliberately small tested subset rather than claiming complete protocol conformance.

## Integration sequence

1. Freeze one external specification version and inspect its official schemas, security requirements, examples and licenses.
2. Create a typed adapter around the stable internal checkout model; do not move budget or inventory authority into protocol parsing.
3. Validate positive examples, invalid signatures/keys, wrong audience, expiry, replay, unsupported version, inconsistent amounts and conflicting statuses.
4. Confirm that the same internal policy and source-state regression suite passes through the adapter.
5. Publish a precise compatibility statement covering the tested operations/version and excluded features.

AP2's closed checkout mandate uses a merchant-signed checkout and a hash bound to that signed object. A JSON hash of our local quote alone is not the AP2 SD-JWT protocol. UCP/ACP merchant integration similarly requires more than exposing an endpoint named checkout.

Pinned research and exact upstream paths are in [reference analysis](reference-analysis.md). This implementation has not copied an upstream commerce engine or private payment reference. Public source research is evidence for design choices, not inherited production guarantees.
