import logging
import threading
import time

from opentelemetry import trace
from sqlalchemy import and_, or_, select

from commerce.models import Execution, Grant, Job, Order, Product, Quote, new_id
from commerce.payments import SourceConflict, SourceUnavailable
from commerce.planner import ModelUnavailable
from commerce.schemas import Actor
from commerce.service import record
from commerce.simulator import SourceRequest

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, factory, settings, source, agent=None, kinds=None):
        self.factory, self.settings, self.source, self.agent = factory, settings, source, agent
        self.stop_event = threading.Event()
        self.thread = None
        self.kinds = kinds or {"AGENT", "EXECUTION"}

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True, name="commerce-worker")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                if not self.tick():
                    self.stop_event.wait(self.settings.worker_poll_seconds)
            except Exception:
                # No prompts, credentials or raw payment payloads in logs.
                log.exception("worker_loop_failed")
                self.stop_event.wait(1)

    def tick(self):
        now = time.time()
        with self.factory.begin() as db:
            job = db.scalar(
                select(Job)
                .where(
                    Job.kind.in_(self.kinds),
                    or_(
                        and_(Job.state == "READY", Job.available_at <= now),
                        and_(Job.state == "RUNNING", Job.lease_until < now),
                    ),
                )
                .order_by(Job.available_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                return False
            job.state, job.lease_token = "RUNNING", new_id()
            job.lease_until, job.attempts = now + self.settings.job_lease_seconds, job.attempts + 1
            identifier, token, kind, resource, attempts = (
                job.id,
                job.lease_token,
                job.kind,
                job.resource_id,
                job.attempts,
            )
        retry, error, needs_review = False, None, False
        try:
            if kind == "AGENT":
                if self.agent is None:
                    raise RuntimeError("Agent workflow is not configured")
                self.agent.run(resource)
            else:
                retry = self.advance(resource)
        except SourceUnavailable:
            retry, error = True, "SOURCE_UNRESOLVED"
        except ModelUnavailable:
            # A quota/auth/model failure must not burn the owner's subscription
            # through automatic retries. An explicit user retry is required.
            retry, error, needs_review = False, "MODEL_UNAVAILABLE", True
        except Exception as exc:
            retry, error = True, type(exc).__name__
            log.error("job_failed resource=%s category=%s", resource, error)
        with self.factory.begin() as db:
            job = db.scalar(select(Job).where(Job.id == identifier).with_for_update())
            if job.lease_token != token:
                return True
            if needs_review or (retry and attempts >= self.settings.max_job_attempts):
                job.state = "NEEDS_REVIEW"
                if kind == "EXECUTION":
                    execution = db.scalar(
                        select(Execution).where(Execution.id == resource).with_for_update()
                    )
                    execution.state, execution.failure_code = (
                        "RECOVERY_REQUIRED",
                        error or "RETRY_LIMIT",
                    )
                    db.get(Order, execution.order_id).state = execution.state
                # Resource holds intentionally remain while outcomes are unresolved.
            else:
                job.state = "READY" if retry else "DONE"
            job.available_at = time.time() + (
                min(30, 0.25 * 2 ** min(attempts, 7)) if error else 0.05
            )
            job.last_error, job.lease_token, job.lease_until = error, None, 0
        return True

    def advance(self, execution_id):
        with trace.get_tracer("commerce.worker").start_as_current_span("checkout.advance") as span:
            span.set_attribute("commerce.execution_id", execution_id)
            return self._advance(execution_id)

    def _advance(self, execution_id):
        with self.factory() as db:
            row = db.get(Execution, execution_id)
            if row.state in {"COMPLETED", "CANCELED", "RECOVERY_REQUIRED"}:
                return False
            stage, version = row.stage, row.version
            quote = db.get(Quote, row.quote_id)
            request = SourceRequest(
                execution_id=row.id,
                action=stage.lower(),
                amount_minor=quote.amount_minor,
                currency=quote.currency,
                quote_digest=quote.digest,
                fault_profile=row.fault_profile,
            )
        try:
            result = self.source.observe_or_send(request)
            state = result.get("state")
            valid = {
                "AUTHORIZE": {"AUTHORIZED", "CAPTURED", "DECLINED"},
                "DISPENSE": {"DISPENSED", "FAILED_CONFIRMED"},
                "CAPTURE": {"CAPTURED", "CAPTURE_DECLINED"},
                "CANCEL": {"CANCELED"},
                "REFUND": {"REFUNDED"},
            }
            if state not in valid[stage]:
                raise SourceConflict("Unknown source status")
        except SourceUnavailable:
            with self.factory.begin() as db:
                row = db.scalar(
                    select(Execution).where(Execution.id == execution_id).with_for_update()
                )
                if row.stage == stage and row.version == version:
                    if stage == "DISPENSE":
                        row.fulfillment_state = "UNKNOWN"
                    elif stage in {"CANCEL", "REFUND"}:
                        row.compensation_state = "UNKNOWN"
                    else:
                        row.payment_state = "UNKNOWN"
                    row.updated_at = time.time()
                    record(
                        db,
                        Actor(user_id=row.user_id, tenant_id=row.tenant_id),
                        row.id,
                        "source.unresolved",
                        action=stage,
                    )
            raise
        except SourceConflict:
            with self.factory.begin() as db:
                row = db.scalar(
                    select(Execution).where(Execution.id == execution_id).with_for_update()
                )
                if row.stage == stage and row.version == version:
                    row.state, row.failure_code = "RECOVERY_REQUIRED", "SOURCE_CONFLICT"
                    db.get(Order, row.order_id).state = row.state
            return False
        with self.factory.begin() as db:
            row = db.scalar(select(Execution).where(Execution.id == execution_id).with_for_update())
            # A late worker cannot regress a stage already advanced by a newer worker.
            if row.stage != stage or row.version != version:
                return row.state == "EXECUTING"
            actor = Actor(user_id=row.user_id, tenant_id=row.tenant_id)
            if stage == "AUTHORIZE":
                row.payment_state = state
                if state == "DECLINED":
                    row.state, row.failure_code = "CANCELED", "PAYMENT_DECLINED"
                else:
                    row.stage = "DISPENSE"
            elif stage == "DISPENSE":
                row.fulfillment_state = state
                if state == "FAILED_CONFIRMED":
                    row.stage = "REFUND" if row.payment_state == "CAPTURED" else "CANCEL"
                    row.compensation_state = "PENDING"
                elif row.payment_state == "CAPTURED":
                    row.state = "COMPLETED"
                else:
                    row.stage = "CAPTURE"
            elif stage == "CAPTURE":
                if state == "CAPTURED":
                    row.payment_state, row.state = state, "COMPLETED"
                else:
                    row.state, row.failure_code = (
                        "RECOVERY_REQUIRED",
                        "CAPTURE_DECLINED_AFTER_DELIVERY",
                    )
                    row.payment_state = "AUTHORIZED"
            else:
                row.payment_state, row.compensation_state, row.state = (
                    state,
                    "CONFIRMED",
                    "CANCELED",
                )
            row.version += 1
            row.updated_at = time.time()
            if row.state != "EXECUTING":
                self.finalize(db, row)
                db.get(Order, row.order_id).state = row.state
            record(
                db,
                actor,
                row.id,
                "source.confirmed",
                action=stage,
                state=state,
                source_command=result["command_id"],
                execution_version=row.version,
            )
            return row.state == "EXECUTING"

    def finalize(self, db, execution):
        quote = db.get(Quote, execution.quote_id)
        # Authority before inventory matches acceptance lock order.
        grant = (
            db.scalar(select(Grant).where(Grant.id == execution.grant_id).with_for_update())
            if execution.grant_id
            else None
        )
        product = db.scalar(select(Product).where(Product.id == quote.product_id).with_for_update())
        if execution.stock_state == "HELD":
            if execution.fulfillment_state == "DISPENSED":
                product.stock -= quote.quantity
                product.reserved -= quote.quantity
                execution.stock_state = "CONSUMED"
            elif execution.state == "CANCELED":
                product.reserved -= quote.quantity
                execution.stock_state = "RELEASED"
        if grant and execution.budget_state == "HELD":
            # Lifetime spend is not replenished by refunds. Unknown payment stays held.
            if execution.payment_state in {"CAPTURED", "REFUNDED"}:
                grant.held_minor -= quote.amount_minor
                grant.spent_minor += quote.amount_minor
                grant.held_count -= 1
                grant.spent_count += 1
                execution.budget_state = "CONSUMED"
            elif execution.state == "CANCELED":
                grant.held_minor -= quote.amount_minor
                grant.held_count -= 1
                execution.budget_state = "RELEASED"
