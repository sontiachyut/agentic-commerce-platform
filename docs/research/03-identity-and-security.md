# Identity, cryptography and tool security

## Identity separation

Treat browser identity, agent recognition, user purchasing authority, merchant identity and provider/service credentials as separate boundaries. Visa TAP authenticates a recognized agent request; AP2 carries purchasing authority; OAuth protects application/tool resources; none proves that an order was paid or delivered.

Use local Keycloak and Authorization Code with PKCE S256 for the next authenticated demonstration. The backend is the OIDC client/BFF. Store opaque browser sessions and login state on the server; keep tokens out of localStorage, URLs, model context and ordinary logs. Validate state, nonce, issuer, audience, expiry, signature and authorized party as applicable. Consume login state once; use fixed redirects. Avoid implicit/password grants. [Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers), [OAuth Security BCP](https://www.rfc-editor.org/rfc/rfc9700.html), [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html).

Map `(issuer, subject)` to internal identity. Tenant membership and operator roles come from validated, administratively controlled membership/claims, never a client-supplied tenant field or an email naming convention. Browser sessions need revocation, expiry and CSRF. Logout must invalidate server authority, not only delete a cookie. The model/worker never receives a user refresh token.

## MCP implementation

Use MCP Python SDK 2.3.0 with its real Streamable HTTP handler. Modern requests and legacy negotiation are tested independently. The host FastAPI lifespan must enter the SDK session manager; mounted ASGI lifespans do not start themselves. Bound body size, timeouts and concurrency. Configure Host/Origin allowlists and required browser protocol headers deliberately. [SDK ASGI integration](https://py.sdk.modelcontextprotocol.io/run/asgi/).

Use TokenVerifier/AuthSettings, resource audience validation, scoped access and protected-resource discovery for OIDC mode. Read the per-request authenticated subject/claims, not the OAuth client's application ID, as the human owner. In-memory SDK tests bypass transport authentication, so black-box HTTP tests are required. Stateless MCP transport does not remove the application's persisted agent sessions/checkpoints. [SDK resource-server authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/).

Initial tools remain read-only catalog/status. A later prepare/request-execution tool still needs deterministic backend authority; no tool may issue human approval or raw payment credentials. Model-visible schemas must not let callers override actor, tenant or verified identity. Use typed output models: an unparameterized dict in the SDK spike produced text without structured output, so explicitly require structured output and validate its schema.

## TAP-style recognition profile

The Visa merchant specification describes signed authority/path, created/expires, key ID, algorithm, tag and nonce. Its prose limits validity to eight minutes; examples show a longer interval, so use the stricter prose limit for the local profile. Browsing and payment tags are distinct. Verify the expected tag and required covered components, not simply any valid signature. [Merchant specification](https://developer.visa.com/docs/trusted-agent-protocol/trusted-agent-protocol-specifications).

For consequential API requests, additionally cover method, query, content type, content digest and idempotency identity. Validate the digest against actual raw bytes. Resolve keys only from an allowlisted registry/configured trusted issuer; do not fetch arbitrary model/header URLs. A cached key needs validity/rotation policy. Persist nonce consumption atomically with a unique issuer/key/nonce identity. Reject unknown key, wrong destination, wrong purpose, expiry, future timestamps and replay.

Visa examples use an algorithm spelling that differs in case from the RFC registry spelling. Preserve signed bytes and handle only explicitly reviewed algorithm aliases; do not silently rewrite the signed header or claim interoperability until external vectors establish it. Use reviewed RFC 9421 libraries for canonicalization and Ed25519 verification. The current signature spike verifies the RFC behavior, not Visa enrollment or payment-container compatibility. [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html), [RFC 9530](https://www.rfc-editor.org/rfc/rfc9530.html).

## Cryptographic integration gates

- Explicit issuer/key/algorithm allowlists; reject self-supplied trust roots and unsupported key use.
- Strict structured-field and JSON parsing; reject duplicate/ambiguous claims and unsupported constraints where authorization meaning is affected.
- Verify signatures before treating claims as trusted; independently verify expected checkout and mandate/receipt hashes.
- Bound chain length, disclosure count, token bytes and nesting. Require meaningful local lifetimes and expected challenges for the supported profile.
- Test disclosure tampering, missing required disclosure, duplicate disclosure, chain/key substitution, wrong type/audience/nonce, stale price, unsupported algorithm and forged receipt.
- Keep private signing material outside the LLM runtime and tool arguments. Use distinct key purposes; publish only public keys. Historical receipt verification and current authorization have different time/rotation policies.

AP2's dependency pins cannot be adopted unchanged: isolated auditing flagged its pinned cryptography, jwcrypto and pytest versions. Modern candidate dependencies resolved and audited without known findings at research time. AP2's two failing intermediate-hop audience/nonce tests also reproduce under the original dependency pins, so they are not explained by dependency modernization. They are a contract inconsistency to investigate, not a demonstrated exploit or a reason to disable final-hop checks.

The high-level SDK presentation facade also appends the full `pres_jwt` to a package-relative log file. That behavior conflicts with this application's protected-artifact/telemetry boundary. Prefer its documented low-level primitives behind a reviewed application wrapper, or an explicit attributed patch; do not solve this by silently accepting token-bearing logs or broadly monkey-patching unrelated SDK behavior.

## Local code review findings to address

The current CSRF exemption checks the presence of an Authorization header, rather than exclusively the successfully authenticated bearer path. Other controls mitigate exposure, but the refactor must make the exemption depend on validated auth method. Replace private request-body mutation middleware with a documented ASGI body-boundary implementation that remains compatible with SDK HTTP handling.

Test cross-user and cross-tenant session/quote/approval/grant/execution/MCP access, duplicate nonce races across processes, revoked browser sessions, invalid issuer/audience/roles and permission changes during checkout. Use least-privilege database/service roles and keep migration ownership separate from runtime. Do not claim universal injection resistance: a malicious model proposal can be blocked while still failing the user's task.
