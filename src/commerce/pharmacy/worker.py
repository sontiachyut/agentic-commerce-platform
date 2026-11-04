import logging
import threading
import time
from collections import Counter

from sqlalchemy import or_, select

from commerce.models import new_id
from commerce.payments import SourceConflict, SourceUnavailable
from commerce.pharmacy.models import (
    FacilityStock,
    FamilyOrder,
    FamilyQuote,
    Household,
    PickupPermission,
    PickupRequest,
    RoutineItem,
)
from commerce.planner import ModelUnavailable
from commerce.schemas import Actor
from commerce.service import record
from commerce.simulator import SourceRequest

log = logging.getLogger(__name__)


class PharmacyWorker:
    def __init__(self, service, workflow, source):
        self.service, self.workflow, self.source = service, workflow, source
        self.stop_event = threading.Event()
        self.threads = []

    def start(self):
        for method, name in (
            (self.plan_once, "pharmacy-planning"),
            (self.advance_once, "pharmacy-payments"),
        ):
            thread = threading.Thread(target=self.loop, args=(method,), name=name, daemon=True)
            self.threads.append(thread)
            thread.start()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=5)

    def loop(self, method):
        while not self.stop_event.is_set():
            try:
                if not method():
                    self.stop_event.wait(0.3)
            except Exception as exc:
                log.error("pharmacy_worker_failed category=%s", type(exc).__name__)
                self.stop_event.wait(1)

    def plan_once(self):
        with self.service.factory.begin() as db:
            row = db.scalar(
                select(PickupRequest)
                .where(
                    PickupRequest.provider == self.workflow.planner.name,
                    or_(
                        PickupRequest.state == "QUEUED",
                        (PickupRequest.state == "PLANNING")
                        & (PickupRequest.lease_until < time.time()),
                    ),
                )
                .order_by(PickupRequest.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not row:
                return False
            identifier = row.id
            row.state = "PLANNING"
            row.lease_until = time.time() + self.service.settings.model_timeout_seconds + 30
            row.lease_token = new_id()
        try:
            self.workflow.run(identifier)
        except ModelUnavailable:
            self.service.stop(
                identifier,
                "MODEL_UNAVAILABLE",
                "The local assistant is unavailable. No new purchase was authorized; try again when it is available.",
            )
        except Exception as exc:
            log.error("pharmacy_planning_failed category=%s", type(exc).__name__)
            self.service.stop(
                identifier,
                "NEEDS_REVIEW",
                "We could not finish checking this request. No purchase confirmation is available.",
            )
        return True

    def advance_once(self):
        now = time.time()
        with self.service.factory.begin() as db:
            order = db.scalar(
                select(FamilyOrder)
                .where(
                    FamilyOrder.stage.in_(["AUTHORIZE", "CAPTURE", "CANCEL", "DISPENSE"]),
                    FamilyOrder.available_at <= now,
                    FamilyOrder.lease_until < now,
                )
                .order_by(FamilyOrder.available_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not order:
                return False
            quote = db.get(FamilyQuote, order.quote_id)
            identifier, stage, version = order.id, order.stage, order.version
            token = new_id()
            order.lease_token = token
            order.lease_until = now + 30
            order.attempts += 1
            command = SourceRequest(
                execution_id=order.id,
                action=stage.lower(),
                amount_minor=quote.amount_minor,
                currency="USD",
                quote_digest=quote.digest,
                fault_profile=order.fault_profile,
                workflow="pharmacy",
            )
        try:
            result = self.source.observe_or_send(command)
        except (SourceUnavailable, SourceConflict) as exc:
            with self.service.factory.begin() as db:
                row = db.scalar(
                    select(FamilyOrder).where(FamilyOrder.id == identifier).with_for_update()
                )
                if row.lease_token != token:
                    return True
                home = db.get(Household, row.household_id)
                actor = Actor(user_id=home.user_id, tenant_id=home.tenant_id)
                row.lease_until = 0
                row.lease_token = None
                row.available_at = time.time() + min(15, 2 ** min(row.attempts, 4))
                record(db, actor, row.id, "pharmacy.source_unresolved", action=stage)
                if (
                    isinstance(exc, SourceConflict)
                    or row.attempts >= self.service.settings.max_job_attempts
                ):
                    row.state, row.stage = "NEEDS_REVIEW", "REVIEW"
                    quote = db.get(FamilyQuote, row.quote_id)
                    request = db.get(PickupRequest, quote.request_id)
                    request.state, request.message = (
                        "NEEDS_REVIEW",
                        "The payment outcome needs pharmacy review. No second transaction will be sent.",
                    )
            return True
        with self.service.factory.begin() as db:
            order = db.scalar(
                select(FamilyOrder).where(FamilyOrder.id == identifier).with_for_update()
            )
            if order.lease_token != token or order.stage != stage or order.version != version:
                return True
            quote = db.get(FamilyQuote, order.quote_id)
            home = db.get(Household, order.household_id)
            request = db.get(PickupRequest, quote.request_id)
            actor = Actor(user_id=home.user_id, tenant_id=home.tenant_id)
            state = result["state"]
            order.lease_until = 0
            order.lease_token = None
            order.available_at = time.time() + 0.1
            order.version += 1
            order.updated_at = time.time()
            record(
                db,
                actor,
                order.id,
                "pharmacy.source_confirmed",
                action=stage,
                state=state,
                source_command=result["command_id"],
            )
            if stage == "AUTHORIZE" and state == "AUTHORIZED":
                order.payment_state = "AUTHORIZED"
                order.state, order.stage = "AWAITING_REVIEW", "WAIT_STAFF"
                request.state, request.message = (
                    "ORDERED",
                    "Your family pickup order is accepted. The pharmacy will confirm when it is ready; payment is authorized, not yet charged.",
                )
            elif stage == "AUTHORIZE" and state == "DECLINED":
                order.payment_state = "DECLINED"
                self.release(db, order, quote)
                order.state, order.stage = "CANCELED", "DONE"
                request.state, request.message = (
                    "CANCELED",
                    "Payment was declined. No items will be prepared.",
                )
            elif stage == "CAPTURE" and state == "CAPTURED" and order.staff_reviewed:
                order.payment_state = "CAPTURED"
                order.state, order.stage = "READY_FOR_PICKUP", "WAIT_PICKUP"
                order.fulfillment_state = "READY"
                self.capture_holds(db, order, quote)
                request.state, request.message = (
                    "READY_FOR_PICKUP",
                    "Your complete family order is ready for pickup. Payment is confirmed.",
                )
            elif stage == "CAPTURE" and state == "CAPTURE_DECLINED":
                order.state, order.stage = "CANCEL_PENDING", "CANCEL"
                request.message = "The payment could not be captured. We are releasing its original authorization."
            elif stage == "CANCEL" and state == "CANCELED":
                order.payment_state = "CANCELED"
                self.release(db, order, quote)
                order.state, order.stage = "CANCELED", "DONE"
                request.state, request.message = (
                    "CANCELED",
                    "The pharmacy order was canceled and the payment authorization released.",
                )
            elif stage == "DISPENSE" and state == "DISPENSED" and order.payment_state == "CAPTURED":
                stocks = self.stock_rows(db, order, quote)
                if order.stock_state == "HELD":
                    for sku, count in Counter(line["sku"] for line in quote.terms["lines"]).items():
                        stocks[sku].stock -= count
                        stocks[sku].reserved -= count
                    order.stock_state = "CONSUMED"
                order.fulfillment_state = "PICKED_UP"
                order.state, order.stage = "PICKED_UP", "DONE"
                request.state, request.message = (
                    "PICKED_UP",
                    "Pickup confirmed. Your family order is complete.",
                )
            else:
                order.state, order.stage = "NEEDS_REVIEW", "REVIEW"
                request.state, request.message = (
                    "NEEDS_REVIEW",
                    "The source result needs pharmacy review. We will not create another charge or pickup.",
                )
        return True

    def stock_rows(self, db, order, quote):
        return {
            row.sku: row
            for row in db.scalars(
                select(FacilityStock)
                .where(
                    FacilityStock.facility_id == order.facility_id,
                    FacilityStock.sku.in_([line["sku"] for line in quote.terms["lines"]]),
                )
                .order_by(FacilityStock.id)
                .with_for_update()
            )
        }

    def capture_holds(self, db, order, quote):
        permission = db.get(PickupPermission, order.permission_id, with_for_update=True)
        if order.budget_state == "HELD":
            permission.held_minor -= quote.amount_minor
            permission.spent_minor += quote.amount_minor
            permission.held_count -= 1
            permission.spent_count += 1
            order.budget_state = "SPENT"
        items = db.scalars(
            select(RoutineItem)
            .where(RoutineItem.id.in_([line["routine_id"] for line in quote.terms["lines"]]))
            .order_by(RoutineItem.id)
            .with_for_update()
        ).all()
        if order.refill_state == "HELD":
            for item in items:
                if item.kind == "RX":
                    item.refills_held -= 1
                    item.refills_remaining -= 1
                    item.eligibility = "TOO_SOON"
            order.refill_state = "FILLED"

    def release(self, db, order, quote):
        permission = db.get(PickupPermission, order.permission_id, with_for_update=True)
        if order.budget_state == "HELD":
            permission.held_minor -= quote.amount_minor
            permission.held_count -= 1
            order.budget_state = "RELEASED"
        items = db.scalars(
            select(RoutineItem)
            .where(RoutineItem.id.in_([line["routine_id"] for line in quote.terms["lines"]]))
            .order_by(RoutineItem.id)
            .with_for_update()
        ).all()
        if order.refill_state == "HELD":
            for item in items:
                if item.kind == "RX":
                    item.refills_held -= 1
            order.refill_state = "RELEASED"
        stocks = self.stock_rows(db, order, quote)
        if order.stock_state == "HELD":
            for sku, count in Counter(line["sku"] for line in quote.terms["lines"]).items():
                stocks[sku].reserved -= count
            order.stock_state = "RELEASED"
