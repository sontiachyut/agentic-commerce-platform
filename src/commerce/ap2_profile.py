"""Pinned AP2 v0.2 SDK primitives in a narrow, explicitly local trust profile.

No high-level SDK logging facade, arbitrary intermediate hops or external wallet
trust. Merchant JWT verification is independent of mandate-chain verification.
"""

import hmac
import json
import secrets
import time
from datetime import UTC, datetime

import jwt
from ap2.sdk.constraints import (
    MandateContext,
    check_checkout_constraints,
    check_payment_constraints,
)
from ap2.sdk.disclosure_metadata import DisclosureMetadata
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import OpenCheckoutMandate
from ap2.sdk.generated.open_payment_mandate import OpenPaymentMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.checkout import Checkout
from ap2.sdk.sdjwt import chain, common, kb_sd_jwt, sd_jwt
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from commerce.domain import canonical_terms, digest
from commerce.protocol_security import b64digest

MERCHANT = {
    "id": "kiosk-a",
    "name": "Local synthetic kiosk",
    "website": "https://merchant.example.test",
}
AUDIENCE = "https://merchant.example.test/checkout"
ISSUER = "https://wallet.example.test"


def strict_model(model, payload):
    if not isinstance(payload, dict):
        raise ValueError("Unsupported mandate claims")
    schema = model.model_json_schema()

    def close_objects(value):
        if isinstance(value, dict):
            if "properties" in value:
                value["additionalProperties"] = False
            for child in value.values():
                close_objects(child)
        elif isinstance(value, list):
            for child in value:
                close_objects(child)

    close_objects(schema)
    if not Draft202012Validator(schema).is_valid(payload):
        raise ValueError("Unsupported mandate claims or constraints")
    return model.model_validate(payload)


