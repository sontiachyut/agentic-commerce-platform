import copy
import time

import pytest
from jwcrypto.jws import InvalidJWSSignature

from commerce.ap2_profile import AP2Profile
from commerce.models import Grant, Quote
from commerce.protocol_security import LocalKeys
from commerce.schemas import GrantRequest


@pytest.mark.parametrize("delegated", [False, True])
def test_sdk_signed_mandates_bind_merchant_exact_terms_and_authority(system, prepared, delegated):
    _, quote_dict, _ = prepared()
    with system.factory() as db:
        quote = db.get(Quote, quote_dict["id"])
    grant = None
    if delegated:
        value = system.service.create_grant(
            system.actor,
            GrantRequest(
                product_ids=[quote.product_id],
                per_purchase_minor=400,
                total_minor=800,
                max_purchases=2,
            ),
        )
        with system.factory() as db:
            grant = db.get(Grant, value["id"])
    profile = AP2Profile(LocalKeys())
    bundle = profile.create(quote, grant)
    verified = profile.verify(bundle, quote, expected_nonce=bundle["nonce"], grant=grant)
    assert verified["amount_minor"] == 350
    with pytest.raises(ValueError):
        profile.verify(bundle, quote, expected_nonce="wrong-nonce", grant=grant)
    quote.amount_minor = 351
    with pytest.raises(ValueError):
        profile.verify(bundle, quote, expected_nonce=bundle["nonce"], grant=grant)


def test_mandates_reject_other_wallet_tampering_expiry_and_unknown_claims(system, prepared):
    _, value, _ = prepared()
    with system.factory() as db:
        quote = db.get(Quote, value["id"])
    profile = AP2Profile(LocalKeys())
    bundle = profile.create(quote)
    with pytest.raises((ValueError, InvalidJWSSignature)):
        AP2Profile(LocalKeys()).verify(bundle, quote, expected_nonce=bundle["nonce"])
    altered = copy.deepcopy(bundle)
    altered["payment"][0] = altered["checkout"][0]
    with pytest.raises(ValueError):
        profile.verify(altered, quote, expected_nonce=bundle["nonce"])
    quote.expires_at = time.time() - 60
    expired = profile.create(quote)
    with pytest.raises((ValueError, InvalidJWSSignature)):
        profile.verify(expired, quote, expected_nonce=expired["nonce"])


def test_delegated_constraints_stop_unsupported_product_budget_and_use_count(system, prepared):
    _, value, _ = prepared()
    with system.factory() as db:
        quote = db.get(Quote, value["id"])
    request = GrantRequest(
        product_ids=[quote.product_id], per_purchase_minor=400, total_minor=800, max_purchases=2
    )
    result = system.service.create_grant(system.actor, request)
    with system.factory() as db:
        grant = db.get(Grant, result["id"])
    profile = AP2Profile(LocalKeys())
    for field, change in (
        ("product_ids", ["water"]),
        ("per_purchase_minor", 100),
        ("spent_count", 2),
        ("spent_minor", 700),
    ):
        prior = getattr(grant, field)
        setattr(grant, field, change)
        bundle = profile.create(quote, grant)
        with pytest.raises(ValueError):
            profile.verify(bundle, quote, expected_nonce=bundle["nonce"], grant=grant)
        setattr(grant, field, prior)
