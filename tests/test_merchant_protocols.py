import copy

import httpx
import pytest

from commerce.auth import IdentityService
from commerce.domain import DomainError
from commerce.merchant_protocols import (
    VERSIONS,
    MerchantAdapter,
    checkout_state,
    detached_authorization,
    negotiate_ucp,
    schema_validate,
    verify_detached_authorization,
)
from commerce.protocol_security import LocalKeys


def checkout(protocol, status="ready_for_complete"):
    total = {"type": "total", "amount": 350}
    subtotal = {"type": "subtotal", "amount": 350}
    if protocol == "acp":
        total["display_text"] = "Total"
        subtotal["display_text"] = "Subtotal"
    result = {
        "id": "checkout_1",
        "status": status
        if protocol == "ucp"
        else {"ready_for_complete": "ready_for_payment"}.get(status, status),
        "currency": "USD",
        "line_items": [
            {
                "id": "line_1",
                "item": {"id": "bar-cocoa"},
                "quantity": 1,
                "totals": [subtotal, total],
            }
        ],
        "totals": [subtotal, total],
        "messages": [],
        "links": [],
    }
    if protocol == "ucp":
        result["line_items"][0]["item"] |= {"title": "Cocoa bar", "price": 350}
        result["ucp"] = {"version": VERSIONS[protocol], "payment_handlers": {}}
    else:
        result |= {
            "protocol": {"version": VERSIONS[protocol]},
            "fulfillment_options": [],
            "capabilities": {},
        }
    if status == "completed":
        result["order"] = {
            "id": "order_1",
            "checkout_session_id": "checkout_1",
            "permalink_url": "https://merchant.example.test/orders/order_1",
        }
    return result


def inputs(protocol):
    if protocol == "ucp":
        return {"line_items": [{"item": {"id": "bar-cocoa"}, "quantity": 1}]}, {
            "payment": {"instruments": []}
        }
    return {"line_items": [{"id": "bar-cocoa"}], "currency": "USD", "capabilities": {}}, {
        "payment_data": {
            "handler_id": "synthetic",
            "instrument": {
                "type": "wallet",
                "credential": {"type": "synthetic", "token": "not-a-payment-token"},
            },
        }
    }


@pytest.mark.parametrize("protocol", ["ucp", "acp"])
def test_pinned_five_operations_full_response_and_replay(system, protocol):
    calls = []

    def peer(request):
        calls.append((request.method, request.url.path, request.headers.get("idempotency-key")))
        operation = request.url.path.rsplit("/", 1)[-1]
        status = (
            "completed"
            if operation == "complete"
            else "canceled"
            if operation == "cancel"
            else "ready_for_complete"
        )
        return httpx.Response(200, json=checkout(protocol, status))

    box = IdentityService(system.factory, system.settings)
    adapter = MerchantAdapter(
        protocol,
        "http://127.0.0.1:8865",
        factory=system.factory,
        box=box,
        token="synthetic-peer-token",
        transport=httpx.MockTransport(peer),
    )
    create, complete = inputs(protocol)
    for operation, payload in [
        ("create", create),
        ("update", create if protocol == "ucp" else {"line_items": [{"id": "bar-cocoa"}]}),
        ("complete", complete),
        ("cancel", {}),
    ]:
        identifier = None if operation == "create" else "checkout_1"
        value = adapter.command(
            system.actor, operation, payload, "operation-" + operation, checkout_id=identifier
        )
        assert value["id"] == "checkout_1"
        assert (
            adapter.command(
                system.actor, operation, payload, "operation-" + operation, checkout_id=identifier
            )
            == value
        )
    assert adapter.retrieve("checkout_1")["id"] == "checkout_1"
    assert len(calls) == 5
    state = checkout_state(checkout(protocol, "completed"))
    assert (
        state["order_placed"]
        and state["payment_confirmed"] is None
        and state["fulfillment_confirmed"] is None
    )
    with pytest.raises(DomainError):
        adapter.command(system.actor, "create", create | {"currency": "EUR"}, "operation-create")
    adapter.close()
    box.close()


@pytest.mark.parametrize("protocol", ["ucp", "acp"])
def test_lost_completion_response_inquires_original_without_second_post(system, protocol):
    calls = []

    def peer(request):
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("Response lost after merchant commit", request=request)
        return httpx.Response(200, json=checkout(protocol, "completed"))

    box = IdentityService(system.factory, system.settings)
    adapter = MerchantAdapter(
        protocol,
        "http://127.0.0.1:8865",
        factory=system.factory,
        box=box,
        token="synthetic",
        transport=httpx.MockTransport(peer),
    )
    _, complete = inputs(protocol)
    with pytest.raises(DomainError):
        adapter.command(
            system.actor, "complete", complete, "same-business-key", checkout_id="checkout_1"
        )
    observed = adapter.command(
        system.actor, "complete", complete, "same-business-key", checkout_id="checkout_1"
    )
    assert observed["status"] == "completed" and calls == ["POST", "GET"]
    adapter.close()
    box.close()


def test_ucp_ap2_jcs_signature_and_security_lock(system):
    keys = LocalKeys()
    result = checkout("ucp")
    result["ap2"] = {
        "merchant_authorization": detached_authorization(result, keys.keys["merchant"])
    }
    compact, reference = verify_detached_authorization(result, keys.public("merchant"))
    assert reference and len(compact.split(".")) == 3
    reordered = dict(reversed(list(result.items())))
    assert verify_detached_authorization(reordered, keys.public("merchant"))[1] == reference
    changed = copy.deepcopy(result)
    changed["totals"][-1]["amount"] = 1
    with pytest.raises(DomainError):
        verify_detached_authorization(changed, keys.public("merchant"))
    profile = {
        "ucp": {
            "version": VERSIONS["ucp"],
            "capabilities": {"dev.ucp.shopping.checkout": [{"version": VERSIONS["ucp"]}]},
        }
    }
    with pytest.raises(DomainError):
        negotiate_ucp(profile, require_ap2=True)
    box = IdentityService(system.factory, system.settings)
    adapter = MerchantAdapter(
        "ucp",
        "http://127.0.0.1:8865",
        factory=system.factory,
        box=box,
        token="synthetic",
        merchant_key=keys.public("merchant"),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=checkout("ucp"))),
    )
    with pytest.raises(DomainError):
        adapter.retrieve("checkout_1", require_ap2=True)
    adapter.close()
    box.close()


def test_pinned_schemas_reject_wrong_shapes_and_long_acp_keys_are_not_truncated(system):
    with pytest.raises(DomainError):
        schema_validate("acp", "create", "request", {"items": [{"id": "bar-cocoa"}]})
    calls = []

    def peer(request):
        calls.append(request.headers["idempotency-key"])
        return httpx.Response(200, json=checkout("acp"))

    box = IdentityService(system.factory, system.settings)
    adapter = MerchantAdapter(
        "acp",
        "http://127.0.0.1:8865",
        factory=system.factory,
        box=box,
        token="synthetic",
        transport=httpx.MockTransport(peer),
    )
    create, _ = inputs("acp")
    adapter.command(system.actor, "create", create, "a" * 255)
    adapter.command(system.actor, "create", create, "a" * 254 + "b")
    assert calls == ["a" * 255, "a" * 254 + "b"]
    with pytest.raises(DomainError):
        adapter.command(system.actor, "create", create, "a" * 256)
    with pytest.raises(ValueError):
        MerchantAdapter(
            "acp",
            "https://real-merchant.example",
            factory=system.factory,
            box=box,
            token="synthetic",
        )
    adapter.close()
    box.close()
