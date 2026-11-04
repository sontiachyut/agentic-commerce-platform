"""Independent synthetic financial/fulfillment source. Never a real PSP."""

import hmac
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import Field
from sqlalchemy import JSON, Float, Integer, String, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from commerce.config import Settings, get_settings
from commerce.db import make_engine, make_sessions
from commerce.domain import digest
from commerce.schemas import StrictModel


class SourceBase(DeclarativeBase):
    pass


class SourcePayment(SourceBase):
    __tablename__ = "source_payments"
    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    binding: Mapped[str] = mapped_column(String(64))
    workflow: Mapped[str] = mapped_column(String(16), default="kiosk")
    state: Mapped[str] = mapped_column(String(32), default="NEW")


class SourceCommand(SourceBase):
    __tablename__ = "source_commands"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(24))
    request_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class SourceRequest(StrictModel):
    workflow: Literal["kiosk", "pharmacy"] = "kiosk"
    execution_id: str = Field(min_length=36, max_length=36)
    action: str
    amount_minor: int = Field(gt=0, le=1_000_000)
    currency: str = Field(pattern="^USD$")
    quote_digest: str = Field(min_length=64, max_length=64)
    fault_profile: str = "none"


class StatefulSource:
    def __init__(self, factory):
        self.factory = factory

    def inquire(self, execution_id, action):
        with self.factory() as db:
            row = db.get(SourceCommand, f"{execution_id}:{action}")
            return row.result if row else None

    def command(self, request: SourceRequest):
        if request.action not in {"authorize", "dispense", "capture", "cancel", "refund"}:
            raise HTTPException(422, "Unsupported source command")
        if request.fault_profile == "source_unavailable":
            raise HTTPException(503, "Synthetic source unavailable")
        key = f"{request.execution_id}:{request.action}"
        request_binding = request.model_dump(exclude={"fault_profile"})
        if request.workflow == "kiosk":
            request_binding.pop("workflow")
        request_hash = digest(request_binding)
        response_lost = False
        with self.factory.begin() as db:
            db.execute(
                insert(SourcePayment)
                .values(
                    execution_id=request.execution_id,
                    amount_minor=request.amount_minor,
                    currency=request.currency,
                    binding=request.quote_digest,
                    workflow=request.workflow,
                    state="NEW",
                )
                .on_conflict_do_nothing()
            )
            payment = db.scalar(
                select(SourcePayment)
                .where(SourcePayment.execution_id == request.execution_id)
                .with_for_update()
            )
            if (
                payment.workflow != request.workflow
                or payment.amount_minor != request.amount_minor
                or payment.currency != request.currency
                or payment.binding != request.quote_digest
            ):
                raise HTTPException(409, "Payment binding conflict")
            prior = db.get(SourceCommand, key)
            if prior:
                if prior.request_digest != request_hash:
                    raise HTTPException(409, "Source idempotency conflict")
                return prior.result
            state = payment.state
            action, fault = request.action, request.fault_profile
            if action == "authorize":
                state = "DECLINED" if fault == "payment_declined" else "AUTHORIZED"
                if fault == "captured_dispense_failed":
                    state = "CAPTURED"
                payment.state = state
            elif action == "dispense":
                if payment.state not in {"AUTHORIZED", "CAPTURED"}:
                    raise HTTPException(409, "Payment authorization required before dispense")
                state = (
                    "FAILED_CONFIRMED"
                    if fault
                    in {"dispense_failed", "captured_dispense_failed", "compensation_response_lost"}
                    else "DISPENSED"
                )
            elif action == "capture":
                dispense = db.get(SourceCommand, f"{request.execution_id}:dispense")
                if payment.workflow == "kiosk" and (
                    not dispense or dispense.result["state"] != "DISPENSED"
                ):
                    raise HTTPException(409, "Confirmed dispense required before capture")
                if payment.state not in {"AUTHORIZED", "CAPTURED"}:
                    raise HTTPException(409, "No capturable authorization")
                state = "CAPTURE_DECLINED" if fault == "capture_declined" else "CAPTURED"
                if state == "CAPTURED":
                    payment.state = state
            elif action == "cancel":
                if payment.state != "AUTHORIZED":
                    raise HTTPException(409, "Only an uncaptured authorization can be canceled")
                state = payment.state = "CANCELED"
            elif action == "refund":
                if payment.state != "CAPTURED":
                    raise HTTPException(409, "Only a captured payment can be refunded")
                state = payment.state = "REFUNDED"
            result = {
                "workflow": payment.workflow,
                "command_id": key,
                "execution_id": request.execution_id,
                "action": action,
                "state": state,
                "amount_minor": request.amount_minor,
                "currency": request.currency,
                "quote_digest": request.quote_digest,
                "source": "local-stateful-simulator-v1",
            }
            db.add(
                SourceCommand(
                    id=key,
                    execution_id=request.execution_id,
                    action=action,
                    request_digest=request_hash,
                    result=result,
                )
            )
            response_lost = fault == {
                "authorize": "payment_response_lost",
                "dispense": "dispense_response_lost",
                "capture": "capture_response_lost",
            }.get(action)
            response_lost |= fault == "compensation_response_lost" and action in {
                "cancel",
                "refund",
            }
        # The remote effect is committed before the response is deliberately lost.
        if response_lost:
            raise HTTPException(
                503, "Synthetic response loss after committed effect; inquire original command"
            )
        return result


def create_source_app(settings: Settings | None = None):
    settings = settings or get_settings()
    engine = make_engine(settings.simulator_database_url)
    factory = make_sessions(engine)

    @asynccontextmanager
    async def lifespan(app):
        settings.require_source_secrets()
        # Simulator schema is not commerce schema and is initialized independently.
        if settings.schema_bootstrap:
            SourceBase.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Synthetic payment and fulfillment source", version="0.1.0", lifespan=lifespan
    )
    source = StatefulSource(factory)

    def authorize(authorization: str = Header(default="")):
        if not hmac.compare_digest(
            authorization, "Bearer " + settings.source_token.get_secret_value()
        ):
            raise HTTPException(401, "Source authentication required")

    @app.get("/health")
    def health():
        return {"status": "ok", "synthetic": True}

    @app.post("/v1/commands", dependencies=[Depends(authorize)])
    def command(request: SourceRequest):
        return source.command(request)

    @app.get("/v1/commands/{execution_id}/{action}", dependencies=[Depends(authorize)])
    def inquire(execution_id: str, action: str):
        result = source.inquire(execution_id, action)
        if result is None:
            raise HTTPException(404, "No recorded command")
        return result

    return app
