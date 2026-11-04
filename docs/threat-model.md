# Threat model — local release

## Assets and trust boundaries

Protect exact user consent, remaining delegated spending authority, inventory, order identity, payment/fulfillment facts, authentication/service secrets and model allowance. Trust the authenticated application boundary and its own database, not model prose, merchant descriptions, client-supplied amounts or arbitrary source JSON.

This is a loopback-only synthetic demonstration, not a hardened multi-tenant SaaS. Demo persona selection is not enterprise authentication. `demo_mode=false` intentionally refuses startup until that production identity boundary exists.

| Threat | Implemented control | Verification |
| --- | --- | --- |
| Model attempts to approve or pay directly | No approval/payment authority in planner; MCP tools are read-only; backend reloads authority | Forged graph resume, unknown MCP tool and missing approval tests |
| Modified price or quote | Frozen terms/digest; price version and amount rechecked under SKU lock | Tampered digest and price-change tests |
| Another user guesses an ID | Actor derives from signed session; owner/tenant checks on resources | Cross-user approval/execution/session tests |
| Cross-site approval | SameSite/HttpOnly cookies, CSRF token, origin allowlist, trusted hosts and loopback client checks | CSRF/origin/API tests |
| Duplicate request/replay | Unique request/checkout identity; consumed approval; original source commands | Concurrent 50-request acceptance test |
| Overselling or overspending | PostgreSQL row locks, atomic holds, database inventory/budget constraints | Independent-connection stock/budget races |
| Response loss creates a second financial effect | Durable execution/stable action IDs; source inquiry; separate source database | Authorize/dispense/capture/compensation response-loss tests |
| Forged provider success | Strict observation binding and allowed state transitions | HTTP adapter negative-contract tests |
| Product prompt injection/XSS | Structured candidate constraints; backend policy; escaped React text; no shell/web/plugin tools in model adapter | Compromised-planner injection case and browser UI checks |
| Subscription exhaustion | Persisted pre-dispatch call reservations, per-day/per-session caps, bounded subprocess deadline, explicit retry on model failure | Quota/admission/adapter tests |
| Raw context leaks through telemetry | Whitelisted span attributes, no prompts/credentials in export, bounded file rotation | Exporter redaction test |

## Known limitations and required production work

- Replace demo identities with an audited OIDC/session implementation, organizational RBAC, tenant provisioning and a reviewed cookie/TLS configuration.
- Use separate least-privilege database/service principals. The local Compose role is intentionally a synthetic development role; its published local password is not a production secret.
- Review Codex runtime configuration and integration changes after upgrades. The local adapter's tool controls and test observations do not substitute for a hardened hosted inference boundary.
- Add production-grade admission controls, quotas, anomaly alerting, key rotation, retention and incident response. Current caps are local safeguards, not a commercial billing system.
- Complete external protocol verification, dependency/security review, accessibility review and independent testing before handling customer transactions.
- Unknown financial or delivery states intentionally retain holds. Manual operational resolution is required for some cases; there is no speculative automatic release.
- Database restore is separate from process restart recovery. Preserve checkpoint and source effects consistently, and reconcile in-flight external operations before resuming production writes.

No PCI DSS, HIPAA, SOC 2 or payment-network certification is claimed.
