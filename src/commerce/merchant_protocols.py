"""Version-pinned outbound merchant adapters with durable uncertain-call handling.

Configured synthetic/contract peers only. No public merchant enrollment is implied.
These adapters do not interpret a checkout status as payment or delivery evidence.
"""

import base64
import json
import re
import time
from importlib.resources import files
from urllib.parse import urlparse

import httpx
import jwt
import rfc8785
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.exceptions import NoSuchResource
from sqlalchemy.dialects.postgresql import insert

from commerce.domain import DomainError, digest
from commerce.models import ProtocolCommand
from commerce.protocol_security import b64digest

VERSIONS = {"ucp": "2026-08-25", "acp": "2026-04-17"}
ACP_TYPES = {
    "create": "CheckoutSessionCreateRequest",
    "update": "CheckoutSessionUpdateRequest",
    "complete": "CheckoutSessionCompleteRequest",
    "cancel": "CancelSessionRequest",
}


def no_remote_schema(uri):
    raise NoSuchResource(uri)


def schema_validate(protocol, operation, direction, payload):
    root = files("commerce").joinpath("protocol_schemas")
    if protocol == "ucp":
        schema = json.loads(root.joinpath(f"ucp/{operation}_{direction}.json").read_text())
    else:
        schema = json.loads(root.joinpath("acp/checkout.json").read_text())
        target = (
            ACP_TYPES[operation]
            if direction == "request"
            else (
                "CheckoutSessionWithOrder"
                if payload.get("status") == "completed"
                else "CheckoutSession"
            )
        )
        schema = schema | {"$ref": "#/$defs/" + target}
    validator = Draft202012Validator(
        schema, registry=Registry(retrieve=no_remote_schema), format_checker=FormatChecker()
    )
    if not validator.is_valid(payload):
        raise DomainError(
            "PROTOCOL_SCHEMA",
            "Message does not satisfy the pinned merchant contract.",
            422 if direction == "request" else 502,
        )


def checkout_state(payload):
    status = payload["status"]
    return {
        "merchant_status": status,
        "order_placed": status == "completed",
        "payment_confirmed": None,
        "fulfillment_confirmed": None,
    }


