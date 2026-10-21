# Milestone-controlled commerce and agent engineering

Current authorization is milestone 0: research, architecture, meaningful documentation and the requested public repository preparation. No application scaffolding/functionality, agents, migrations, tests, CI or infrastructure configuration. All implementation milestones are unstarted.

In future sessions: teach the problem; show relevant pinned Medusa/AP2/LangGraph/source-test references; discuss alternatives; obtain owner approval before beginning a milestone. After approval, Codex may generate code/tests and supporting changes only within that authorized milestone. Validate/debug, explain important code paths and transaction/tool/recovery behavior, ask understanding/interview questions, then update progress based on real evidence. Generated code alone does not complete a milestone.

AC-01 through AC-10 are mandatory. Start human-approved and complete that vertical slice before delegated autonomy. The LLM interprets/selects/proposes; deterministic trusted code enforces identity, amount, merchant/product scope, expiration/revocation, budget, replay and fulfillment policy. It cannot authorize itself or hold signing keys/raw payment authority.

Keep user intent, purchase permission, stock reservation, order, payment, fulfillment and agent execution state separate. Graph checkpoints do not guarantee payment or dispense idempotency. Do not directly reuse the old PayOps investigation design; this is a new commerce application with original documentation.

Use synthetic data, sandbox providers and a virtual kiosk only. No real card data, funds, hardware control, billable providers/cloud resources or public runtime deployment without explicit approval. No protocol-compliance, production-use or benchmark claims without actual conformance/test evidence. References are for concepts, not source translation or indiscriminate copying; inspect per-file licenses before future reuse.

Use exact repository-scoped Git operations. The Java payment platform remains independent; do not duplicate it in Python or access its database. Only the exact old payops-ai GitHub repository may be deleted after the separately required final owner confirmation; no other repository deletion is authorized.
