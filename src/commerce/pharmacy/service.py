import base64
import hashlib
import hmac
import math
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from commerce.domain import DomainError, digest
from commerce.models import AuditEvent, new_id
from commerce.pharmacy.fixtures import ensure_demo
from commerce.pharmacy.models import (
    Facility,
    FacilityStock,
    FamilyMember,
    FamilyOrder,
    FamilyQuote,
    Household,
    PickupPermission,
    PickupRequest,
    RoutineItem,
    StaffAssignment,
)
from commerce.schemas import Actor
from commerce.service import record


def distance(a, b, c, d):
    lat1, lat2 = math.radians(a), math.radians(c)
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(d - b) / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(min(1, math.sqrt(value)))


def within(amount, limit, comparison):
    return limit is not None and (amount < limit if comparison == "lt" else amount <= limit)


class PharmacyService:
    def __init__(self, factory, settings, clock=time.time):
        self.factory, self.settings, self.clock = factory, settings, clock

    def household(self, db, actor):
        value = db.scalar(
            select(Household).where(
                Household.tenant_id == actor.tenant_id, Household.user_id == actor.user_id
            )
        )
        if not value:
            raise DomainError("HOUSEHOLD_NOT_FOUND", "Family workspace not found.", 404)
        return value

    def customer(self, actor):
        if actor.role != "shopper":
            raise DomainError(
                "CUSTOMER_REQUIRED", "Open a customer workspace for family requests.", 403
            )
        return ensure_demo(self.factory, actor)

    def permission_dict(self, row):
        return {
            k: getattr(row, k)
            for k in (
                "id",
                "per_order_minor",
                "total_minor",
                "held_minor",
                "spent_minor",
                "held_count",
                "spent_count",
                "max_orders",
                "expires_at",
                "revoked",
                "version",
                "member_ids",
                "facility_ids",
            )
        }

    def workspace(self, actor):
        household_id = self.customer(actor)
        with self.factory() as db:
            home = self.household(db, actor)
            members = []
            for member in db.scalars(
                select(FamilyMember).where(FamilyMember.household_id == household_id)
            ):
                item = db.scalar(select(RoutineItem).where(RoutineItem.member_id == member.id))
                members.append(
                    {
                        "id": member.id,
                        "alias": member.alias,
                        "name": member.name,
                        "relationship": member.relationship,
                        "access_approved": member.access_approved,
                        "regular": {
                            "name": item.name,
                            "package": item.package,
                            "kind": item.kind,
                            "price_minor": item.price_minor,
                            "eligibility": item.eligibility,
                            "coverage": item.coverage,
                        }
                        if member.access_approved
                        else None,
                    }
                )
            permissions = db.scalars(
                select(PickupPermission)
                .where(
                    PickupPermission.household_id == home.id,
                    PickupPermission.exact_quote_id.is_(None),
                )
                .order_by(PickupPermission.expires_at.desc())
            ).all()
            facilities = db.scalars(
                select(Facility).where(Facility.tenant_id == actor.tenant_id)
            ).all()
            requests = db.scalars(
                select(PickupRequest)
                .where(PickupRequest.household_id == home.id)
                .order_by(PickupRequest.created_at.desc())
                .limit(12)
            ).all()
            return {
                "household_id": home.id,
                "home": home.home_label,
                "members": members,
                "permission": self.permission_dict(permissions[0]) if permissions else None,
                "facilities": [self.facility_dict(f, home) for f in facilities],
                "requests": [
                    {
                        "id": r.id,
                        "text": r.text,
                        "state": r.state,
                        "message": r.message,
                        "created_at": r.created_at,
                    }
                    for r in requests
                ],
                "synthetic": True,
                "model_provider": self.settings.model_provider,
            }

    def facility_dict(self, facility, home):
        return {
            "id": facility.id,
            "name": facility.name,
            "address": facility.address,
            "distance_miles": round(
                distance(home.latitude, home.longitude, facility.latitude, facility.longitude), 2
            ),
            "closes_at": f"{facility.close_minute // 60:02d}:{facility.close_minute % 60:02d}",
        }

    def create_permission(self, actor, body, *, exact_quote=None):
        home_id = self.customer(actor)
        with self.factory.begin() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                {"scope": "family-permission:" + home_id},
            )
            if exact_quote is None:
                for previous in db.scalars(
                    select(PickupPermission)
                    .where(
                        PickupPermission.household_id == home_id,
                        PickupPermission.exact_quote_id.is_(None),
                        PickupPermission.revoked.is_(False),
                    )
                    .order_by(PickupPermission.id)
                    .with_for_update()
                ):
                    previous.revoked = True
                    previous.version += 1
            members = db.scalars(
                select(FamilyMember).where(
                    FamilyMember.household_id == home_id, FamilyMember.alias.in_(body.members)
                )
            ).all()
            if len(members) != len(set(body.members)) or any(
                not m.access_approved for m in members
            ):
                raise DomainError(
                    "CAREGIVER_ACCESS",
                    "Approved access is required for every selected family member.",
                    403,
                )
            routines = db.scalars(
                select(RoutineItem).where(RoutineItem.member_id.in_([m.id for m in members]))
            ).all()
            facilities = db.scalars(
                select(Facility.id).where(Facility.tenant_id == actor.tenant_id)
            ).all()
            value = PickupPermission(
                id=new_id(),
                household_id=home_id,
                member_ids=[m.id for m in members],
                routine_ids=[r.id for r in routines],
                facility_ids=facilities,
                per_order_minor=body.per_order_minor,
                total_minor=body.total_minor,
                max_orders=body.max_orders,
                expires_at=self.clock() + body.valid_for_seconds,
                exact_quote_id=exact_quote,
            )
            db.add(value)
            db.flush()
            record(
                db,
                actor,
                value.id,
                "pharmacy.permission_granted",
                limit_minor=value.per_order_minor,
                members=len(members),
                exact=bool(exact_quote),
            )
            return self.permission_dict(value)

    def revoke_permission(self, actor, identifier):
        with self.factory.begin() as db:
            home = self.household(db, actor)
            row = db.get(PickupPermission, identifier)
            if not row or row.household_id != home.id:
                raise DomainError("NOT_FOUND", "Permission not found.", 404)
            row.revoked = True
            row.version += 1
            record(db, actor, row.id, "pharmacy.permission_revoked")

    def create_request(self, actor, body, key):
        home_id = self.customer(actor)
        binding = digest(body.model_dump())
        with self.factory.begin() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                {"scope": "family-request:" + home_id},
            )
            previous = db.scalar(
                select(PickupRequest).where(
                    PickupRequest.household_id == home_id, PickupRequest.request_key == key
                )
            )
            if previous:
                if previous.request_digest != binding:
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT", "This request key belongs to a different request."
                    )
                return previous.id
            if (
                db.scalar(
                    select(func.count())
                    .select_from(PickupRequest)
                    .where(
                        PickupRequest.household_id == home_id,
                        PickupRequest.state.in_(["QUEUED", "PLANNING"]),
                    )
                )
                >= 3
            ):
                raise DomainError(
                    "ADMISSION_LIMIT", "Please let your current family request finish first.", 429
                )
            row = PickupRequest(
                id=new_id(),
                household_id=home_id,
                request_key=key,
                request_digest=binding,
                text=body.text,
                channel=body.channel,
                provider=self.settings.model_provider,
            )
            db.add(row)
            record(db, actor, row.id, "pharmacy.request_received", channel=body.channel)
            return row.id

    def request_context(self, identifier):
        with self.factory() as db:
            row = db.get(PickupRequest, identifier)
            home = db.get(Household, row.household_id)
            return Actor(user_id=home.user_id, tenant_id=home.tenant_id), row

    def stop(self, identifier, state, message):
        actor, _ = self.request_context(identifier)
        with self.factory.begin() as db:
            row = db.scalar(
                select(PickupRequest).where(PickupRequest.id == identifier).with_for_update()
            )
            if row.state == "CANCELED":
                return None
            row.state, row.message = state, message
            record(db, actor, row.id, "pharmacy.request_stopped", reason=state)
        return None

    def prepare_quote(self, actor, identifier, intent):
        with self.factory.begin() as db:
            request = db.scalar(
                select(PickupRequest).where(PickupRequest.id == identifier).with_for_update()
            )
            home = self.household(db, actor)
            if request.household_id != home.id:
                raise DomainError("NOT_FOUND", "Request not found.", 404)
            if request.state == "CANCELED":
                return None
            previous = db.scalar(select(FamilyQuote).where(FamilyQuote.request_id == identifier))
            if previous:
                return previous.id
            if (
                intent.clarification
                or not intent.members
                or intent.max_amount_minor is None
                or intent.currency != "USD"
            ):
                request.state, request.message = (
                    "NEEDS_INPUT",
                    intent.clarification or "Please confirm the family members and a USD budget.",
                )
                return None
            members = db.scalars(
                select(FamilyMember)
                .where(FamilyMember.household_id == home.id, FamilyMember.alias.in_(intent.members))
                .order_by(FamilyMember.id)
            ).all()
            if len(members) != len(set(intent.members)) or any(
                not m.access_approved for m in members
            ):
                request.state, request.message = (
                    "BLOCKED",
                    "Family access needs attention. Nothing was ordered; an adult family member must approve access.",
                )
                return None
            items = db.scalars(
                select(RoutineItem)
                .where(RoutineItem.member_id.in_([m.id for m in members]))
                .order_by(RoutineItem.id)
            ).all()
            by_member = {m.id: m for m in members}
            lines = []
            for item in items:
                member = by_member[item.member_id]
                blocked = (
                    item.eligibility != "ELIGIBLE"
                    or item.coverage != "CONFIRMED"
                    or item.kind == "RX"
                    and (item.refills_remaining <= item.refills_held or item.refills_held > 0)
                )
                if blocked:
                    reason = (
                        "coverage needs confirmation"
                        if item.coverage != "CONFIRMED"
                        else "a refill is already pending"
                        if item.refills_held
                        else "a prescription renewal or refill-date check is needed"
                    )
                    request.state, request.message = (
                        "BLOCKED",
                        f"{member.relationship if member.alias != 'self' else 'Your'} saved item cannot be ordered yet: {reason}. Nothing was charged or ordered.",
                    )
                    return None
                lines.append(
                    {
                        "routine_id": item.id,
                        "member_id": member.id,
                        "alias": member.alias,
                        "member_name": member.name,
                        "access_version": member.access_version,
                        "sku": item.sku,
                        "name": item.name,
                        "package": item.package,
                        "kind": item.kind,
                        "quantity": 1,
                        "amount_minor": item.price_minor,
                        "price_version": item.price_version,
                    }
                )
            if not lines:
                raise DomainError("EMPTY_ROUTINE", "No saved regular items were found.")
            now = datetime.fromtimestamp(self.clock(), ZoneInfo("America/Phoenix"))
            minute = (
                self.settings.pharmacy_demo_minute
                if self.settings.pharmacy_demo_minute is not None
                else now.hour * 60 + now.minute
            )
            choices = []
            for facility in db.scalars(
                select(Facility).where(Facility.tenant_id == actor.tenant_id)
            ):
                stocks = {
                    s.sku: s.stock - s.reserved
                    for s in db.scalars(
                        select(FacilityStock).where(FacilityStock.facility_id == facility.id)
                    )
                }
                eligible = facility.open_minute <= minute < facility.close_minute and all(
                    stocks.get(sku, 0) >= count
                    for sku, count in Counter(line["sku"] for line in lines).items()
                )
                choices.append(
                    self.facility_dict(facility, home)
                    | {
                        "eligible": eligible,
                        "reason": "Complete family basket available"
                        if eligible
                        else "Closed or a saved item is unavailable",
                    }
                )
            choices.sort(key=lambda choice: (choice["distance_miles"], choice["id"]))
            facility = next((choice for choice in choices if choice["eligible"]), None)
            if not facility:
                request.state, request.message = (
                    "BLOCKED",
                    "No open location can supply the complete family basket. Nothing was ordered.",
                )
                return None
            amount = sum(line["amount_minor"] for line in lines)
            terms = {
                "household_id": home.id,
                "tenant_id": actor.tenant_id,
                "user_id": actor.user_id,
                "facility": facility,
                "alternatives": choices,
                "lines": lines,
                "amount_minor": amount,
                "currency": "USD",
                "requested_limit_minor": intent.max_amount_minor,
                "budget_comparison": intent.budget_comparison,
            }
            quote = FamilyQuote(
                id=new_id(),
                request_id=identifier,
                household_id=home.id,
                facility_id=facility["id"],
                terms=terms,
                digest=digest(terms),
                amount_minor=amount,
                expires_at=self.clock() + 300,
            )
            db.add(quote)
            request.state = "QUOTED"
            request.message = "Your family basket and pickup location are ready."
            if not within(amount, intent.max_amount_minor, intent.budget_comparison):
                request.state, request.message = (
                    "BUDGET_EXCEEDED",
                    f"The complete basket is ${amount / 100:.2f}, above your requested limit. Nothing was ordered; I will not remove or substitute medicines to fit the budget.",
                )
            record(
                db,
                actor,
                identifier,
                "pharmacy.quote_prepared",
                amount_minor=amount,
                items=len(lines),
                facility_id=quote.facility_id,
            )
            return quote.id

    def accept(self, actor, quote_id, permission_id=None, expected_digest=None):
        with self.factory.begin() as db:
            home = self.household(db, actor)
            quote = db.scalar(
                select(FamilyQuote).where(FamilyQuote.id == quote_id).with_for_update()
            )
            if not quote or quote.household_id != home.id:
                raise DomainError("NOT_FOUND", "Family quote not found.", 404)
            existing = db.scalar(select(FamilyOrder).where(FamilyOrder.quote_id == quote.id))
            if existing:
                return existing.id
            if (
                quote.expires_at <= self.clock()
                or quote.digest != digest(quote.terms)
                or expected_digest
                and not hmac.compare_digest(expected_digest, quote.digest)
            ):
                raise DomainError(
                    "QUOTE_CHANGED",
                    "The exact family quote expired or changed. Start a fresh request.",
                )
            request = db.scalar(
                select(PickupRequest).where(PickupRequest.id == quote.request_id).with_for_update()
            )
            if request.state == "CANCELED":
                raise DomainError("REQUEST_CANCELED", "This family request was canceled.")
            terms = quote.terms
            if not within(
                quote.amount_minor, terms["requested_limit_minor"], terms["budget_comparison"]
            ):
                raise DomainError(
                    "REQUEST_BUDGET", "The basket exceeds the original request limit."
                )
            selection = select(PickupPermission).where(
                PickupPermission.household_id == home.id,
                PickupPermission.revoked.is_(False),
                PickupPermission.expires_at > self.clock(),
            )
            selection = (
                selection.where(PickupPermission.id == permission_id)
                if permission_id
                else selection.where(PickupPermission.exact_quote_id.is_(None))
            )
            permissions = db.scalars(
                selection.order_by(PickupPermission.expires_at.desc()).with_for_update()
            ).all()
            permission = next(
                (
                    p
                    for p in permissions
                    if (not p.exact_quote_id or p.exact_quote_id == quote.id)
                    and quote.amount_minor <= p.per_order_minor
                    and p.held_minor + p.spent_minor + quote.amount_minor <= p.total_minor
                    and p.held_count + p.spent_count < p.max_orders
                    and quote.facility_id in p.facility_ids
                    and all(
                        line["member_id"] in p.member_ids and line["routine_id"] in p.routine_ids
                        for line in terms["lines"]
                    )
                ),
                None,
            )
            if not permission:
                raise DomainError(
                    "PERMISSION_REQUIRED",
                    "Review this exact basket or configure a valid family pickup permission.",
                    403,
                )
            members = {
                m.id: m
                for m in db.scalars(
                    select(FamilyMember)
                    .where(FamilyMember.id.in_([line["member_id"] for line in terms["lines"]]))
                    .order_by(FamilyMember.id)
                    .with_for_update()
                )
            }
            routines = {
                r.id: r
                for r in db.scalars(
                    select(RoutineItem)
                    .where(RoutineItem.id.in_([line["routine_id"] for line in terms["lines"]]))
                    .order_by(RoutineItem.id)
                    .with_for_update()
                )
            }
            stocks = {
                s.sku: s
                for s in db.scalars(
                    select(FacilityStock)
                    .where(
                        FacilityStock.facility_id == quote.facility_id,
                        FacilityStock.sku.in_([line["sku"] for line in terms["lines"]]),
                    )
                    .order_by(FacilityStock.id)
                    .with_for_update()
                )
            }
            for line in terms["lines"]:
                member, item = members[line["member_id"]], routines[line["routine_id"]]
                if not member.access_approved or member.access_version != line["access_version"]:
                    raise DomainError(
                        "CAREGIVER_ACCESS", "Family access changed. Nothing was ordered.", 403
                    )
                if (
                    item.price_minor != line["amount_minor"]
                    or item.price_version != line["price_version"]
                    or item.eligibility != "ELIGIBLE"
                    or item.coverage != "CONFIRMED"
                ):
                    raise DomainError(
                        "PHARMACY_TERMS_CHANGED",
                        "Saved prescription eligibility or final pricing changed. Request a fresh basket.",
                    )
                if item.kind == "RX" and (
                    item.refills_held > 0 or item.refills_remaining <= item.refills_held
                ):
                    raise DomainError(
                        "REFILL_ALREADY_REQUESTED",
                        "A saved prescription is no longer available for another refill request.",
                    )
            for sku, count in Counter(line["sku"] for line in terms["lines"]).items():
                if sku not in stocks or stocks[sku].stock - stocks[sku].reserved < count:
                    raise DomainError(
                        "PHARMACY_STOCK_CHANGED",
                        "A saved item is no longer available at this location.",
                    )
                stocks[sku].reserved += count
            for item in routines.values():
                if item.kind == "RX":
                    item.refills_held += 1
            permission.held_minor += quote.amount_minor
            permission.held_count += 1
            order = FamilyOrder(
                id=new_id(),
                quote_id=quote.id,
                household_id=home.id,
                facility_id=quote.facility_id,
                permission_id=permission.id,
            )
            db.add(order)
            request.state, request.message = (
                "ORDERING",
                "Checking payment authorization. Your order is not confirmed yet.",
            )
            record(
                db,
                actor,
                order.id,
                "pharmacy.order_accepted",
                quote_id=quote.id,
                permission_id=permission.id,
                amount_minor=quote.amount_minor,
            )
            return order.id

    def code(self, order_id):
        return base64.b32encode(
            hmac.digest(
                self.settings.signing_key.get_secret_value().encode(),
                ("pharmacy-pickup:" + order_id).encode(),
                hashlib.sha256,
            )
        ).decode()[:8]

    def safe_terms(self, db, quote):
        terms = dict(quote.terms)
        lines = []
        for line in terms["lines"]:
            member = db.get(FamilyMember, line["member_id"])
            lines.append(
                line
                if member and member.access_approved
                else {
                    "alias": line["alias"],
                    "member_id": line["member_id"],
                    "member_name": line["member_name"],
                    "name": "Family access no longer authorized",
                    "amount_minor": line["amount_minor"],
                    "quantity": 1,
                    "kind": "HIDDEN",
                }
            )
        return terms | {"lines": lines}

    def order_dict(self, db, row, *, staff=False):
        quote = db.get(FamilyQuote, row.quote_id)
        facility = db.get(Facility, row.facility_id)
        return {
            "id": row.id,
            "reference": "AF-" + row.id[:6].upper(),
            "state": row.state,
            "payment_state": row.payment_state,
            "fulfillment_state": row.fulfillment_state,
            "amount_minor": quote.amount_minor,
            "facility": {"id": facility.id, "name": facility.name, "address": facility.address},
            "terms": quote.terms if staff else self.safe_terms(db, quote),
            "pickup_code": self.code(row.id)
            if not staff and row.state == "READY_FOR_PICKUP"
            else None,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def request_detail(self, actor, identifier):
        with self.factory() as db:
            home = self.household(db, actor)
            request = db.get(PickupRequest, identifier)
            if not request or request.household_id != home.id:
                raise DomainError("NOT_FOUND", "Request not found.", 404)
            quote = db.scalar(select(FamilyQuote).where(FamilyQuote.request_id == request.id))
            order = (
                db.scalar(select(FamilyOrder).where(FamilyOrder.quote_id == quote.id))
                if quote
                else None
            )
            events = db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == actor.tenant_id,
                    AuditEvent.actor_id == actor.user_id,
                    AuditEvent.resource_id.in_([request.id, order.id if order else ""]),
                )
                .order_by(AuditEvent.created_at)
            ).all()
            return {
                "id": request.id,
                "text": request.text,
                "state": request.state,
                "message": request.message,
                "quote": {
                    "id": quote.id,
                    "digest": quote.digest,
                    "terms": self.safe_terms(db, quote),
                    "expires_at": quote.expires_at,
                }
                if quote
                else None,
                "order": self.order_dict(db, order) if order else None,
                "events": [{"type": event.event_type, "at": event.created_at} for event in events],
            }

    def staff_facilities(self, db, actor):
        if actor.role != "operator":
            raise DomainError("STAFF_REQUIRED", "Pharmacy staff access required.", 403)
        return list(
            db.scalars(
                select(StaffAssignment.facility_id).where(
                    StaffAssignment.tenant_id == actor.tenant_id,
                    StaffAssignment.user_id == actor.user_id,
                )
            )
        )

    def staff_workspace(self, actor):
        ensure_demo(self.factory, actor)
        with self.factory() as db:
            facilities = self.staff_facilities(db, actor)
            orders = db.scalars(
                select(FamilyOrder)
                .where(FamilyOrder.facility_id.in_(facilities))
                .order_by(FamilyOrder.created_at.desc())
                .limit(30)
            ).all()
            return {
                "facilities": [
                    {"id": f.id, "name": f.name, "address": f.address}
                    for f in db.scalars(select(Facility).where(Facility.id.in_(facilities)))
                ],
                "orders": [self.order_dict(db, o, staff=True) for o in orders],
                "synthetic": True,
                "model_provider": self.settings.model_provider,
            }

    def staff_action(self, actor, identifier, action):
        with self.factory.begin() as db:
            facilities = self.staff_facilities(db, actor)
            order = db.scalar(
                select(FamilyOrder)
                .where(FamilyOrder.id == identifier, FamilyOrder.facility_id.in_(facilities))
                .with_for_update()
            )
            if not order:
                raise DomainError("NOT_FOUND", "Pharmacy order not found.", 404)
            if action.action in {"ready", "collect"}:
                quote = db.get(FamilyQuote, order.quote_id)
                members = {
                    m.id: m
                    for m in db.scalars(
                        select(FamilyMember)
                        .where(
                            FamilyMember.id.in_(
                                [line["member_id"] for line in quote.terms["lines"]]
                            )
                        )
                        .order_by(FamilyMember.id)
                        .with_for_update()
                    )
                }
                if any(
                    not members[line["member_id"]].access_approved
                    or members[line["member_id"]].access_version != line["access_version"]
                    for line in quote.terms["lines"]
                ):
                    raise DomainError(
                        "CAREGIVER_ACCESS_CHANGED",
                        "Family pickup access changed. Reconcile this order with the customer before proceeding.",
                        403,
                    )
                permission = db.get(PickupPermission, order.permission_id)
                if action.action == "ready" and (
                    permission.revoked or permission.expires_at <= self.clock()
                ):
                    raise DomainError(
                        "PERMISSION_CHANGED",
                        "The payment permission expired or was revoked. Do not charge this order.",
                        403,
                    )
            if action.action == "ready":
                if order.state in ["CAPTURE_PENDING", "READY_FOR_PICKUP", "PICKED_UP"]:
                    return
                if order.state != "AWAITING_REVIEW" or not action.clinical_review_confirmed:
                    raise DomainError(
                        "PHARMACY_REVIEW",
                        "Review eligibility and prepare every saved item before marking ready.",
                    )
                order.staff_reviewed = True
                order.stage = "CAPTURE"
                order.state = "CAPTURE_PENDING"
            elif action.action == "reject":
                if order.state == "CANCELED":
                    return
                if order.state != "AWAITING_REVIEW":
                    raise DomainError(
                        "CANCEL_REVIEW", "This order requires reconciliation before cancellation."
                    )
                order.stage, order.state = "CANCEL", "CANCEL_PENDING"
            else:
                if order.state == "PICKED_UP":
                    return
                if (
                    order.state != "READY_FOR_PICKUP"
                    or not action.pickup_code
                    or not hmac.compare_digest(action.pickup_code.upper(), self.code(order.id))
                ):
                    raise DomainError(
                        "PICKUP_VERIFICATION",
                        "Ready status and the customer pickup code are required.",
                        403,
                    )
                order.stage, order.state = "DISPENSE", "PICKUP_CONFIRMING"
            order.version += 1
            order.available_at = self.clock()
            record(db, actor, order.id, "pharmacy.staff_action", action=action.action)
