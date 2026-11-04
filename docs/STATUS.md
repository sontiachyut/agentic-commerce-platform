# Implementation status

Updated 2026-11-04. Working branch: `feat/interop-hardening-v2`. This is a **local synthetic interoperability candidate**, not a publicly deployed or commercially certified service.

## Product scope

The implemented application remains general retail: one virtual kiosk, one item, USD and synthetic source effects. The owner has now raised **pharmacy facilities and customers** as the intended domain. Whether the first pharmacy workflow is OTC/personal-care ordering and pickup or prescription/insurance coordination is pending clarification. Neither pharmacy-specific workflow has been built. Shared commerce infrastructure is reusable; changing labels alone would not provide those workflows.

## Implemented and verified

- Stateful LangGraph shopping, exact consent and delegated permissions; atomic stock/budget holds; independent authorization/dispense/capture/cancel/refund simulator; durable inquiry/recovery.
- Strict/inclusive budget comparisons preserved through interpretation, catalog selection, quote and acceptance. Unsupported currency/quantity requests stop for clarification.
- Revocable opaque browser sessions, CSRF and an optional local Keycloak Code + PKCE login. Trusted issuer/key/audience/nonce/state verification and provisioned tenant/role membership; provider tokens encrypted at rest.
- Official MCP Python SDK 2.3.0 Streamable HTTP with structured read-only tools. Real HTTP modern and legacy clients, metadata discovery, owner isolation and authorization/body-limit checks passed.
- Narrow AP2 v0.2 ES256 direct and one-hop delegated profiles using the pinned SDK primitives. Independent merchant JWT verification, exact hashes and current backend authority checks. Signed artifacts retained encrypted; receipts require confirmed source outcomes. Human-approved API/browser purchases pass through this profile.
- RFC 9421 Ed25519 local recognition with TAP-style purpose tags and a durable concurrent replay ledger. No Visa registry enrollment is claimed.
- Pinned UCP/ACP outbound five-operation adapters, offline bundled official schemas/licenses/hashes, JCS detached merchant-authorization helpers and encrypted durable command journals. Contract tests exercise synthetic peers, uncertain completion inquiry and long ACP keys. **These adapters are not live merchant connections or shopper-graph routing.**
- Aggregate workflow/queue/source metrics with a separate read-only scrape credential. Dashboard and alert definitions exist; a running monitoring stack/alert exercise is not yet verified.
- Separate non-administrative application/source database roles. A built non-root, read-only-root-filesystem container profile completed a real HTTP synthetic purchase with response-loss recovery and duplicate execution returning the same ID.

Latest complete backend run: **87 passed in 17.36 seconds**. Six browser tests passed, including OIDC login/revocation, purchase/recovery, mobile layout and automated WCAG checks on four shopper screens. Python advisory audit reported no known vulnerabilities in installed third-party dependencies; the local application itself is not on PyPI and was skipped. These are bounded local checks, not production certification or a complete accessibility/security audit.

## Measured decisions

- Original 100-case synthetic rule-baseline corpus: **100/100 passed**. Twenty grouped families; not representative real-world accuracy.
- First real-Codex three-case batch: **1/3 passed**; two cases returned an empty kiosk and safely stopped. Those failures remain recorded.
- After making the trusted default kiosk explicit, the same three regression cases: **3/3 passed**, 20.467 seconds in aggregate decision time. This is a small regression sample, no longer an unseen holdout claim.
- Workflow ordering is controlled by the graph; no model tool-selection accuracy percentage is claimed. Evaluation sessions reserve the normal durable model-call allowance without creating purchase jobs.

## Remaining work

1. Select and implement the pharmacy product workflow, its staff/customer roles and correct fulfillment states.
2. Complete native OIDC MCP-client browser authorization and broader protocol negative/conformance fixtures. Local protocol tests do not establish external wallet/merchant/Visa acceptance.
3. Connect selected external merchant adapters to an authorized shopper workflow, including version/identity negotiation and end-to-end independent peer testing. Preserve current price/consent/source invariants.
4. Finish monitoring deployment and alert exercises, isolated workload benchmarks and broader accessibility/security review. The latest migration downgrade/upgrade and two-database restore rehearsal passed; identity-provider/configuration recovery still needs its own exercise. Container imports required a documented portable OpenSSL CPU profile on this older Docker Desktop ARM host.
5. Choose a distribution license and commercial support model. Public hosting, supported hosted inference, actual provider onboarding and real transactions require separate resources/authorization; they are not enabled.

No Java payment platform, paid model API, cloud account, Kafka, Redis or public deployment is required for the current local candidate. Do not treat historical interview narrative metrics or completed research as implementation evidence.

See [local setup](../README.md), [identity/packaging](local-identity-and-packaging.md), [decision ADR](adr/009-local-identity-and-signed-profiles.md), [research backlog](research/06-implementation-backlog.md) and [verification](verification-report.md).
