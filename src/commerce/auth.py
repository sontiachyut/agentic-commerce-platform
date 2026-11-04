"""Revocable local sessions and an OIDC backend-for-frontend boundary."""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from authlib.integrations.httpx_client import OAuth2Client
from authlib.oauth2.rfc6749 import OAuth2Error
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request
from sqlalchemy import select

from commerce.models import BrowserSession, LoginAttempt
from commerce.schemas import Actor


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class Principal:
    actor: Actor
    csrf: str | None
    session_id: str | None
    issuer: str
    scopes: list[str]
    expires_at: int
    auth_method: str


class IdentityService:
    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.http = httpx.Client(timeout=5, follow_redirects=False, trust_env=False)
        self._metadata, self._keys, self._cached_at = None, None, 0
        self.box = AESGCM(
            hmac.digest(
                settings.signing_key.get_secret_value().encode(), b"identity-secrets-v1", "sha256"
            )
        )

    def close(self):
        self.http.close()

    def seal(self, value):
        nonce = secrets.token_bytes(12)
        return base64.urlsafe_b64encode(
            nonce + self.box.encrypt(nonce, json.dumps(value).encode(), b"commerce-identity-v1")
        ).decode()

    def unseal(self, value):
        raw = base64.urlsafe_b64decode(value)
        return json.loads(self.box.decrypt(raw[:12], raw[12:], b"commerce-identity-v1"))

    def provider(self):
        now = time.time()
        if self._metadata and self._keys and now - self._cached_at < 300:
            return self._metadata, self._keys
        issuer = self.settings.oidc_issuer.rstrip("/")
        response = self.http.get(issuer + "/.well-known/openid-configuration")
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("issuer") != issuer:
            raise ValueError("Untrusted issuer metadata")
        origin = urlparse(issuer)
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            target = urlparse(metadata[field])
            if (
                (target.scheme, target.netloc) != (origin.scheme, origin.netloc)
                or target.username
                or target.fragment
            ):
                raise ValueError("Untrusted identity endpoint")
            if target.scheme != "https" and not (
                target.scheme == "http" and target.hostname in {"127.0.0.1", "localhost"}
            ):
                raise ValueError("Identity transport requires TLS except for local development")
        keys = self.http.get(metadata["jwks_uri"])
        keys.raise_for_status()
        if len(keys.content) > 131072:
            raise ValueError("Oversized key set")
        self._metadata, self._keys, self._cached_at = metadata, keys.json(), now
        return self._metadata, self._keys

    def decode(self, encoded: str, audience: str):
        if len(encoded) > 32768:
            raise ValueError("Oversized identity token")
        header = jwt.get_unverified_header(encoded)
        if (
            header.get("alg") != "RS256"
            or not isinstance(header.get("kid"), str)
            or header.get("crit")
        ):
            raise ValueError("Unsupported identity signing profile")
        _, keys = self.provider()
        matching = [
            k
            for k in keys.get("keys", [])
            if k.get("kid") == header["kid"]
            and k.get("kty") == "RSA"
            and k.get("use", "sig") == "sig"
            and k.get("alg", "RS256") == "RS256"
        ]
        if len(matching) != 1:
            # One bounded refetch supports key rotation; never follow token-supplied URLs.
            self._cached_at = 0
            _, keys = self.provider()
            matching = [
                k
                for k in keys.get("keys", [])
                if k.get("kid") == header["kid"]
                and k.get("kty") == "RSA"
                and k.get("use", "sig") == "sig"
                and k.get("alg", "RS256") == "RS256"
            ]
        if len(matching) != 1:
            raise ValueError("Unknown identity signing key")
        key = jwt.PyJWK(matching[0], algorithm="RS256").key
        if key.key_size < 2048:
            raise ValueError("Insufficient signing key size")
        claims = jwt.decode(
            encoded,
            key,
            algorithms=["RS256"],
            audience=audience,
            issuer=self.settings.oidc_issuer.rstrip("/"),
            leeway=30,
            options={"require": ["iss", "sub", "aud", "exp", "iat"]},
        )
        if not isinstance(claims["sub"], str) or not claims["sub"] or len(claims["sub"]) > 200:
            raise ValueError("Invalid subject")
        return claims

    def actor_from_claims(self, claims):
        tenant = claims.get("tenant_id")
        if not isinstance(tenant, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", tenant
        ):
            raise ValueError("Account has no valid tenant membership")
        membership = claims.get("realm_access", {})
        roles = membership.get("roles", []) if isinstance(membership, dict) else []
        if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
            raise ValueError("Invalid role membership")
        if "commerce-operator" not in roles and "commerce-shopper" not in roles:
            raise ValueError("Account is not provisioned for commerce")
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, claims["iss"] + "\x00" + claims["sub"]))
        name = claims.get("preferred_username") or claims.get("name") or "Shopper"
        if not isinstance(name, str):
            name = "Shopper"
        return Actor(
            user_id=identifier,
            tenant_id=tenant,
            role="operator" if "commerce-operator" in roles else "shopper",
            display_name=name[:80],
        )

    def issue_session(self, actor, *, issuer="local-demo", subject=None, tokens=None):
        raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        now = time.time()
        with self.factory.begin() as db:
            db.add(
                BrowserSession(
                    id=token_hash(raw),
                    actor=actor.model_dump(),
                    csrf=csrf,
                    auth_source="oidc" if tokens else "demo",
                    issuer=issuer,
                    subject=subject or actor.user_id,
                    expires_at=now + self.settings.session_ttl_seconds,
                    token_expires_at=now + tokens.get("expires_in", 300) if tokens else None,
                    encrypted_tokens=self.seal(tokens) if tokens else None,
                    revoked=False,
                )
            )
        return raw, csrf

    def oauth_client(self):
        return OAuth2Client(
            self.settings.oidc_client_id,
            self.settings.oidc_client_secret.get_secret_value(),
            code_challenge_method="S256",
            timeout=5,
            follow_redirects=False,
            trust_env=False,
        )

    def start_login(self):
        metadata, _ = self.provider()
        state, binding, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
        with self.factory.begin() as db:
            db.add(
                LoginAttempt(
                    id=token_hash(state),
                    browser_binding=token_hash(binding),
                    nonce=nonce,
                    encrypted_verifier=self.seal(verifier),
                    expires_at=time.time() + 300,
                    consumed=False,
                )
            )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        url = (
            metadata["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.oidc_client_id,
                    "response_type": "code",
                    "scope": "openid profile commerce:read commerce:write",
                    "redirect_uri": self.settings.public_base_url + "/api/v1/auth/callback",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        return url, binding

    def finish_login(self, state, code, binding):
        if not state or not code or not binding or len(state) > 200 or len(code) > 4096:
            raise HTTPException(400, "Invalid login response")
        with self.factory.begin() as db:
            row = db.scalar(
                select(LoginAttempt).where(LoginAttempt.id == token_hash(state)).with_for_update()
            )
            if (
                not row
                or row.consumed
                or row.expires_at <= time.time()
                or not hmac.compare_digest(row.browser_binding, token_hash(binding))
            ):
                raise HTTPException(400, "Login state is invalid, expired or already used")
            verifier, nonce = self.unseal(row.encrypted_verifier), row.nonce
            row.consumed = True
        try:
            metadata, _ = self.provider()
            with self.oauth_client() as client:
                tokens = client.fetch_token(
                    metadata["token_endpoint"],
                    grant_type="authorization_code",
                    code=code,
                    code_verifier=verifier,
                    redirect_uri=self.settings.public_base_url + "/api/v1/auth/callback",
                )
            identity = self.decode(tokens["id_token"], self.settings.oidc_client_id)
            if not hmac.compare_digest(identity.get("nonce", ""), nonce):
                raise ValueError("Nonce mismatch")
            audiences = identity["aud"]
            if (
                identity.get("azp", self.settings.oidc_client_id) != self.settings.oidc_client_id
                or isinstance(audiences, list)
                and len(audiences) > 1
                and identity.get("azp") != self.settings.oidc_client_id
            ):
                raise ValueError("Authorized party mismatch")
            if "at_hash" in identity:
                expected = (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(tokens["access_token"].encode()).digest()[:16]
                    )
                    .rstrip(b"=")
                    .decode()
                )
                if not hmac.compare_digest(identity["at_hash"], expected):
                    raise ValueError("Access-token hash mismatch")
            access = self.decode(tokens["access_token"], self.settings.oidc_api_audience)
            if access["sub"] != identity["sub"]:
                raise ValueError("Subject mismatch")
            actor = self.actor_from_claims(access)
            raw, csrf = self.issue_session(
                actor, issuer=identity["iss"], subject=identity["sub"], tokens=tokens
            )
            return raw, csrf, actor
        except (
            ValueError,
            KeyError,
            TypeError,
            InvalidTag,
            OAuth2Error,
            jwt.PyJWTError,
            httpx.HTTPError,
        ) as exc:
            logging.getLogger(__name__).warning(
                "identity_verification_failed category=%s missing_claim=%s",
                type(exc).__name__,
                getattr(exc, "claim", "none"),
            )
            raise HTTPException(401, "Identity verification failed. Start sign-in again.") from exc

    def session_principal(self, token):
        with self.factory.begin() as db:
            row = db.scalar(
                select(BrowserSession)
                .where(BrowserSession.id == token_hash(token))
                .with_for_update()
            )
            if (
                not row
                or row.revoked
                or row.expires_at <= time.time()
                or row.auth_source != self.settings.auth_mode
                or (
                    row.auth_source == "oidc"
                    and row.issuer != self.settings.oidc_issuer.rstrip("/")
                )
            ):
                return None
            if row.auth_source == "oidc" and row.token_expires_at <= time.time() + 20:
                # A short, bounded lock serializes refresh-token rotation. It holds no commerce locks.
                try:
                    previous = self.unseal(row.encrypted_tokens)
                    if not previous.get("refresh_token"):
                        raise ValueError("No refresh grant")
                    metadata, _ = self.provider()
                    with self.oauth_client() as client:
                        tokens = client.refresh_token(
                            metadata["token_endpoint"], refresh_token=previous["refresh_token"]
                        )
                    claims = self.decode(tokens["access_token"], self.settings.oidc_api_audience)
                    if claims["sub"] != row.subject:
                        raise ValueError("Subject changed")
                    row.actor = self.actor_from_claims(claims).model_dump()
                    if "refresh_token" not in tokens:
                        tokens["refresh_token"] = previous["refresh_token"]
                    row.encrypted_tokens = self.seal(tokens)
                    row.token_expires_at = time.time() + tokens.get("expires_in", 300)
                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    InvalidTag,
                    OAuth2Error,
                    jwt.PyJWTError,
                    httpx.HTTPError,
                ):
                    row.revoked = True
                    return None
            return Principal(
                Actor.model_validate(row.actor),
                row.csrf,
                row.id,
                row.issuer,
                ["commerce:read", "commerce:write"],
                int(row.expires_at),
                "session",
            )

    def bearer_principal(self, token, resource=None):
        session = (
            self.session_principal(token)
            if not resource or self.settings.auth_mode == "demo"
            else None
        )
        if session:
            return session
        if self.settings.auth_mode != "oidc":
            return None
        try:
            claims = self.decode(token, resource or self.settings.oidc_api_audience)
            scopes = claims.get("scope", "").split()
            if "commerce:read" not in scopes:
                return None
            return Principal(
                self.actor_from_claims(claims),
                None,
                None,
                claims["iss"],
                scopes,
                int(claims["exp"]),
                "bearer",
            )
        except (
            ValueError,
            KeyError,
            TypeError,
            InvalidTag,
            OAuth2Error,
            jwt.PyJWTError,
            httpx.HTTPError,
        ):
            return None

    def authenticate(self, request: Request):
        authorization = request.headers.get("authorization")
        if authorization:
            scheme, _, token = authorization.partition(" ")
            principal = (
                self.bearer_principal(token) if scheme.lower() == "bearer" and token else None
            )
        else:
            principal = self.session_principal(request.cookies.get("commerce_session", ""))
        if principal is None:
            raise HTTPException(401, "Sign in to continue")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if "commerce:write" not in principal.scopes:
                raise HTTPException(403, "Write permission required")
            if not authorization and not hmac.compare_digest(
                request.headers.get("x-csrf-token", ""), principal.csrf or ""
            ):
                raise HTTPException(403, "CSRF token required")
        request.state.principal = principal
        request.state.actor = principal.actor
        return principal.actor

    def revoke(self, principal):
        if principal.session_id:
            with self.factory.begin() as db:
                row = db.get(BrowserSession, principal.session_id)
                if row:
                    row.revoked = True
                    row.encrypted_tokens = None
