import time

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from commerce.db import Base
from commerce.models import new_id


class Household(Base):
    __tablename__ = "pharmacy_households"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_pharmacy_household_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64))
    home_label: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class FamilyMember(Base):
    __tablename__ = "pharmacy_family_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_households.id"), index=True)
    alias: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    relationship: Mapped[str] = mapped_column(String(40))
    access_approved: Mapped[bool] = mapped_column(default=True)
    access_version: Mapped[int] = mapped_column(Integer, default=1)


class RoutineItem(Base):
    __tablename__ = "pharmacy_routine_items"
    __table_args__ = (
        CheckConstraint(
            "refills_remaining >= 0 AND refills_held >= 0 AND refills_held <= refills_remaining",
            name="ck_pharmacy_refill_holds",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_family_members.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    package: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(8))
    eligibility: Mapped[str] = mapped_column(String(32), default="ELIGIBLE")
    coverage: Mapped[str] = mapped_column(String(16), default="CONFIRMED")
    price_minor: Mapped[int] = mapped_column(Integer)
    price_version: Mapped[int] = mapped_column(Integer, default=1)
    refills_remaining: Mapped[int] = mapped_column(Integer, default=2)
    refills_held: Mapped[int] = mapped_column(Integer, default=0)


class Facility(Base):
    __tablename__ = "pharmacy_facilities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    open_minute: Mapped[int] = mapped_column(Integer, default=480)
    close_minute: Mapped[int] = mapped_column(Integer, default=1260)


class FacilityStock(Base):
    __tablename__ = "pharmacy_facility_stock"
    __table_args__ = (
        UniqueConstraint("facility_id", "sku", name="uq_pharmacy_stock_sku"),
        CheckConstraint(
            "stock >= 0 AND reserved >= 0 AND reserved <= stock", name="ck_pharmacy_stock"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_facilities.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64))
    stock: Mapped[int] = mapped_column(Integer, default=10)
    reserved: Mapped[int] = mapped_column(Integer, default=0)


class StaffAssignment(Base):
    __tablename__ = "pharmacy_staff_assignments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "facility_id", name="uq_pharmacy_staff_facility"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    facility_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_facilities.id"))


class PickupPermission(Base):
    __tablename__ = "pharmacy_pickup_permissions"
    __table_args__ = (
        CheckConstraint(
            "held_minor >= 0 AND spent_minor >= 0 AND held_minor + spent_minor <= total_minor",
            name="ck_pharmacy_permission_budget",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_households.id"), index=True)
    member_ids: Mapped[list] = mapped_column(JSON)
    routine_ids: Mapped[list] = mapped_column(JSON)
    facility_ids: Mapped[list] = mapped_column(JSON)
    exact_quote_id: Mapped[str | None] = mapped_column(String(36))
    per_order_minor: Mapped[int] = mapped_column(Integer)
    total_minor: Mapped[int] = mapped_column(Integer)
    held_minor: Mapped[int] = mapped_column(Integer, default=0)
    spent_minor: Mapped[int] = mapped_column(Integer, default=0)
    held_count: Mapped[int] = mapped_column(Integer, default=0)
    spent_count: Mapped[int] = mapped_column(Integer, default=0)
    max_orders: Mapped[int] = mapped_column(Integer, default=3)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class PickupRequest(Base):
    __tablename__ = "pharmacy_pickup_requests"
    __table_args__ = (
        UniqueConstraint("household_id", "request_key", name="uq_pharmacy_request_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_households.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(String(2000))
    channel: Mapped[str] = mapped_column(String(8), default="text")
    provider: Mapped[str] = mapped_column(String(16))
    intent: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default="QUEUED")
    message: Mapped[str] = mapped_column(
        String(500), default="Checking your family pickup request."
    )
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class FamilyQuote(Base):
    __tablename__ = "pharmacy_family_quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_pickup_requests.id"), unique=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_households.id"))
    facility_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_facilities.id"))
    terms: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[float] = mapped_column(Float)


class FamilyOrder(Base):
    __tablename__ = "pharmacy_family_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quote_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_family_quotes.id"), unique=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_households.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_facilities.id"), index=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("pharmacy_pickup_permissions.id"))
    state: Mapped[str] = mapped_column(String(32), default="PAYMENT_PENDING")
    stage: Mapped[str] = mapped_column(String(16), default="AUTHORIZE")
    payment_state: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    fulfillment_state: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    stock_state: Mapped[str] = mapped_column(String(16), default="HELD")
    budget_state: Mapped[str] = mapped_column(String(16), default="HELD")
    refill_state: Mapped[str] = mapped_column(String(16), default="HELD")
    staff_reviewed: Mapped[bool] = mapped_column(default=False)
    fault_profile: Mapped[str] = mapped_column(String(40), default="none")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    available_at: Mapped[float] = mapped_column(Float, default=time.time)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
