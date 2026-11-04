from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select

from commerce.domain import DomainError
from commerce.pharmacy.models import PickupRequest
from commerce.pharmacy.schemas import PermissionInput, PickupInput, StaffAction
from commerce.pharmacy.speech import NeuralSpeaker, status_sentence
from commerce.pharmacy.voice import VoiceRecognizer
from commerce.schemas import StrictModel


class ExactApproval(StrictModel):
    quote_digest: str = Field(min_length=64, max_length=64)


class SpeechStatus(StrictModel):
    state: str = Field(min_length=1, max_length=32)


def register_pharmacy(app, service, actor, key):
    router = APIRouter(prefix="/api/v1/pharmacy", tags=["Family pickup"])
    voice = VoiceRecognizer(service.settings)
    speaker = NeuralSpeaker(service.settings)
    app.state.speaker = speaker

    @router.get("/workspace")
    def workspace(identity=Depends(actor)):
        return (
            service.staff_workspace(identity)
            if identity.role == "operator"
            else service.workspace(identity)
        )

    @router.get("/voice")
    def voice_status(identity=Depends(actor)):
        return {
            "available": voice.available(),
            "recognition": "local",
            "synthesis": "qwen3-tts-0.6b-8bit-mlx",
            "synthesis_available": speaker.available(),
            "max_seconds": 45,
            "native_carplay": False,
        }

    @router.post("/voice/transcribe")
    async def transcribe(request: Request, identity=Depends(actor)):
        if identity.role != "shopper":
            raise DomainError(
                "CUSTOMER_REQUIRED", "Voice pickup is available in the customer workspace.", 403
            )
        import anyio

        audio = await request.body()
        return await anyio.to_thread.run_sync(voice.transcribe, audio)

    @router.post("/permissions", status_code=201)
    def permission(body: PermissionInput, identity=Depends(actor)):
        return service.create_permission(identity, body)

    @router.delete("/permissions/{identifier}")
    def revoke(identifier: str, identity=Depends(actor)):
        service.revoke_permission(identity, identifier)
        return {"revoked": True}

    @router.post("/requests", status_code=202)
    def create(body: PickupInput, identity=Depends(actor), request_key=Depends(key)):
        return {"request_id": service.create_request(identity, body, request_key)}

    @router.post("/requests/{identifier}/speech")
    async def speak(identifier: str, body: SpeechStatus, identity=Depends(actor)):
        import anyio

        detail = service.request_detail(identity, identifier)
        if detail["state"] != body.state:
            raise DomainError(
                "STATUS_CHANGED", "The order status changed. Read its current status.", 409
            )
        return await anyio.to_thread.run_sync(speaker.speak, status_sentence(detail))

    @router.get("/requests/{identifier}")
    def detail(identifier: str, identity=Depends(actor)):
        return service.request_detail(identity, identifier)

    @router.post("/requests/{identifier}/approval", status_code=202)
    def approve(identifier: str, body: ExactApproval, identity=Depends(actor)):
        detail = service.request_detail(identity, identifier)
        quote = detail["quote"]
        if not quote or quote["digest"] != body.quote_digest:
            raise DomainError("QUOTE_CHANGED", "Review the exact current family basket first.")
        if detail.get("order"):
            return {"order_id": detail["order"]["id"]}
        if detail["state"] != "AWAITING_APPROVAL":
            raise DomainError("APPROVAL_STATE", "This request is not awaiting exact approval.")
        aliases = [line["alias"] for line in quote["terms"]["lines"]]
        amount = quote["terms"]["amount_minor"]
        permission = service.create_permission(
            identity,
            PermissionInput(
                members=aliases,
                per_order_minor=amount,
                total_minor=amount,
                max_orders=1,
                valid_for_seconds=300,
            ),
            exact_quote=quote["id"],
        )
        return {
            "order_id": service.accept(identity, quote["id"], permission["id"], body.quote_digest)
        }

    @router.post("/requests/{identifier}/cancel")
    def cancel(identifier: str, identity=Depends(actor)):
        service.request_detail(identity, identifier)
        with service.factory.begin() as db:
            row = db.scalar(
                select(PickupRequest).where(PickupRequest.id == identifier).with_for_update()
            )
            if row.state not in {
                "QUEUED",
                "PLANNING",
                "QUOTED",
                "AWAITING_APPROVAL",
                "NEEDS_INPUT",
                "BLOCKED",
                "BUDGET_EXCEEDED",
                "MODEL_UNAVAILABLE",
            }:
                raise DomainError(
                    "ORDER_ALREADY_SUBMITTED",
                    "The pharmacy has this order. Please contact the pharmacy team to cancel it.",
                )
            row.state, row.message = "CANCELED", "Request canceled. No new order will be placed."
        return {"canceled": True}

    @router.get("/staff")
    def staff(identity=Depends(actor)):
        return service.staff_workspace(identity)

    @router.post("/staff/orders/{identifier}")
    def progress(identifier: str, body: StaffAction, identity=Depends(actor)):
        service.staff_action(identity, identifier, body)
        return {"accepted": True}

    app.include_router(router)
