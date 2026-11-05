"""One durable allowance ledger shared by all local product workflows."""

import time

from sqlalchemy import func, select, text

from commerce.models import AuditEvent
from commerce.planner import ModelUnavailable
from commerce.service import record


def reserve_call(factory, settings, actor, resource_id, purpose, provider):
    if provider != "codex":
        return
    alternate_engine = None
    if settings.model_budget_database_url:
        from commerce.db import make_engine, make_sessions

        alternate_engine = make_engine(settings.model_budget_database_url.get_secret_value())
        factory = make_sessions(alternate_engine)
    try:
        with factory.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(91470332)"))
            daily = db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "model.call_reserved",
                    AuditEvent.created_at >= int(time.time() // 86400) * 86400,
                )
            )
            resource = db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "model.call_reserved",
                    AuditEvent.resource_id == resource_id,
                )
            )
            if (
                daily >= settings.max_daily_model_calls
                or resource >= settings.max_model_calls_per_session
            ):
                raise ModelUnavailable("The configured local model-call budget is exhausted")
            record(
                db, actor, resource_id, "model.call_reserved", purpose=purpose, provider=provider
            )
    finally:
        if alternate_engine is not None:
            alternate_engine.dispose()
