from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from commerce.auth import IdentityService
from commerce.domain import DomainError
from commerce.models import Execution, ProtocolEnvelope
from commerce.protocol_gateway import ProtocolGateway
from commerce.protocol_security import LocalKeys, b64digest
from commerce.schemas import Actor, GrantRequest


def gateway(system):
    return ProtocolGateway(
        system.service, IdentityService(system.factory, system.settings), LocalKeys()
    )


def test_signed_checkout_fifty_retries_one_execution_and_receipts_wait_for_sources(
    system, prepared
):
    _, quote, _ = prepared()
    adapter = gateway(system)
    envelope = adapter.authorize(system.actor, quote["id"], quote_digest=quote["digest"])[
        "envelope_id"
    ]
    with pytest.raises(DomainError):
        adapter.receipts(system.actor, envelope)
    with ThreadPoolExecutor(max_workers=8) as pool:
        executions = list(
            pool.map(
                lambda _: adapter.execute(system.actor, envelope, "signed-concurrent-key"),
                range(50),
            )
        )
    assert len(set(executions)) == 1
    for _ in range(4):
        system.worker.advance(executions[0])
    receipts = adapter.receipts(system.actor, envelope)
    bundle = adapter.bundle(system.actor, envelope)
    verified = adapter.verify_receipt(
        receipts["checkout_receipt"],
        kind="local-checkout-receipt+jwt",
        reference=b64digest(bundle["checkout"][-1]),
    )
    assert verified["status"] == "Success"
    with pytest.raises(ValueError):
        adapter.verify_receipt(
            receipts["payment_receipt"],
            kind="local-checkout-receipt+jwt",
            reference=b64digest(bundle["checkout"][-1]),
        )
    with system.factory() as db:
        stored = db.get(ProtocolEnvelope, envelope)
        assert bundle["checkout"][0] not in stored.encrypted_bundle
        assert len(db.scalars(select(Execution)).all()) == 1
    adapter.identity.close()


def test_signed_authority_does_not_bypass_owner_or_current_grant_revocation(system, prepared):
    _, quote, _ = prepared()
    permission = system.service.create_grant(
        system.actor,
        GrantRequest(
            product_ids=["bar-cocoa"], per_purchase_minor=400, total_minor=800, max_purchases=2
        ),
    )
    adapter = gateway(system)
    envelope = adapter.authorize(
        system.actor, quote["id"], grant_id=permission["id"], grant_version=permission["version"]
    )["envelope_id"]
    with pytest.raises(DomainError):
        adapter.execute(Actor(user_id="sam"), envelope, "other-owner-signed")
    system.service.revoke_grant(system.actor, permission["id"])
    with pytest.raises(DomainError):
        adapter.execute(system.actor, envelope, "revoked-signed-key")
    with system.factory() as db:
        assert not db.scalars(select(Execution)).all()
    adapter.identity.close()
