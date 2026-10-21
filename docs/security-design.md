# Proposed security, authorization and audit boundaries

No security implementation exists. Synthetic-only simulation reduces exposure but does not establish security or protocol compliance. Threat model includes accidental model mistakes, malicious merchant/product content, replaying clients, stale workers and compromised low-privilege tool context.

## Trust map

User identity and trusted approval surface create permission. Agent identity authenticates which software is acting; it does not prove user spending consent. Merchant identity identifies the payee/kiosk; display name/URL from content is not sufficient. Commerce policy binds all three plus exact terms. Java service identity enforces permitted merchant/payment operations separately. Dispenser credentials control only the simulated fulfillment boundary.

Validate token issuer/audience/expiry/algorithm and object ownership at every API, tool, grant, checkpoint and report read/write. Trusted context injects user/agent IDs; reject arguments attempting to override them. One-user MVP still includes scope fields and negative tests; do not remove authorization because a demo has one account.

## Least privilege and financial tools

Agent can search, quote, request approval, request execution of an already authorized checkout, and read scoped status. It cannot access approval signer, private keys/payment credentials, arbitrary network URLs, SQL/shell/browser/code execution, raw payment/dispense endpoints, policy administration or unrestricted refunds. Coordinator identity may authorize/capture/cancel/refund only original linked operations according to versioned deterministic policy and the trusted purchase binding.

Use separate user, graph runner, coordinator, compensator, webhook ingestor and read/audit scopes where boundaries require them. Do not give a broad provider key to the model or describe an app wrapper as equivalent to provider-enforced read-only credentials. No actual credentials or keys are created now.

## Prompt injection and output handling

Catalog descriptions, tool errors, retrieved docs, merchant responses and model output are untrusted. Typed structured fields and source labels constrain interpretation; application dispatch independently authorizes every action. Bound query/output sizes, allowlist endpoints/merchants, escape rendered HTML/links, and do not execute model-produced JSON or URLs as instructions. JSON schema compliance is not semantic correctness or permission.

An attacker might still influence product ranking or final prose despite no financial effect. Evaluate misleading recommendations, data disclosure and fabricated outcomes separately from blocked purchase attempts. Ground final response in typed authoritative states and deny unsupported “paid/dispensed/refunded” claims.

## Replay, tampering and concurrent authority

Server-side immutable quote/version/hash and receipt/grant identity; nonce/execution unique constraints; semantic idempotency; durable usage reservation; current revocation/expiry/version checks. A valid signature or fresh timestamp alone does not consume a nonce or budget. Established crypto libraries plus issuer/audience/algorithm/key trust are required if signed boundary tokens are added. Key rotation and retention must preserve verifiability of recorded past approvals without granting new use.

Revocation is linearized at deterministic execution acceptance with explicit in-flight limitations; see [authority design](authorization-and-mandates.md). Locks/leases, checkpoints and event delivery are not substitute permission checks.

## Sensitive data and observability

No PAN/CVC, real account/payment records or employer material. Use synthetic product/payment refs. Redact credentials/auth headers and private grant/receipt material before model/tracing. Langfuse and OTel store minimum metadata/digests by default; full prompt capture requires an explicit synthetic-only retention/access decision. Checkpoints can contain sensitive excerpts, so retention applies there too.

Audit approvals/denials, grant version/revocation, quote digest, policy reasons, execution/stock usage, service actions, source observations, recovery and compensation, with actor/correlation/time. Preserve failed/unknown actions and report revisions; do not overwrite history to hide an uncertain outcome. Metrics avoid per-order labels; trace/log IDs stay scoped and access controlled.

## Future validation gates

AC-06/09/10 plus negative tests for cross-user refs, unauthorized signing/refund/dispense, malformed payloads, stale review, nonce replay, wrong key/audience, price tamper, budget/stock race, denial partial commits and stale owner/checkpoint writes. Access rules must be tested at backend, not just hidden UI buttons. Networked/shared deployment requires TLS, secret storage, rate/admission bounds, dependency/version review and cost approval before exposure.

Optional TAP/AP2/UCP/ACP adapters need pinned conformance requirements and negative evidence before compatibility claims. Kubernetes isolation/OpenFGA/MCP are later choices; none replaces deterministic permission and effect identity.
