# HTTP API — pharmacy candidate and preserved retail engine

Interactive reference: `http://127.0.0.1:8510/docs`. Machine-readable contract: [OpenAPI snapshot](openapi.json). Regenerate the snapshot after API schema changes; do not edit it by hand.

## Authentication and mutations

The default product mode is pharmacy; `GET /api/v1/product` describes it. Optional local OIDC uses Code + PKCE and provisioned tenant/role membership. Demo mode uses `POST /api/v1/auth/demo` with persona alex, sam or operator. Both establish an opaque revocable HttpOnly SameSite=Strict server-side session and return a CSRF token. `/api/v1/auth/me` restores the actor/CSRF token. Logout revokes the session and clears its cookie.

Mutations using cookies require `X-CSRF-Token`; origin/host and authenticated resource scope are checked. Identity is not accepted from request bodies. Most bodies are bounded to 64 KiB; the voice-transcription endpoint separately allows a validated PCM WAV of up to 45 seconds/1,440,044 bytes. Amounts are integer USD minor units. A 202 response means queued/accepted for processing, not paid or handed over.

## Pharmacy workflow

| Method / path | Meaning |
| --- | --- |
| GET `/api/v1/pharmacy/workspace` | Authorized customer household/history or facility-scoped staff workspace |
| GET `/api/v1/pharmacy/voice` | Local recognition and natural-synthesis availability; no native CarPlay claim |
| POST `/api/v1/pharmacy/voice/transcribe` | Authenticated customer PCM WAV recognition, not purchase approval |
| POST `/api/v1/pharmacy/permissions` | Explicit saved-member permission with per-order/total/count/expiry limits |
| DELETE `/api/v1/pharmacy/permissions/{id}` | Revoke future use and prevent a new staff capture confirmation |
| POST `/api/v1/pharmacy/requests` | Idempotent text/voice request; body `text`, `channel`; Idempotency-Key required |
| GET `/api/v1/pharmacy/requests/{id}` | Owned request, quote, order/source facts and event history |
| POST `/api/v1/pharmacy/requests/{id}/approval` | Exact current `quote_digest`; does not accept model-created authority |
| POST `/api/v1/pharmacy/requests/{id}/cancel` | Cancel before pharmacy submission; submitted orders require staff reconciliation |
| POST `/api/v1/pharmacy/requests/{id}/speech` | Current `state` only; backend constructs the spoken sentence; no arbitrary client prose |
| GET `/api/v1/pharmacy/staff` | Assigned-facility queue |
| POST `/api/v1/pharmacy/staff/orders/{id}` | ready with preparation confirmation, reject before capture, or collect with customer pickup code |

Natural speech returns a bounded base64 WAV, engine/voice, duration and synthesis timing. This optional Apple Silicon Qwen3-TTS profile runs locally in an isolated process; failure leaves the written status available. Speech endpoints retain ownership, role and CSRF controls. A client cannot supply a success sentence or speak a different state from the recorded request.

Requests use QUEUED/PLANNING, NEEDS_INPUT, BLOCKED/BUDGET_EXCEEDED, AWAITING_APPROVAL, ORDERING/ORDERED, READY_FOR_PICKUP and PICKED_UP, with cancellation/review/model-unavailable paths. Payment authorization is not capture; readiness is not physical handover. See [pharmacy architecture](pharmacy/architecture.md).

## Preserved retail-mode API

The following paths are retained for `COMMERCE_PRODUCT_MODE=retail` and return 404 in pharmacy mode. Their one-item virtual-kiosk scenario is historical, rather than the current default customer product.

## Workflow

| Method / path | Meaning |
| --- | --- |
| GET `/api/v1/catalog?kiosk_id=kiosk-a` | Read available products |
| POST `/api/v1/sessions` | Submit `request` and optional `grant_id`; returns 202 and a session ID |
| GET `/api/v1/sessions/{id}` | Read agent progress, exact quote, source outcome and activity |
| GET `/api/v1/sessions` | Read the owner's latest 40 sessions |
| POST `/api/v1/sessions/{id}/retry` | Explicitly re-enqueue the existing graph; does not grant approval |
| POST `/api/v1/quotes/{id}/approval` | Approve the exact `quote_digest` as the authenticated owner |
| POST `/api/v1/executions` | Atomically accept an authorized quote and schedule execution |
| GET `/api/v1/executions/{id}` | Read confirmed payment, fulfillment and compensation facts |
| POST / GET `/api/v1/grants` | Create/read constrained delegated purchase permissions |
| POST `/api/v1/grants/{id}/revoke` | Revoke future acceptance under a grant |

