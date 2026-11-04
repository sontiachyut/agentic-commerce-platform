from concurrent.futures import ThreadPoolExecutor

import httpx2
import pytest

from commerce.domain import DomainError
from commerce.protocol_security import LocalKeys, Recognition


def test_signed_transport_binds_destination_body_and_business_key(system):
    recognition = Recognition(LocalKeys(), system.factory)
    body = b'{"checkout_id":"synthetic"}'
    request = recognition.sign(
        "POST", "https://merchant.example.test/complete?version=1", body, "checkout-key"
    )
    assert recognition.verify(request)["purpose"] == "agent-payer-auth"
    with pytest.raises(DomainError) as failure:
        recognition.verify(request)
    assert failure.value.code == "REPLAYED_REQUEST"
    # A fresh transport nonce permits inquiry/retry under the same business key.
    fresh = recognition.sign("POST", str(request.url), body, "checkout-key")
    assert recognition.verify(fresh)
    for method, url, payload, key, purpose in (
        ("GET", str(request.url), body, "checkout-key", "agent-payer-auth"),
        (
            "POST",
            "https://merchant.example.test/other?version=1",
            body,
            "checkout-key",
            "agent-payer-auth",
        ),
        (
            "POST",
            "https://merchant.example.test/complete?version=2",
            body,
            "checkout-key",
            "agent-payer-auth",
        ),
        ("POST", str(request.url), b"{}", "checkout-key", "agent-payer-auth"),
        ("POST", str(request.url), body, "changed-key", "agent-payer-auth"),
        ("POST", str(request.url), body, "checkout-key", "agent-browser-auth"),
    ):
        changed = httpx2.Request(
            method, url, content=payload, headers=dict(request.headers) | {"idempotency-key": key}
        )
        with pytest.raises(DomainError):
            recognition.verify(changed, purpose=purpose)


def test_concurrent_replay_exactly_one_is_accepted_and_restart_retains_it(system):
    keys = LocalKeys()
    request = Recognition(keys, system.factory).sign(
        "POST", "https://merchant.example.test/complete", b"{}", "same-key"
    )

    def attempt(_):
        try:
            Recognition(keys, system.factory).verify(request)
            return True
        except DomainError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(20))) == 1
    with pytest.raises(DomainError):
        Recognition(keys, system.factory).verify(request)
