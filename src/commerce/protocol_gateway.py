"""Trusted AP2 local issuer and acceptance adapter around the commerce service."""

import time

import jwt
from ap2.sdk.generated.checkout_receipt import CheckoutReceipt
from ap2.sdk.generated.payment_receipt import PaymentReceipt
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from commerce.ap2_profile import AUDIENCE, AP2Profile
from commerce.domain import DomainError
from commerce.models import AuditEvent, Execution, Grant, ProtocolEnvelope, Quote
from commerce.protocol_security import b64digest
from commerce.schemas import ExecutionRequest
from commerce.service import own, record


class ProtocolGateway:
    def __init__(self, service, identity, keys):
        self.service, self.identity, self.keys = service, identity, keys
        self.profile = AP2Profile(keys)

    def authorize(self, actor, quote_id, *, quote_digest=None, grant_id=None, grant_version=None):
        if bool(quote_digest) == bool(grant_id):
            raise DomainError(
                "AUTHORITY_REQUIRED", "Choose exact consent or a delegated grant.", 422
            )
        if quote_digest:
            approval = self.service.approve(actor, quote_id, quote_digest)
            authority = {"approval_id": approval["id"]}
        else:
            authority = {"grant_id": grant_id, "grant_version": grant_version}
        with self.service.factory.begin() as db:
            quote = own(
                db.scalar(select(Quote).where(Quote.id == quote_id).with_for_update()), actor
            )
            previous = db.scalar(
                select(ProtocolEnvelope).where(ProtocolEnvelope.quote_id == quote_id)
            )
            request = ExecutionRequest(quote_id=quote_id, **authority)
            if previous:
                if previous.authority != request.model_dump():
                    raise DomainError(
                        "AUTHORITY_CONFLICT",
                        "This quote already has a different protocol authority.",
                    )
                return {"envelope_id": previous.id, "profile": "local-ap2-v0.2-es256"}
            if quote.expires_at <= time.time():
                raise DomainError("QUOTE_EXPIRED", "Request a fresh quote.")
            grant = own(db.get(Grant, grant_id), actor) if grant_id else None
            if grant and grant.version != grant_version:
                raise DomainError("GRANT_INACTIVE", "Delegated permission has changed.", 403)
            bundle = self.profile.create(quote, grant)
            self.profile.verify(bundle, quote, expected_nonce=bundle["nonce"], grant=grant)
            envelope = ProtocolEnvelope(
                quote_id=quote_id,
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                encrypted_bundle=self.identity.seal(bundle),
                authority=request.model_dump(),
            )
            db.add(envelope)
            db.flush()
            record(
                db,
                actor,
                quote.session_id,
                "protocol.authorized",
                profile=bundle["profile"],
                envelope_id=envelope.id,
            )
            return {"envelope_id": envelope.id, "profile": bundle["profile"]}

    def bundle(self, actor, envelope_id):
        with self.service.factory() as db:
            envelope = own(db.get(ProtocolEnvelope, envelope_id), actor)
            return self.identity.unseal(envelope.encrypted_bundle)

    def execute(self, actor, envelope_id, request_key, *, fault_profile="none"):
        try:
            with self.service.factory() as db:
                envelope = own(db.get(ProtocolEnvelope, envelope_id), actor)
                quote = own(db.get(Quote, envelope.quote_id), actor)
                authority = ExecutionRequest.model_validate(envelope.authority).model_copy(
                    update={"fault_profile": fault_profile}
                )
                # The commerce service still checks existing replay authority and scoped keys.
                existing = db.scalar(select(Execution).where(Execution.quote_id == quote.id))
                if not existing:
                    bundle = self.identity.unseal(envelope.encrypted_bundle)
                    grant = (
                        own(db.get(Grant, authority.grant_id), actor)
                        if authority.grant_id
                        else None
                    )
                    self.profile.verify(bundle, quote, expected_nonce=bundle["nonce"], grant=grant)
            return self.service.accept(actor, authority, request_key)
        except DomainError:
            raise
        except (ValueError, KeyError, TypeError, InvalidTag, jwt.PyJWTError) as exc:
            raise DomainError(
                "MANDATE_INVALID", "The signed purchase authority could not be verified.", 403
            ) from exc

    def receipts(self, actor, envelope_id):
        with self.service.factory() as db:
            envelope = own(db.get(ProtocolEnvelope, envelope_id), actor)
            execution = db.scalar(select(Execution).where(Execution.quote_id == envelope.quote_id))
            if (
                not execution
                or execution.state != "COMPLETED"
                or execution.payment_state != "CAPTURED"
                or execution.fulfillment_state != "DISPENSED"
            ):
                raise DomainError("RECEIPT_PENDING", "Payment and delivery are not both confirmed.")
            capture = db.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.resource_id == execution.id,
                    AuditEvent.event_type == "source.confirmed",
                )
                .order_by(AuditEvent.created_at.desc())
            )
            if (
                not capture
                or capture.data.get("action") != "CAPTURE"
                or capture.data.get("state") != "CAPTURED"
            ):
                raise DomainError("RECEIPT_PENDING", "The source confirmation is unavailable.")
            bundle = self.identity.unseal(envelope.encrypted_bundle)
            now = int(time.time())
            checkout = CheckoutReceipt.model_validate(
                {
                    "status": "Success",
                    "iss": "https://merchant.example.test",
                    "iat": now,
                    "reference": b64digest(bundle["checkout"][-1]),
                    "order_id": execution.order_id,
                }
            )
            payment = PaymentReceipt.model_validate(
                {
                    "status": "Success",
                    "iss": "https://synthetic-source.example.test",
                    "iat": now,
                    "reference": b64digest(bundle["payment"][-1]),
                    "payment_id": execution.id,
                    "psp_confirmation_id": capture.data["source_command"],
                    "network_confirmation_id": "synthetic-no-payment-network",
                }
            )

            def sign(payload, kind):
                return jwt.encode(
                    payload | {"aud": AUDIENCE, "exp": now + 300},
                    self.keys.keys["merchant"].export_to_pem(private_key=True, password=None),
                    algorithm="ES256",
                    headers={"kid": "local-merchant-v1", "typ": kind},
                )

            return {
                "checkout_receipt": sign(
                    checkout.model_dump(mode="json", exclude_none=True),
                    "local-checkout-receipt+jwt",
                ),
                "payment_receipt": sign(
                    payment.model_dump(mode="json", exclude_none=True), "local-payment-receipt+jwt"
                ),
                "synthetic": True,
            }

    def verify_receipt(self, encoded, *, kind, reference):
        header = jwt.get_unverified_header(encoded)
        if header != {"alg": "ES256", "kid": "local-merchant-v1", "typ": kind}:
            raise ValueError("Wrong receipt key/type")
        claims = jwt.decode(
            encoded,
            self.keys.public("merchant").export_to_pem(),
            algorithms=["ES256"],
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        issuer = (
            "https://merchant.example.test"
            if kind == "local-checkout-receipt+jwt"
            else "https://synthetic-source.example.test"
        )
        if claims["iss"] != issuer or claims.get("reference") != reference:
            raise ValueError("Wrong receipt issuer/reference")
        return claims
