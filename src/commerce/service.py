import hmac
import time

from opentelemetry import trace
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert

from commerce.domain import DomainError, canonical_terms, digest, outcome
from commerce.models import (
    Approval,
    AuditEvent,
    Execution,
    Grant,
    Job,
    Order,
    Product,
    PurchaseSession,
    Quote,
    new_id,
)
from commerce.schemas import Actor, ExecutionRequest, GrantRequest, Intent


def own(row, actor: Actor):
    if row is None or row.tenant_id != actor.tenant_id or row.user_id != actor.user_id:
        raise DomainError("NOT_FOUND", "Resource not found.", 404)
    return row


def record(db, actor: Actor, resource: str, event: str, **data):
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        data["trace_id"] = f"{context.trace_id:032x}"
    db.add(
        AuditEvent(
            tenant_id=actor.tenant_id,
            actor_id=actor.user_id,
            resource_id=resource,
            event_type=event,
            data=data,
        )
    )


def enqueue(db, kind: str, resource_id: str, *, revive: bool = False):
    values = dict(
        id=new_id(),
        kind=kind,
        resource_id=resource_id,
        state="READY",
        attempts=0,
        available_at=time.time(),
        lease_until=0,
    )
    statement = insert(Job).values(**values)
    if revive:
        statement = statement.on_conflict_do_update(
            constraint="uq_job_resource",
            set_={
                "state": "READY",
                "available_at": time.time(),
                "lease_token": None,
                "lease_until": 0,
                "attempts": 0,
                "last_error": None,
            },
        )
    else:
        statement = statement.on_conflict_do_nothing(constraint="uq_job_resource")
    db.execute(statement)


