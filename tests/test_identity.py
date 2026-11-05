import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from commerce.api import create_app
from commerce.auth import IdentityService, token_hash
from commerce.models import BrowserSession, LoginAttempt
from commerce.schemas import Actor


def test_sessions_are_opaque_revocable_and_cannot_cross_auth_modes(system):
    identity = IdentityService(system.factory, system.settings)
    token, _ = identity.issue_session(system.actor)
    with system.factory() as db:
        row = db.get(BrowserSession, token_hash(token))
        assert row and row.id != token
    principal = identity.session_principal(token)
    assert principal.actor == system.actor
    identity.revoke(principal)
    assert identity.session_principal(token) is None
    another, _ = identity.issue_session(system.actor)
    system.settings.auth_mode = "oidc"
    assert identity.session_principal(another) is None
    assert identity.bearer_principal(another, resource="http://127.0.0.1:8510/mcp") is None
    identity.close()


def test_invalid_authorization_never_falls_back_to_valid_cookie(system):
    app = create_app(system.settings, checkpointer=InMemorySaver(), source=system.worker.source)
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/demo", json={"persona": "alex"}).json()
        token = client.cookies["commerce_session"]
        assert (
            client.get("/api/v1/catalog", headers={"Authorization": "Bearer invalid"}).status_code
            == 401
        )
        assert client.post("/api/v1/auth/logout").status_code == 403
        assert (
            client.post(
                "/api/v1/auth/logout", headers={"X-CSRF-Token": login["csrf_token"]}
            ).status_code
            == 200
        )
        assert (
            client.get("/api/v1/catalog", headers={"Authorization": "Bearer " + token}).status_code
            == 401
        )


def test_oidc_pkce_state_is_browser_bound_expiring_and_single_use(system, monkeypatch):
    identity = IdentityService(system.factory, system.settings)
    monkeypatch.setattr(
        identity,
        "provider",
        lambda: ({"authorization_endpoint": system.settings.oidc_issuer + "/auth"}, {}),
    )
    location, binding = identity.start_login()
    parameters = parse_qs(urlparse(location).query)
    assert parameters["code_challenge_method"] == ["S256"]
    assert len(parameters["code_challenge"][0]) == 43
    state = parameters["state"][0]
    with pytest.raises(HTTPException) as error:
        identity.finish_login(state, "synthetic-code", "different-browser")
    assert error.value.status_code == 400
    with system.factory.begin() as db:
        attempt = db.get(LoginAttempt, token_hash(state))
        assert not attempt.consumed and attempt.encrypted_verifier
        attempt.expires_at = time.time() - 1
    with pytest.raises(HTTPException):
        identity.finish_login(state, "synthetic-code", binding)
    identity.close()


def test_trusted_jwt_profile_and_tenant_roles(system, monkeypatch):
    identity = IdentityService(system.factory, system.settings)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "trusted"}
    monkeypatch.setattr(identity, "provider", lambda: ({}, {"keys": [jwk]}))
    claims = {
        "iss": system.settings.oidc_issuer,
        "sub": "subject-a",
        "aud": "commerce-api",
        "iat": int(time.time()),
        "exp": int(time.time()) + 120,
        "tenant_id": "demo",
        "realm_access": {"roles": ["commerce-shopper"]},
    }

    def encode(value, signing_key=key):
        return jwt.encode(value, signing_key, algorithm="RS256", headers={"kid": "trusted"})

    actor = identity.actor_from_claims(identity.decode(encode(claims), "commerce-api"))
    assert actor.tenant_id == "demo" and actor.role == "shopper"
    for changed in (
        {"aud": "different"},
        {"iss": "https://attacker.test"},
        {"exp": int(time.time()) - 60},
    ):
        with pytest.raises(jwt.PyJWTError):
            identity.decode(encode(claims | changed), "commerce-api")
    with pytest.raises(jwt.PyJWTError):
        identity.decode(
            encode(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048)),
            "commerce-api",
        )
    with pytest.raises(ValueError):
        identity.actor_from_claims(claims | {"tenant_id": ""})
    with pytest.raises(ValueError):
        identity.actor_from_claims(claims | {"realm_access": {"roles": []}})
    other = identity.actor_from_claims(claims | {"tenant_id": "studio-b"})
    assert other.user_id == actor.user_id and other.tenant_id != actor.tenant_id
    session = system.service.create_session(actor, "Buy water under $3", "tenant-isolation-oidc")
    from commerce.domain import DomainError

    with pytest.raises(DomainError):
        system.service.session_detail(other, session)
    identity.close()


def test_server_stores_provider_tokens_encrypted_and_refresh_failure_revokes(system, monkeypatch):
    system.settings.auth_mode = "oidc"
    identity = IdentityService(system.factory, system.settings)
    token, _ = identity.issue_session(
        Actor(user_id="synthetic"),
        issuer=system.settings.oidc_issuer,
        tokens={
            "access_token": "sensitive-access",
            "refresh_token": "sensitive-refresh",
            "expires_in": -1,
        },
    )
    with system.factory() as db:
        row = db.scalar(select(BrowserSession))
        assert "sensitive" not in row.encrypted_tokens
    monkeypatch.setattr(
        identity, "provider", lambda: (_ for _ in ()).throw(ValueError("Provider unavailable"))
    )
    assert identity.session_principal(token) is None
    with system.factory() as db:
        assert db.scalar(select(BrowserSession)).revoked
    identity.close()