Session and execution creation require an `Idempotency-Key` of 8–100 characters. Same session request/key returns its original ID; changing its semantics conflicts. The unique quote-to-execution identity also prevents a second purchase when a client changes a transport key. The original authority binding must still match.

Human-approved acceptance body:

```json
{
  "quote_id": "<backend quote ID>",
  "approval_id": "<trusted approval receipt ID>",
  "fault_profile": "none"
}
```

Delegated acceptance uses `grant_id` plus its current `grant_version` instead of `approval_id`. The graph's delegated path derives these from the selected existing grant; the model cannot create a grant. Grant revocation prevents new acceptance but does not undo previously accepted external effects.

202 means accepted for processing, not paid or delivered. A successful purchase requires `state=COMPLETED`, `payment_state=CAPTURED` and `fulfillment_state=DISPENSED`. Read `outcome` for the backend-owned classification. Unknown, canceled, refunded and recovery-required states remain distinct.

## Operators and source adapter

Operator-only endpoints: GET `/api/v1/operator/overview`; POST `/api/v1/operator/products/{id}/price`; POST `/api/v1/operator/executions/{id}/retry`; GET `/metrics`. Retry is limited to a resolved synthetic source-outage profile and preserves command identity. It is not a generic override of financial policy.

The source simulator has a separate API/database on port 8511. Its `/v1/commands` and `/v1/commands/{execution}/{action}` endpoints require the application service token. It commits each effect independently and can lose a response after commit. It is not a client-facing approval route or a payment gateway implementation.

## MCP transport

The official SDK 2.3.0 exposes authenticated read-only Streamable HTTP tools. Pharmacy mode provides `get_family_regulars` and `get_family_pickup_status`; retail mode provides `search_products` and `get_purchase_status`. Neither mode exposes approval, permission creation, payment or handover tools. Modern/legacy HTTP and metadata discovery are tested for the preserved transport; native OIDC client-browser authorization remains a separate integration exercise. [Exact support matrix](protocol-support.md).

## Failures

Business errors use `{"error":{"code":"...","message":"..."}}` with an appropriate HTTP status; request IDs appear where available. Validation errors list field paths without echoing rejected inputs. Examples include `AUTHORITY_REQUIRED`, `QUOTE_EXPIRED`, `PRICE_CHANGED`, `OUT_OF_STOCK`, `GRANT_INACTIVE`, `GRANT_EXHAUSTED`, `GRANT_SCOPE`, `ADMISSION_LIMIT` and `IDEMPOTENCY_CONFLICT`.

Never interpret a transport timeout as a declined purchase. Retry with the same idempotency identity or query the existing resource. Do not create a new request key to work around an uncertain result. A source conflict or unresolved effect may require operator review, not another charge.


## Local hardening candidate

Browser cookies now contain opaque references to revocable server-side sessions. GET /api/v1/auth/config selects demo or OIDC login. OIDC starts at GET /api/v1/auth/login and returns to the fixed /api/v1/auth/callback; the browser never receives provider tokens. The existing exact approval endpoint also creates a signed local AP2 envelope, and matching execution requests verify that envelope before acceptance. GET /api/v1/protocols describes the local profiles; scoped envelope/receipt retrieval is under /api/v1/protocols/ap2/envelopes/{id}. Receipts remain pending until both authoritative synthetic source outcomes are confirmed.

MCP uses official SDK Streamable HTTP and bearer authorization, not browser-cookie authority. Its protected-resource metadata is /.well-known/oauth-protected-resource/mcp. GET /internal/metrics accepts only the separately configured scrape bearer credential; that credential grants no commerce or operator permissions.
