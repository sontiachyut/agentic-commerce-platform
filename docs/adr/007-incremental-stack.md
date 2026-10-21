# ADR 007 — Add infrastructure only for a demonstrated requirement

**Status:** proposed. Python/FastAPI/Pydantic/PostgreSQL/SQLAlchemy/Alembic and pure tests first; LangGraph/fake provider then trusted UI/checkout, durable saver/recovery and optional workers. Langfuse/OTel support evaluation/debugging, never truth/permission.

Celery/Redis transports work only if needed; PostgreSQL owns jobs/state. Exact catalog filters precede full-text/pgvector. MCP/OpenFGA/Temporal/Kubernetes and multi-agent reasoning need new scope/ADR and measurable value. k6/simulators measure capacity separately from LLM quality and low-volume Stripe integration. Compose/Actions/ECS configuration and billable deployment/calls require later approval; no configs exist now. Pin compatible patches/prices/retention during implementation rather than inventing a supported matrix or cost today.