class CommerceService:
    def __init__(self, factory, settings, clock=time.time):
        self.factory, self.settings, self.clock = factory, settings, clock

    def audit_denial(self, actor: Actor, resource: str, code: str):
        with self.factory.begin() as db:
            record(db, actor, resource[:64], "policy.denied", code=code)

    def catalog(self, actor: Actor, kiosk_id: str = "kiosk-a", intent: Intent | None = None):
        with self.factory() as db:
            rows = db.scalars(
                select(Product)
                .where(
                    Product.tenant_id == actor.tenant_id,
                    Product.kiosk_id == kiosk_id,
                    Product.active.is_(True),
                )
                .order_by(Product.price_minor, Product.id)
            ).all()
            result = []
            for p in rows:
                if intent:
                    if intent.category != "any" and p.category != intent.category:
                        continue
                    if (
                        intent.max_amount_minor is not None
                        and p.price_minor > intent.max_amount_minor
                    ):
                        continue
                    if p.stock - p.reserved < 1:
                        continue
                result.append(
                    {
                        "id": p.id,
                        "kiosk_id": p.kiosk_id,
                        "name": p.name,
                        "category": p.category,
                        "description": p.description[:500],
                        "price_minor": p.price_minor,
                        "currency": p.currency,
                        "available": p.stock - p.reserved,
                        "price_version": p.version,
                    }
                )
            return result

    def create_session(self, actor: Actor, request: str, request_key: str, grant_id=None):
        payload_hash = digest({"request": request, "grant_id": grant_id})
        with self.factory.begin() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                {"scope": f"commerce-session:{actor.tenant_id}:{actor.user_id}"},
            )
            prior = db.scalar(
                select(PurchaseSession).where(
                    PurchaseSession.tenant_id == actor.tenant_id,
                    PurchaseSession.user_id == actor.user_id,
                    PurchaseSession.request_key == request_key,
                )
            )
            if prior:
                if prior.request_hash != payload_hash:
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "This request key already belongs to different terms.",
                    )
                return prior.id
            active = db.scalar(
                select(func.count())
                .select_from(PurchaseSession)
                .outerjoin(Quote, Quote.id == PurchaseSession.quote_id)
                .outerjoin(Execution, Execution.id == PurchaseSession.execution_id)
                .where(
                    PurchaseSession.tenant_id == actor.tenant_id,
                    PurchaseSession.user_id == actor.user_id,
                    or_(
                        PurchaseSession.state == "QUEUED",
                        (PurchaseSession.state == "EXECUTING")
                        & Execution.state.in_(["EXECUTING", "RECOVERY_REQUIRED"]),
                        (PurchaseSession.state == "AWAITING_APPROVAL")
                        & (Quote.expires_at > self.clock()),
                    ),
                )
            )
            if active >= self.settings.max_active_sessions_per_user:
                raise DomainError(
                    "ADMISSION_LIMIT",
                    "Finish an existing purchase or let its quote expire before starting another.",
                    429,
                )
            if grant_id:
                own(db.get(Grant, grant_id), actor)
            identifier = new_id()
            db.execute(
                insert(PurchaseSession)
                .values(
                    id=identifier,
                    tenant_id=actor.tenant_id,
                    user_id=actor.user_id,
                    original_request=request,
                    request_key=request_key,
                    request_hash=payload_hash,
                    grant_id=grant_id,
                    model_provider=self.settings.model_provider,
                    state="QUEUED",
                    intent={},
                    revision=1,
                    message="Understanding your shopping request.",
                    created_at=self.clock(),
                )
                .on_conflict_do_nothing(constraint="uq_session_request")
            )
            row = db.scalar(
                select(PurchaseSession).where(
                    PurchaseSession.tenant_id == actor.tenant_id,
                    PurchaseSession.user_id == actor.user_id,
                    PurchaseSession.request_key == request_key,
                )
            )
            if row.request_hash != payload_hash:
                raise DomainError(
                    "IDEMPOTENCY_CONFLICT", "This request key already belongs to different terms."
                )
            enqueue(db, "AGENT", row.id)
            if row.id == identifier:
                record(db, actor, row.id, "session.created", provider=row.model_provider)
            return row.id

    def quote(self, actor: Actor, session_id: str, product_id: str):
        with self.factory.begin() as db:
            session = own(
                db.scalar(
                    select(PurchaseSession)
                    .where(PurchaseSession.id == session_id)
                    .with_for_update()
                ),
                actor,
            )
            if session.quote_id:
                return self.quote_dict(own(db.get(Quote, session.quote_id), actor))
            product = db.scalar(
                select(Product).where(
                    Product.id == product_id,
                    Product.tenant_id == actor.tenant_id,
                    Product.active.is_(True),
                )
            )
            if product is None:
                raise DomainError(
                    "PRODUCT_NOT_FOUND", "The selected product is not available.", 404
                )
            intent = Intent.model_validate(session.intent)
            if product.kiosk_id != intent.kiosk_id or (
                intent.category != "any" and product.category != intent.category
            ):
                raise DomainError(
                    "PRODUCT_SCOPE", "The selected product does not match the shopping request."
                )
            if (
                intent.max_amount_minor is not None
                and product.price_minor > intent.max_amount_minor
            ):
                raise DomainError(
                    "OVER_BUDGET", "The selected product exceeds the requested budget."
                )
            if product.stock - product.reserved < 1:
                raise DomainError("OUT_OF_STOCK", "This item is no longer available.")
            quote = Quote(
                id=new_id(),
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                session_id=session.id,
                product_id=product.id,
                product_name=product.name,
                kiosk_id=product.kiosk_id,
                quantity=1,
                price_version=product.version,
                amount_minor=product.price_minor,
                currency=product.currency,
                expires_at=self.clock() + self.settings.quote_ttl_seconds,
            )
            quote.digest = digest(canonical_terms(quote))
            db.add(quote)
            session.quote_id, session.state = quote.id, "AWAITING_APPROVAL"
            session.message = (
                "Review the exact purchase below. Nothing has been charged or reserved."
            )
            record(db, actor, session.id, "quote.created", quote_id=quote.id, digest=quote.digest)
            return self.quote_dict(quote)

    @staticmethod
    def quote_dict(quote):
        return {
            **canonical_terms(quote),
            "digest": quote.digest,
            "product_name": quote.product_name,
        }

    def approve(self, actor: Actor, quote_id: str, expected_digest: str):
        with self.factory.begin() as db:
            quote = own(
                db.scalar(select(Quote).where(Quote.id == quote_id).with_for_update()), actor
            )
            if not hmac.compare_digest(expected_digest, quote.digest) or quote.digest != digest(
                canonical_terms(quote)
            ):
                raise DomainError(
                    "QUOTE_TAMPERED", "The approval does not match the exact purchase terms."
                )
            if quote.expires_at <= self.clock():
                raise DomainError(
                    "QUOTE_EXPIRED", "This quote has expired. Start a new shopping request."
                )
            prior = db.scalar(select(Approval).where(Approval.quote_id == quote.id))
            if prior:
                return {"id": prior.id, "state": prior.state, "quote_id": quote.id}
            approval = Approval(
                id=new_id(),
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                quote_id=quote.id,
                digest=quote.digest,
                state="ACTIVE",
                expires_at=quote.expires_at,
            )
            db.add(approval)
            record(
                db,
                actor,
                quote.session_id,
                "approval.granted",
                approval_id=approval.id,
                quote_id=quote.id,
            )
            return {"id": approval.id, "state": approval.state, "quote_id": quote.id}

    def accept(self, actor: Actor, request: ExecutionRequest, request_key: str):
        with self.factory.begin() as db:
            # The quote lock serializes duplicate acceptance; authority then SKU locks
            # give all requests the same lock order. No remote I/O occurs here.
            quote = own(
                db.scalar(select(Quote).where(Quote.id == request.quote_id).with_for_update()),
                actor,
            )
            prior_key = db.scalar(
                select(Execution).where(
                    Execution.tenant_id == actor.tenant_id,
                    Execution.user_id == actor.user_id,
                    Execution.request_key == request_key,
                )
            )
            if prior_key and prior_key.quote_id != quote.id:
                raise DomainError(
                    "IDEMPOTENCY_CONFLICT", "This execution key belongs to another checkout."
                )
            existing = db.scalar(select(Execution).where(Execution.quote_id == quote.id))
            if existing:
                if (
                    existing.approval_id != request.approval_id
                    or existing.grant_id != request.grant_id
                ):
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "This checkout already has a different authority binding.",
                    )
                return existing.id
            if quote.expires_at <= self.clock():
                raise DomainError(
                    "QUOTE_EXPIRED", "This quote has expired. Request a new quote and approval."
                )
            if quote.digest != digest(canonical_terms(quote)):
                raise DomainError("QUOTE_TAMPERED", "The purchase terms could not be verified.")
            if bool(request.approval_id) == bool(request.grant_id):
                raise DomainError(
                    "AUTHORITY_REQUIRED",
                    "Supply exactly one human approval or delegated grant.",
                    403,
                )
            approval, grant = None, None
            if request.approval_id:
                approval = own(
                    db.scalar(
                        select(Approval).where(Approval.id == request.approval_id).with_for_update()
                    ),
                    actor,
                )
                if (
                    approval.quote_id != quote.id
                    or approval.digest != quote.digest
                    or approval.state != "ACTIVE"
                    or approval.expires_at <= self.clock()
                ):
                    raise DomainError(
                        "APPROVAL_INVALID",
                        "The purchase approval is invalid, consumed, revoked or expired.",
                        403,
                    )
            else:
                grant = own(
                    db.scalar(select(Grant).where(Grant.id == request.grant_id).with_for_update()),
                    actor,
                )
                if (
                    grant.revoked
                    or grant.expires_at <= self.clock()
                    or grant.version != request.grant_version
                ):
                    raise DomainError(
                        "GRANT_INACTIVE", "This permission is expired, revoked or has changed.", 403
                    )
                if (
                    grant.agent_id != "shopping-agent"
                    or quote.product_id not in grant.product_ids
                    or quote.kiosk_id not in grant.kiosk_ids
                    or quote.currency != "USD"
                ):
                    raise DomainError(
                        "GRANT_SCOPE", "This permission does not cover the selected purchase.", 403
                    )
                if (
                    quote.amount_minor > grant.per_purchase_minor
                    or grant.held_minor + grant.spent_minor + quote.amount_minor > grant.total_minor
                    or grant.held_count + grant.spent_count >= grant.max_purchases
                ):
                    raise DomainError(
                        "GRANT_EXHAUSTED",
                        "The purchase would exceed the delegated spending limit.",
                        403,
                    )
            product = db.scalar(
                select(Product).where(Product.id == quote.product_id).with_for_update()
            )
            if (
                not product
                or not product.active
                or product.tenant_id != actor.tenant_id
                or product.kiosk_id != quote.kiosk_id
            ):
                raise DomainError(
                    "PRODUCT_SCOPE", "This product is not available in the approved scope.", 403
                )
            if (
                product.version != quote.price_version
                or product.price_minor != quote.amount_minor
                or product.currency != quote.currency
            ):
                raise DomainError(
                    "PRICE_CHANGED", "The price changed. A new quote and approval are required."
                )
            if product.stock - product.reserved < quote.quantity:
                raise DomainError(
                    "OUT_OF_STOCK",
                    "Another purchase reserved the last item. No payment was requested.",
                )
            product.reserved += quote.quantity
            if approval:
                approval.state = "CONSUMED"
            if grant:
                grant.held_minor += quote.amount_minor
                grant.held_count += 1
            order = Order(
                id=new_id(),
                quote_id=quote.id,
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                state="EXECUTING",
            )
            db.add(order)
            db.flush()
            execution = Execution(
                id=new_id(),
                order_id=order.id,
                quote_id=quote.id,
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                request_key=request_key,
                approval_id=request.approval_id,
                grant_id=request.grant_id,
                fault_profile=request.fault_profile,
                state="EXECUTING",
                stage="AUTHORIZE",
                payment_state="NOT_STARTED",
                fulfillment_state="NOT_STARTED",
                compensation_state="NOT_NEEDED",
                stock_state="HELD",
                budget_state="HELD",
                version=1,
            )
            db.add(execution)
            db.flush()
            session = db.get(PurchaseSession, quote.session_id)
            session.execution_id, session.state = execution.id, "EXECUTING"
            enqueue(db, "EXECUTION", execution.id)
            record(
                db,
                actor,
                execution.id,
                "checkout.accepted",
                order_id=order.id,
                quote_id=quote.id,
                authority_id=request.approval_id or request.grant_id,
            )
            return execution.id

    def create_grant(self, actor: Actor, request: GrantRequest):
        if request.total_minor < request.per_purchase_minor:
            raise DomainError(
                "INVALID_BUDGET", "The total budget must cover the per-purchase limit.", 422
            )
        with self.factory.begin() as db:
            products = db.scalars(
                select(Product).where(
                    Product.id.in_(request.product_ids),
                    Product.tenant_id == actor.tenant_id,
                    Product.active.is_(True),
                )
            ).all()
            if len(products) != len(set(request.product_ids)) or any(
                p.kiosk_id not in request.kiosk_ids for p in products
            ):
                raise DomainError(
                    "GRANT_SCOPE", "Every permitted product must belong to a permitted kiosk.", 403
                )
            grant = Grant(
                id=new_id(),
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                product_ids=sorted(set(request.product_ids)),
                kiosk_ids=sorted(set(request.kiosk_ids)),
                per_purchase_minor=request.per_purchase_minor,
                total_minor=request.total_minor,
                max_purchases=request.max_purchases,
                expires_at=self.clock() + request.valid_for_seconds,
            )
            db.add(grant)
            db.flush()
            record(db, actor, grant.id, "grant.created", total_minor=grant.total_minor)
            return self.grant_dict(grant)

    @staticmethod
    def grant_dict(grant):
        return {
            key: getattr(grant, key)
            for key in (
                "id",
                "product_ids",
                "kiosk_ids",
                "per_purchase_minor",
                "total_minor",
                "held_minor",
                "spent_minor",
                "max_purchases",
                "held_count",
                "spent_count",
                "expires_at",
                "revoked",
                "version",
            )
        }

    def revoke_grant(self, actor: Actor, grant_id: str):
        with self.factory.begin() as db:
            grant = own(
                db.scalar(select(Grant).where(Grant.id == grant_id).with_for_update()), actor
            )
            if not grant.revoked:
                grant.revoked, grant.version = True, grant.version + 1
                record(db, actor, grant.id, "grant.revoked", in_flight_count=grant.held_count)
            return self.grant_dict(grant)

    def session_detail(self, actor: Actor, session_id: str):
        with self.factory() as db:
            row = own(db.get(PurchaseSession, session_id), actor)
            result = {
                key: getattr(row, key)
                for key in (
                    "id",
                    "original_request",
                    "state",
                    "message",
                    "intent",
                    "model_provider",
                    "created_at",
                    "grant_id",
                )
            }
            result["quote"] = self.quote_dict(db.get(Quote, row.quote_id)) if row.quote_id else None
            result["execution"] = (
                self.execution_dict(db.get(Execution, row.execution_id))
                if row.execution_id
                else None
            )
            if result["execution"]:
                result["state"] = result["execution"]["state"]
                result["message"] = result["execution"]["outcome"]["message"]
            result["events"] = [
                {"id": e.id, "type": e.event_type, "data": e.data, "created_at": e.created_at}
                for e in db.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.tenant_id == actor.tenant_id,
                        AuditEvent.resource_id.in_([row.id, row.execution_id or ""]),
                    )
                    .order_by(AuditEvent.created_at)
                ).all()
            ]
            return result

    @staticmethod
    def execution_dict(row):
        return {
            **{
                key: getattr(row, key)
                for key in (
                    "id",
                    "order_id",
                    "quote_id",
                    "state",
                    "stage",
                    "payment_state",
                    "fulfillment_state",
                    "compensation_state",
                    "failure_code",
                    "version",
                    "created_at",
                    "updated_at",
                )
            },
            "outcome": outcome(row),
        }


