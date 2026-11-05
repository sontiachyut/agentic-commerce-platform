"""Local trust registry and durable transport replay protection.

This is an RFC 9421 local profile using TAP purpose tags, not Visa enrollment.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from http_message_signatures import HTTPMessageSigner, HTTPMessageVerifier
from http_message_signatures.algorithms import ED25519
from http_message_signatures.resolvers import HTTPSignatureKeyResolver
from jwcrypto.jwk import JWK
from sqlalchemy.dialects.postgresql import insert

from commerce.domain import DomainError
from commerce.models import ReplayNonce

COVERED = (
    "@method",
    "@authority",
    "@path",
    "@query",
    "content-type",
    "signature-agent",
    "idempotency-key",
    "content-digest",
)


def b64digest(value: str | bytes):
    return (
        base64.urlsafe_b64encode(
            hashlib.sha256(value.encode() if isinstance(value, str) else value).digest()
        )
        .rstrip(b"=")
        .decode()
    )


class LocalKeys(HTTPSignatureKeyResolver):
    """Explicit allowlist; no token-supplied URLs or certificate roots are trusted."""

    def __init__(self, path: Path | None = None):
        self.keys = {}
        if path and path.exists():
            raw = json.loads(path.read_text())
        else:
            raw = {
                role: json.loads(
                    JWK.generate(
                        kty="EC", crv="P-256", kid="local-" + role + "-v1"
                    ).export_private()
                )
                for role in ("wallet", "merchant", "delegate")
            }
            raw["recognition"] = base64.b64encode(
                Ed25519PrivateKey.generate().private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
            ).decode()
            if path:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as output:
                    json.dump(raw, output)
        self.keys = {role: JWK(**raw[role]) for role in ("wallet", "merchant", "delegate")}
        self.recognition = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(raw["recognition"])
        )

    def public(self, role):
        return JWK(**json.loads(self.keys[role].export_public()))

    def resolve_private_key(self, key_id):
        if key_id != "local-agent-recognition-v1":
            raise ValueError("Unknown recognition key")
        return self.recognition

    def resolve_public_key(self, key_id):
        return self.resolve_private_key(key_id).public_key()


class ReplayStore:
    def __init__(self, factory):
        self.factory = factory

    def consume(self, namespace, nonce, expires_at):
        now = time.time()
        if not isinstance(nonce, str) or not 16 <= len(nonce) <= 200 or expires_at <= now:
            raise DomainError("INVALID_NONCE", "Invalid or expired transport nonce.", 403)
        # Keep digests beyond the signature lifetime. Cleanup must retain the full accepted window.
        with self.factory.begin() as db:
            inserted = db.execute(
                insert(ReplayNonce)
                .values(
                    id=b64digest(namespace + "\x00" + nonce),
                    expires_at=expires_at,
                )
                .on_conflict_do_nothing()
                .returning(ReplayNonce.id)
            ).scalar_one_or_none()
        if not inserted:
            raise DomainError("REPLAYED_REQUEST", "This signed request was already received.", 409)


class Recognition:
    def __init__(self, keys, factory, *, authority="merchant.example.test"):
        self.keys, self.store, self.authority = keys, ReplayStore(factory), authority

    def sign(self, method, url, body, request_key, purpose="agent-payer-auth"):
        request = httpx2.Request(
            method,
            url,
            headers={
                "Content-Type": "application/json",
                "Signature-Agent": "https://agent.example.test",
                "Idempotency-Key": request_key,
            },
            content=body,
        )
        now = datetime.now(UTC)
        HTTPMessageSigner(signature_algorithm=ED25519, key_resolver=self.keys).sign(
            request,
            key_id="local-agent-recognition-v1",
            created=now - timedelta(seconds=1),
            expires=now + timedelta(minutes=3),
            nonce=secrets.token_urlsafe(24),
            tag=purpose,
            covered_component_ids=COVERED,
            body=body,
        )
        return request

    def verify(self, request, *, purpose="agent-payer-auth"):
        try:
            if (
                str(request.url.netloc.decode()) != self.authority
                or request.headers.get("signature-agent") != "https://agent.example.test"
            ):
                raise ValueError("Wrong destination or agent")
            if purpose not in {"agent-payer-auth", "agent-browser-auth"}:
                raise ValueError("Unsupported purpose")
            result = HTTPMessageVerifier(
                signature_algorithm=ED25519, key_resolver=self.keys
            ).verify(
                request,
                expect_tag=purpose,
                require_components=COVERED,
                body=request.content,
                max_age=timedelta(minutes=8),
            )
            if len(result) != 1:
                raise ValueError("Exactly one recognized signature required")
            parameters = result[0].parameters
            now = time.time()
            created, expires = parameters["created"], parameters["expires"]
            if (
                not now - 480 <= created <= now + 5
                or not created < expires <= created + 480
                or expires <= now
            ):
                raise ValueError("Signature outside lifetime")
            self.store.consume("recognition:" + parameters["keyid"], parameters["nonce"], expires)
            return {"agent": "local-shopping-agent", "purpose": purpose}
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "UNRECOGNIZED_AGENT", "Signed agent request could not be verified.", 403
            ) from exc