class AP2Profile:
    def __init__(self, keys):
        self.keys = keys

    def root(self, payload: BaseModel, nonce: str, expires: int, *, audience=AUDIENCE):
        claims = common.selectively_disclosable_claims(
            payload.model_dump(mode="json", exclude_none=True),
            DisclosureMetadata.from_model(payload),
            {
                "iss": ISSUER,
                "aud": audience,
                "nonce": nonce,
                "iat": int(time.time()),
                "exp": expires,
            },
        )
        # The pinned AP2 examples use this root typ; it is a local profile, not a universal SD-JWT credential claim.
        return common.issue_sd_jwt(
            claims=claims,
            issuer_key=self.keys.keys["wallet"],
            header_params=common.header_parameters(self.keys.keys["wallet"], "example+sd-jwt"),
            add_decoy_claims=False,
            serialization_format="compact",
        ).sd_jwt_issuance

    def checkout_payload(self, quote):
        total = {"type": "total", "amount": quote.amount_minor}
        subtotal = {"type": "subtotal", "amount": quote.amount_minor}
        payload = {
            "id": quote.id,
            "merchant": MERCHANT,
            "line_items": [
                {
                    "id": quote.product_id,
                    "item": {
                        "id": quote.product_id,
                        "title": quote.product_name,
                        "price": quote.amount_minor,
                    },
                    "quantity": quote.quantity,
                    "totals": [subtotal, total],
                }
            ],
            "status": "ready_for_complete",
            "currency": quote.currency,
            "totals": [subtotal, total],
            "links": [],
            "expires_at": datetime.fromtimestamp(quote.expires_at, UTC).isoformat(),
            "terms": canonical_terms(quote),
            "quote_digest": quote.digest,
            "iss": MERCHANT["website"],
            "aud": ISSUER,
            "iat": int(time.time()),
            "exp": int(quote.expires_at),
        }
        Checkout.model_validate(payload)
        return payload

    def merchant_checkout(self, quote):
        return jwt.encode(
            self.checkout_payload(quote),
            self.keys.keys["merchant"].export_to_pem(private_key=True, password=None),
            algorithm="ES256",
            headers={"kid": "local-merchant-v1", "typ": "JWT"},
        )

    def create(self, quote, grant=None):
        now, expires = int(time.time()), int(quote.expires_at)
        checkout = self.merchant_checkout(quote)
        checkout_hash = b64digest(checkout)
        nonce = secrets.token_urlsafe(32)
        closed_checkout = CheckoutMandate(
            checkout_jwt=checkout, checkout_hash=checkout_hash, iat=now, exp=expires
        )
        closed_payment = PaymentMandate(
            transaction_id=checkout_hash,
            payee=MERCHANT,
            payment_amount={"amount": quote.amount_minor, "currency": quote.currency},
            payment_instrument={"id": "synthetic-wallet", "type": "synthetic"},
            iat=now,
            exp=expires,
        )
        if grant is None:
            checkout_tokens = [self.root(closed_checkout, "checkout:" + nonce, expires)]
            payment_tokens = [self.root(closed_payment, "payment:" + nonce, expires)]
        else:
            public = json.loads(self.keys.public("delegate").export_public())
            expiry = min(expires, int(grant.expires_at))
            open_checkout = OpenCheckoutMandate(
                constraints=[
                    {
                        "type": "checkout.allowed_merchants",
                        "allowed": [MERCHANT] if "kiosk-a" in grant.kiosk_ids else [],
                    },
                    {
                        "type": "checkout.line_items",
                        "items": [
                            {
                                "id": "one-item",
                                "acceptable_items": [
                                    {"id": sku, "title": sku} for sku in grant.product_ids
                                ],
                                "quantity": 1,
                            }
                        ],
                    },
                ],
                cnf={"jwk": public},
                iat=now,
                exp=expiry,
            )
            root_checkout = self.root(
                open_checkout, "checkout:" + nonce, expiry, audience="urn:commerce:delegate"
            )
            open_payment = OpenPaymentMandate(
                constraints=[
                    {"type": "payment.allowed_payees", "allowed": [MERCHANT]},
                    {
                        "type": "payment.amount_range",
                        "currency": "USD",
                        "min": 1,
                        "max": grant.per_purchase_minor,
                    },
                    {
                        "type": "payment.reference",
                        "conditional_transaction_id": b64digest(root_checkout),
                    },
                    {
                        "type": "payment.agent_recurrence",
                        "frequency": "ON_DEMAND",
                        "max_occurrences": grant.max_purchases,
                    },
                    {"type": "payment.budget", "currency": "USD", "max": grant.total_minor},
                ],
                cnf={"jwk": public},
                iat=now,
                exp=expiry,
            )
            root_payment = self.root(
                open_payment, "payment:" + nonce, expiry, audience="urn:commerce:delegate"
            )

            def terminal(root, closed, purpose):
                # Verification resolves cnf before the documented holder-binding primitive is called.
                parsed = common.parse_token(root)
                verified = sd_jwt.verify(root, self.keys.public("wallet"))
                parsed = parsed.with_verified_payload(
                    verified,
                    [
                        open_checkout.model_dump()
                        if purpose == "checkout"
                        else open_payment.model_dump()
                    ],
                )
                return kb_sd_jwt.create(
                    parsed, self.keys.keys["delegate"], closed, AUDIENCE, purpose + ":" + nonce
                ).sd_jwt_issuance

            checkout_tokens = [root_checkout, terminal(root_checkout, closed_checkout, "checkout")]
            payment_tokens = [root_payment, terminal(root_payment, closed_payment, "payment")]
        return {
            "profile": "local-ap2-v0.2-es256",
            "nonce": nonce,
            "checkout": checkout_tokens,
            "payment": payment_tokens,
        }

    def verified_payloads(self, tokens, purpose, nonce):
        if len(tokens) not in {1, 2} or sum(map(len, tokens)) > 48000:
            raise ValueError("Unsupported chain profile")
        parsed = [common.parse_token(token) for token in tokens]
        if parsed[0].header.get("typ") != "example+sd-jwt":
            raise ValueError("Unsupported root type")
        for index, token in enumerate(parsed):
            expected_kid = "local-wallet-v1" if index == 0 else "local-delegate-v1"
            if (
                token.header.get("alg") != "ES256"
                or token.header.get("kid") != expected_kid
                or set(token.header) - {"typ", "alg", "kid"}
            ):
                raise ValueError("Untrusted signing profile")
        payloads = chain.verify_chain(
            parsed,
            lambda _: self.keys.public("wallet"),
            clock_skew_seconds=0,
            expected_aud=AUDIENCE,
            expected_nonce=purpose + ":" + nonce,
        )
        root = sd_jwt.verify(tokens[0], self.keys.public("wallet"))
        if (
            root.get("iss") != ISSUER
            or root.get("nonce") != purpose + ":" + nonce
            or root.get("aud") != (AUDIENCE if len(tokens) == 1 else "urn:commerce:delegate")
        ):
            raise ValueError("Root issuer, audience or nonce mismatch")
        now = int(time.time())
        for payload in payloads:
            if (
                not isinstance(payload.get("exp"), int)
                or not isinstance(payload.get("iat"), int)
                or not payload["iat"] <= now < payload["exp"]
            ):
                raise ValueError("Mandate outside validity")
        return payloads

    def verify(self, bundle, quote, *, expected_nonce, grant=None):
        if bundle.get("profile") != "local-ap2-v0.2-es256" or not hmac.compare_digest(
            bundle.get("nonce", ""), expected_nonce
        ):
            raise ValueError("Wrong profile or challenge")
        checkout_payloads = self.verified_payloads(bundle["checkout"], "checkout", expected_nonce)
        payment_payloads = self.verified_payloads(bundle["payment"], "payment", expected_nonce)
        if len(checkout_payloads) != len(payment_payloads) or (grant is None) != (
            len(checkout_payloads) == 1
        ):
            raise ValueError("Conflicting mandate modes")
        checkout = strict_model(CheckoutMandate, checkout_payloads[-1])
        payment = strict_model(PaymentMandate, payment_payloads[-1])
        if payment.pisp or payment.execution_date or payment.risk_data:
            raise ValueError("Unsupported payment profile extension")
        header = jwt.get_unverified_header(checkout.checkout_jwt)
        if header != {"alg": "ES256", "kid": "local-merchant-v1", "typ": "JWT"}:
            raise ValueError("Unknown merchant signing profile")
        merchant = jwt.decode(
            checkout.checkout_jwt,
            self.keys.public("merchant").export_to_pem(),
            algorithms=["ES256"],
            audience=ISSUER,
            issuer=MERCHANT["website"],
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        expected = self.checkout_payload(quote)
        if {k: v for k, v in merchant.items() if k != "iat"} != {
            k: v for k, v in expected.items() if k != "iat"
        }:
            raise ValueError("Merchant terms do not match current exact quote")
        if (
            quote.digest != digest(canonical_terms(quote))
            or checkout.checkout_hash != b64digest(checkout.checkout_jwt)
            or payment.transaction_id != checkout.checkout_hash
        ):
            raise ValueError("Checkout hash binding mismatch")
        if (
            payment.payee.id != "kiosk-a"
            or payment.payment_amount.amount != quote.amount_minor
            or payment.payment_amount.currency != quote.currency
            or payment.payment_instrument.id != "synthetic-wallet"
            or payment.payment_instrument.type != "synthetic"
        ):
            raise ValueError("Payment does not match checkout")
        if grant:
            if (
                grant.revoked
                or grant.expires_at <= time.time()
                or quote.product_id not in grant.product_ids
                or quote.kiosk_id not in grant.kiosk_ids
                or quote.amount_minor > grant.per_purchase_minor
                or grant.held_minor + grant.spent_minor + quote.amount_minor > grant.total_minor
                or grant.held_count + grant.spent_count >= grant.max_purchases
            ):
                raise ValueError("Current delegated authority is exhausted or out of scope")
            opened_checkout = strict_model(OpenCheckoutMandate, checkout_payloads[0])
            opened_payment = strict_model(OpenPaymentMandate, payment_payloads[0])
            expected_checkout = {"checkout.allowed_merchants", "checkout.line_items"}
            expected_payment = {
                "payment.allowed_payees",
                "payment.amount_range",
                "payment.reference",
                "payment.agent_recurrence",
                "payment.budget",
            }
            if (
                {c.type for c in opened_checkout.constraints} != expected_checkout
                or len(opened_checkout.constraints) != len(expected_checkout)
                or {c.type for c in opened_payment.constraints} != expected_payment
                or len(opened_payment.constraints) != len(expected_payment)
            ):
                raise ValueError("Unsupported or missing delegation constraints")
            violations = check_checkout_constraints(
                opened_checkout, Checkout.model_validate(merchant)
            )
            violations += check_payment_constraints(
                opened_payment,
                payment,
                open_checkout_hash=b64digest(bundle["checkout"][0]),
                mandate_context=MandateContext(
                    total_amount=grant.held_minor + grant.spent_minor,
                    total_uses=grant.held_count + grant.spent_count,
                ),
            )
            if violations:
                raise ValueError("Delegated mandate constraints rejected")
        return {
            "checkout_hash": checkout.checkout_hash,
            "amount_minor": payment.payment_amount.amount,
            "checkout_reference": b64digest(bundle["checkout"][-1]),
            "payment_reference": b64digest(bundle["payment"][-1]),
        }
