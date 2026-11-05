import time
import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from commerce.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "price_minor > 0 AND stock >= 0 AND reserved >= 0 AND reserved <= stock",
            name="ck_product_inventory",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    kiosk_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(1000), default="")
    price_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    stock: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(default=True)


class PurchaseSession(Base):
    __tablename__ = "purchase_sessions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "request_key", name="uq_session_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    original_request: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(40), default="QUEUED")
    intent: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="Understanding your shopping request.")
    quote_id: Mapped[str | None] = mapped_column(String(36))
    execution_id: Mapped[str | None] = mapped_column(String(36))
    grant_id: Mapped[str | None] = mapped_column(String(36))
    model_provider: Mapped[str] = mapped_column(String(32), default="baseline")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(ForeignKey("purchase_sessions.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    kiosk_id: Mapped[str] = mapped_column(String(64))
    product_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_version: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("quote_id", name="uq_approval_quote"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    expires_at: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        CheckConstraint(
            "held_minor >= 0 AND spent_minor >= 0 AND held_minor + spent_minor <= total_minor",
            name="ck_grant_budget",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64), default="shopping-agent")
    product_ids: Mapped[list] = mapped_column(JSON)
    kiosk_ids: Mapped[list] = mapped_column(JSON)
    per_purchase_minor: Mapped[int] = mapped_column(Integer)
    total_minor: Mapped[int] = mapped_column(Integer)
    held_minor: Mapped[int] = mapped_column(Integer, default=0)
    spent_minor: Mapped[int] = mapped_column(Integer, default=0)
    max_purchases: Mapped[int] = mapped_column(Integer, default=1)
    held_count: Mapped[int] = mapped_column(Integer, default=0)
    spent_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(40), default="EXECUTING")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "request_key", name="uq_execution_request"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), unique=True)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"))
    grant_id: Mapped[str | None] = mapped_column(ForeignKey("grants.id"))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64))
    request_key: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(40), default="EXECUTING")
    stage: Mapped[str] = mapped_column(String(32), default="AUTHORIZE")
    payment_state: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    fulfillment_state: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    compensation_state: Mapped[str] = mapped_column(String(32), default="NOT_NEEDED")
    failure_code: Mapped[str | None] = mapped_column(String(64))
    fault_profile: Mapped[str] = mapped_column(String(40), default="none")
    stock_state: Mapped[str] = mapped_column(String(24), default="HELD")
    budget_state: Mapped[str] = mapped_column(String(24), default="HELD")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("kind", "resource_id", name="uq_job_resource"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    resource_id: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(16), default="READY", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    last_error: Mapped[str | None] = mapped_column(String(64))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor: Mapped[dict] = mapped_column(JSON)
    csrf: Mapped[str] = mapped_column(String(64))
    auth_source: Mapped[str] = mapped_column(String(16))
    issuer: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    token_expires_at: Mapped[float | None] = mapped_column(Float)
    encrypted_tokens: Mapped[str | None] = mapped_column(Text)
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_binding: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(64))
    encrypted_verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[float] = mapped_column(Float)
    consumed: Mapped[bool] = mapped_column(default=False)


class ReplayNonce(Base):
    __tablename__ = "replay_nonces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)


class ProtocolEnvelope(Base):
    __tablename__ = "protocol_envelopes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), unique=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64))
    encrypted_bundle: Mapped[str] = mapped_column(Text)
    authority: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class ProtocolCommand(Base):
    __tablename__ = "protocol_commands"
    __table_args__ = (
        UniqueConstraint("checkout_scope", name="protocol_commands_checkout_scope_key"),
    )
    checkout_scope: Mapped[str | None] = mapped_column(String(64))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    encrypted_response: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[float] = mapped_column(Float)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
