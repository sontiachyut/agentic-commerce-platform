# Milestone-controlled commerce and agent engineering

Owner authorization updated 2026-11-04: build the standalone Agentic Commerce product, supporting documents, local infrastructure, tests and CI, using the assessment and technical design as capability targets. Build and verify each slice before advancing. Java integration is deferred and is not a standalone release gate. The owner approved local Codex-subscription inference; no separately billed model APIs, cloud resources, live payments or public runtime deployment are authorized. Record measured results and limitations rather than treating the assessment's historical prose as implementation evidence.

In future sessions: read docs/STATUS.md first, teach the problem, consult pinned references and relevant tests, explain alternatives, and progress autonomously within the authorized standalone scope. Validate/debug, explain transaction/tool/recovery behavior and maintain the learning guide. Ask for approval only for work outside that scope. Generated code alone does not complete a milestone.

The 2026-11-04 follow-up authorizes the locally feasible MCP/AP2/TAP/UCP/ACP, identity, evaluation, operational and product-hardening work. Read docs/research/README.md, sources.lock.json and the implementation backlog before proceeding. Research findings are not implemented capabilities; keep their evidence separate. No repeated milestone approval is needed within this scope; paid/external enrollment/public runtime boundaries still apply.

AC-01 through AC-10 are mandatory. Start human-approved and complete that vertical slice before delegated autonomy. The LLM interprets/selects/proposes; deterministic trusted code enforces identity, amount, merchant/product scope, expiration/revocation, budget, replay and fulfillment policy. It cannot authorize itself or hold signing keys/raw payment authority.

Keep user intent, purchase permission, stock reservation, order, payment, fulfillment and agent execution state separate. Graph checkpoints do not guarantee payment or dispense idempotency. Do not directly reuse the old PayOps investigation design; this is a new commerce application with original documentation.

Use synthetic data, sandbox providers and a virtual kiosk only. No real card data, funds, hardware control, billable providers/cloud resources or public runtime deployment without explicit approval. No protocol-compliance, production-use or benchmark claims without actual conformance/test evidence. References are for concepts, not source translation or indiscriminate copying; inspect per-file licenses before future reuse.

Use exact repository-scoped Git operations. The Java payment platform remains independent; do not duplicate it in Python or access its database. Only the exact old payops-ai GitHub repository may be deleted after the separately required final owner confirmation; no other repository deletion is authorized.
