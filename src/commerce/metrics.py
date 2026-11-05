"""Bounded aggregate workflow metrics; no account, purchase or payload labels."""

import time

from prometheus_client import Gauge
from sqlalchemy import func, select

from commerce.models import AuditEvent, Execution, Job

EXECUTIONS = Gauge("commerce_executions", "Recorded executions by current state", ["state"])
JOBS = Gauge("commerce_jobs", "Recorded jobs by current state", ["state"])
PENDING_AGE = Gauge(
    "commerce_oldest_pending_execution_seconds", "Age since creation of oldest unresolved execution"
)
QUEUE_AGE = Gauge("commerce_oldest_ready_job_seconds", "Age of oldest runnable job")
UNRESOLVED = Gauge(
    "commerce_source_unresolved_events", "Durable unresolved source observations; historical count"
)
DENIALS = Gauge("commerce_policy_denial_events", "Durable denied operations; historical count")


def refresh_workflow_metrics(factory):
    now = time.time()
    with factory() as db:
        for model, metric, states in (
            (Execution, EXECUTIONS, ("EXECUTING", "COMPLETED", "CANCELED", "RECOVERY_REQUIRED")),
            (Job, JOBS, ("READY", "RUNNING", "DONE", "NEEDS_REVIEW")),
        ):
            counts = dict(db.execute(select(model.state, func.count()).group_by(model.state)).all())
            for state in states:
                metric.labels(state).set(counts.get(state, 0))
        oldest = db.scalar(
            select(func.min(Execution.created_at)).where(
                Execution.state.in_(["EXECUTING", "RECOVERY_REQUIRED"])
            )
        )
        PENDING_AGE.set(max(0, now - oldest) if oldest else 0)
        ready = db.scalar(
            select(func.min(Job.available_at)).where(Job.state == "READY", Job.available_at <= now)
        )
        QUEUE_AGE.set(max(0, now - ready) if ready else 0)
        for event, gauge in (("source.unresolved", UNRESOLVED), ("policy.denied", DENIALS)):
            gauge.set(
                db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.event_type == event)
                )
            )