def detached_authorization(checkout, key):
    """UCP AP2 signs JCS of the full response excluding only its top-level ap2."""
    protected = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"alg": "ES256", "kid": key.get("kid"), "typ": "JWT"}, separators=(",", ":")
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(rfc8785.dumps({k: v for k, v in checkout.items() if k != "ap2"}))
        .rstrip(b"=")
        .decode()
    )
    signing = (protected + "." + payload).encode()
    private = key.get_op_key("sign")
    der = private.sign(signing, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    signature = (
        base64.urlsafe_b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        .rstrip(b"=")
        .decode()
    )
    return protected + ".." + signature


def verify_detached_authorization(checkout, key):
    encoded = checkout.get("ap2", {}).get("merchant_authorization", "")
    parts = encoded.split(".")
    if len(parts) != 3 or parts[1]:
        raise DomainError("MERCHANT_SIGNATURE", "Detached merchant authorization is required.", 502)
    payload = (
        base64.urlsafe_b64encode(rfc8785.dumps({k: v for k, v in checkout.items() if k != "ap2"}))
        .rstrip(b"=")
        .decode()
    )
    compact = parts[0] + "." + payload + "." + parts[2]
    try:
        header = jwt.get_unverified_header(compact)
        if header != {"alg": "ES256", "kid": key.get("kid"), "typ": "JWT"}:
            raise ValueError("Untrusted key/profile")
        # UCP checkout is not a JWT claims set; its signed object has no issuer/audience claims.
        # Destination and merchant key come only from configured peer trust.
        jwt.decode(
            compact,
            key.export_to_pem(),
            algorithms=["ES256"],
            options={
                "verify_aud": False,
                "verify_iat": False,
                "verify_exp": False,
                "verify_nbf": False,
            },
        )
    except (ValueError, jwt.PyJWTError) as exc:
        raise DomainError(
            "MERCHANT_SIGNATURE", "Merchant terms signature could not be verified.", 502
        ) from exc
    return compact, b64digest(compact)


class MerchantAdapter:
    def __init__(
        self,
        protocol,
        base_url,
        *,
        factory,
        box,
        token,
        transport=None,
        merchant_key=None,
        retry_policy="read_only",
    ):
        if (
            protocol not in VERSIONS
            or retry_policy not in {"read_only", "ucp_idempotent"}
            or retry_policy == "ucp_idempotent"
            and protocol != "ucp"
        ):
            raise ValueError("Unsupported adapter profile")
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("This release permits configured loopback synthetic merchants only")
        self.protocol, self.base_url, self.factory, self.box = (
            protocol,
            base_url.rstrip("/"),
            factory,
            box,
        )
        self.merchant_key, self.retry_policy = merchant_key, retry_policy
        self.http = httpx.Client(
            base_url=self.base_url,
            timeout=5,
            trust_env=False,
            follow_redirects=False,
            headers={
                "Authorization": "Bearer " + token,
                "API-Version": VERSIONS[protocol],
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    def close(self):
        self.http.close()

    def validate_response(self, operation, payload, checkout_id=None, *, require_ap2=False):
        schema_validate(self.protocol, operation, "response", payload)
        if (
            payload.get("ucp", {}).get("version")
            if self.protocol == "ucp"
            else payload.get("protocol", {}).get("version")
        ) != VERSIONS[self.protocol]:
            raise DomainError(
                "PROTOCOL_VERSION", "Merchant response has an unsupported version.", 502
            )
        if checkout_id and payload["id"] != checkout_id:
            raise DomainError("CHECKOUT_BINDING", "Merchant returned a different checkout.", 502)
        if require_ap2:
            if self.protocol != "ucp" or not self.merchant_key:
                raise DomainError(
                    "MANDATE_REQUIRED", "Negotiated AP2 cannot be removed or left unverified.", 502
                )
            verify_detached_authorization(payload, self.merchant_key)
        return payload

    def retrieve(self, checkout_id, *, require_ap2=False):
        self.reference(checkout_id)
        try:
            response = self.http.get(
                "/checkout-sessions/" + checkout_id
                if self.protocol == "ucp"
                else "/checkout_sessions/" + checkout_id
            )
            response.raise_for_status()
            return self.validate_response(
                "read", response.json(), checkout_id, require_ap2=require_ap2
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise DomainError(
                "MERCHANT_UNRESOLVED", "Merchant status remains unresolved.", 503
            ) from exc

    @staticmethod
    def reference(checkout_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", checkout_id):
            raise DomainError("CHECKOUT_REFERENCE", "Invalid merchant checkout reference.", 422)

    def command(
        self, actor, operation, payload, request_key, *, checkout_id=None, require_ap2=False
    ):
        if operation not in {"create", "update", "complete", "cancel"}:
            raise ValueError("Unsupported operation")
        if not 8 <= len(request_key) <= (255 if self.protocol == "acp" else 100):
            raise DomainError("IDEMPOTENCY_KEY", "Invalid merchant request key length.", 422)
        if operation != "create":
            self.reference(checkout_id or "")
        # GET and cancel have no UCP checkout-body schema in the selected REST operation.
        if not (self.protocol == "ucp" and operation == "cancel"):
            if require_ap2 and operation == "complete" and self.protocol == "ucp":
                schema = json.loads(
                    files("commerce")
                    .joinpath("protocol_schemas/ucp/ap2_complete_request.json")
                    .read_text()
                )
                if not Draft202012Validator(
                    schema, registry=Registry(retrieve=no_remote_schema)
                ).is_valid(payload):
                    raise DomainError(
                        "MANDATE_REQUIRED", "The negotiated AP2 mandate is required.", 422
                    )
            else:
                schema_validate(self.protocol, operation, "request", payload)
        scope = {
            "tenant": actor.tenant_id,
            "user": actor.user_id,
            "merchant": self.base_url,
            "protocol": self.protocol,
            "key": request_key,
        }
        identifier, binding = (
            digest(scope),
            digest(
                {
                    "operation": operation,
                    "checkout_id": checkout_id,
                    "payload": payload,
                    "require_ap2": require_ap2,
                }
            ),
        )
        checkout_scope = (
            digest({k: v for k, v in scope.items() if k != "key"} | {"checkout_id": checkout_id})
            if operation == "complete"
            else None
        )
        existing_state = None
        with self.factory.begin() as db:
            inserted = db.execute(
                insert(ProtocolCommand)
                .values(
                    id=identifier,
                    checkout_scope=checkout_scope,
                    request_digest=binding,
                    state="INFLIGHT",
                    lease_until=time.time() + 15,
                )
                .on_conflict_do_nothing()
                .returning(ProtocolCommand.id)
            ).scalar_one_or_none()
            if not inserted:
                row = db.get(ProtocolCommand, identifier)
                if row is None:
                    from sqlalchemy import select

                    row = db.scalar(
                        select(ProtocolCommand).where(
                            ProtocolCommand.checkout_scope == checkout_scope
                        )
                    )
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "This merchant checkout already has a different completion key.",
                    )
                if row.request_digest != binding:
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT", "Request key belongs to different merchant terms."
                    )
                if row.state == "RESOLVED":
                    return self.box.unseal(row.encrypted_response)
                if row.state == "INFLIGHT" and row.lease_until > time.time():
                    raise DomainError(
                        "REQUEST_IN_PROGRESS", "The original merchant request is still in progress."
                    )
                existing_state = row.state
                row.state = "UNKNOWN"
        if existing_state:
            if not checkout_id:
                raise DomainError(
                    "MERCHANT_UNRESOLVED",
                    "Creation is uncertain; reconcile the original merchant request key.",
                    503,
                )
            observed = self.retrieve(checkout_id, require_ap2=require_ap2)
            if operation == "complete" and observed["status"] in {
                "completed",
                "complete_in_progress",
            }:
                return self.resolve(identifier, observed)
            if operation != "complete" or self.retry_policy != "ucp_idempotent":
                raise DomainError(
                    "MERCHANT_UNRESOLVED",
                    "The original request needs reconciliation; no second completion was sent.",
                    503,
                )
            # Explicit configured-peer policy only. Claim another bounded lease before identical-key retransmission.
            with self.factory.begin() as db:
                row = db.get(ProtocolCommand, identifier, with_for_update=True)
                if row.state == "RESOLVED":
                    return self.box.unseal(row.encrypted_response)
                if row.state == "INFLIGHT" and row.lease_until > time.time():
                    raise DomainError(
                        "REQUEST_IN_PROGRESS", "Reconciliation is already in progress."
                    )
                row.state, row.lease_until = "INFLIGHT", time.time() + 15
        prefix = "/checkout-sessions" if self.protocol == "ucp" else "/checkout_sessions"
        path = (
            prefix
            + ("/" + checkout_id if checkout_id else "")
            + ("/" + operation if operation in {"complete", "cancel"} else "")
        )
        method = "PUT" if operation == "update" and self.protocol == "ucp" else "POST"
        try:
            # Transport signature refresh belongs here; the business key and serialized payload stay stable.
            response = self.http.request(
                method, path, json=payload, headers={"Idempotency-Key": request_key}
            )
            response.raise_for_status()
            result = self.validate_response(
                operation, response.json(), checkout_id, require_ap2=require_ap2
            )
            return self.resolve(identifier, result)
        except (httpx.HTTPError, ValueError, DomainError) as exc:
            with self.factory.begin() as db:
                db.get(ProtocolCommand, identifier).state = "UNKNOWN"
            if isinstance(exc, DomainError):
                raise
            raise DomainError(
                "MERCHANT_UNRESOLVED",
                "Merchant response is uncertain; retrieve the original checkout before retrying.",
                503,
            ) from exc

    def resolve(self, identifier, payload):
        with self.factory.begin() as db:
            row = db.get(ProtocolCommand, identifier, with_for_update=True)
            row.state, row.encrypted_response = "RESOLVED", self.box.seal(payload)
        return payload


def negotiate_ucp(profile, *, require_ap2=False):
    version = profile.get("ucp", {}).get("version")
    capabilities = profile.get("ucp", {}).get("capabilities", {})
    if version != VERSIONS["ucp"] or "dev.ucp.shopping.checkout" not in capabilities:
        raise DomainError("PROTOCOL_NEGOTIATION", "No supported checkout capability.", 422)
    if require_ap2 and "dev.ucp.common.payment_ap2_mandate" not in capabilities:
        raise DomainError("MANDATE_DOWNGRADE", "Required AP2 capability is absent.", 403)
    for name in ["dev.ucp.shopping.checkout"] + (
        ["dev.ucp.common.payment_ap2_mandate"] if require_ap2 else []
    ):
        entries = capabilities.get(name)
        if not isinstance(entries, list) or not any(
            isinstance(entry, dict) and entry.get("version") == VERSIONS["ucp"] for entry in entries
        ):
            raise DomainError("PROTOCOL_NEGOTIATION", "No supported capability version.", 422)
    return {
        "version": version,
        "checkout": "dev.ucp.shopping.checkout",
        "ap2_required": require_ap2,
    }