CATALOG = [
    (
        "bar-cocoa",
        "Cocoa almond protein bar",
        "protein-bar",
        350,
        8,
        "18g protein. Almonds, cocoa and sea salt.",
    ),
    (
        "bar-peanut",
        "Peanut crunch protein bar",
        "protein-bar",
        375,
        6,
        "20g protein. Roasted peanuts and dark chocolate.",
    ),
    (
        "bar-premium",
        "Vanilla protein bar",
        "protein-bar",
        450,
        5,
        "22g protein. Vanilla and cashew.",
    ),
    ("sparkling-water", "Lime sparkling water", "drink", 225, 12, "Unsweetened. 330ml can."),
    ("trail-mix", "Roasted trail mix", "snack", 295, 7, "A small bag of nuts and dried fruit."),
    (
        "last-bar",
        "Limited oat protein bar",
        "protein-bar",
        325,
        1,
        "One item remaining. Use this SKU to test a stock race.",
    ),
]


def seed(factory):
    with factory.begin() as db:
        for sku, name, category, price, stock, description in CATALOG:
            db.execute(
                insert(Product)
                .values(
                    id=sku,
                    tenant_id="demo",
                    kiosk_id="kiosk-a",
                    name=name,
                    category=category,
                    price_minor=price,
                    currency="USD",
                    stock=stock,
                    reserved=0,
                    description=description,
                    active=True,
                    version=1,
                )
                .on_conflict_do_nothing()
            )
