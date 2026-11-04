# HTTP API — v0.1

Interactive reference: `http://127.0.0.1:8510/docs`. Machine-readable contract: [OpenAPI snapshot](openapi.json). Regenerate the snapshot after API schema changes; do not edit it by hand.

## Authentication and mutations

`POST /api/v1/auth/demo` with `{"persona":"alex"}` establishes an eight-hour signed HttpOnly SameSite=Strict synthetic session and returns a CSRF token. Supported personas are alex, sam and operator. This is only a local demonstration identity boundary.

All subsequent mutations require `X-CSRF-Token` from the session response when using its cookie. Origin and host are checked; cross-user resources are denied. `/api/v1/auth/me` restores the current actor/token after reload. Logout deletes the browser cookie; production session revocation is not implemented.

Amounts are integer USD minor units: `350` means $3.50. Clients never supply authoritative final prices. User/tenant identity is derived from the signed session, not request bodies. JSON mutation bodies are bounded to 64 KiB; shopping requests to 2,000 characters. Resource IDs and model values are untrusted inputs.

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

## MCP subset

POST `/mcp` uses the same authenticated boundary and CSRF rules. It accepts JSON-RPC initialize, ping, tools/list, tools/call and initialized notification. Tools are `search_products` and `get_purchase_status`; neither can approve or mutate a purchase. Protocol versions 2025-06-18 and 2025-03-26 are recognized for this subset. Full transport/session/SSE interoperability is outstanding; see [protocol support](protocol-support.md).

## Failures

Business errors use `{"error":{"code":"...","message":"..."}}` with an appropriate HTTP status; request IDs appear where available. Validation errors list field paths without echoing rejected inputs. Examples include `AUTHORITY_REQUIRED`, `QUOTE_EXPIRED`, `PRICE_CHANGED`, `OUT_OF_STOCK`, `GRANT_INACTIVE`, `GRANT_EXHAUSTED`, `GRANT_SCOPE`, `ADMISSION_LIMIT` and `IDEMPOTENCY_CONFLICT`.

Never interpret a transport timeout as a declined purchase. Retry with the same idempotency identity or query the existing resource. Do not create a new request key to work around an uncertain result. A source conflict or unresolved effect may require operator review, not another charge.
