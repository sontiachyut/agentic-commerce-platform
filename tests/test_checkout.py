import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from commerce.domain import DomainError, outcome
from commerce.models import Approval, Execution, Grant, Order, Product
from commerce.payments import SourceUnavailable
from commerce.schemas import Actor, ExecutionRequest, GrantRequest
from commerce.simulator import SourceCommand


def accept(system, quote, approval, *, profile="none", key="checkout-test-key"):
    return system.service.accept(
        system.actor,
        ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"], fault_profile=profile),
        key,
    )


def drain(system, identifier):
    for _ in range(12):
        try:
            more = system.worker.advance(identifier)
        except SourceUnavailable:
            more = True
        if not more:
            break
    with system.factory() as db:
        return db.get(Execution, identifier)


def test_ac01_full_purchase_requires_captured_payment_and_dispense(system, prepared):
    _, quote, approval = prepared()
    identifier = accept(system, quote, approval)
    execution = drain(system, identifier)
    assert outcome(execution)["success"]
    with system.factory() as db:
        product = db.get(Product, quote["product_id"])
        assert (product.stock, product.reserved) == (7, 0)
        assert db.get(Approval, approval["id"]).state == "CONSUMED"
    with system.source_factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCommand)) == 3


def test_approval_cannot_be_omitted_or_forged(system, prepared):
    _, quote, approval = prepared()
    for request in [
        ExecutionRequest(quote_id=quote["id"]),
        ExecutionRequest(quote_id=quote["id"], approval_id="forged"),
    ]:
        with pytest.raises(DomainError):
            system.service.accept(system.actor, request, "missing-approval-key")
    with pytest.raises(DomainError, match="exact purchase"):
        system.service.approve(system.actor, quote["id"], "0" * 64)
    with system.factory() as db:
        assert db.scalar(select(func.count()).select_from(Execution)) == 0
        assert db.get(Product, quote["product_id"]).reserved == 0


def test_ac03_price_change_requires_fresh_approval(system, prepared):
    _, quote, approval = prepared()
    with system.factory.begin() as db:
        product = db.get(Product, quote["product_id"])
        product.price_minor, product.version = 425, product.version + 1
    with pytest.raises(DomainError) as error:
        accept(system, quote, approval)
    assert error.value.code == "PRICE_CHANGED"
    with system.factory() as db:
        assert db.get(Product, quote["product_id"]).reserved == 0


def test_ac04_postgres_last_item_race(system, prepared):
    purchases = [prepared("last-bar") for _ in range(2)]
    barrier = threading.Barrier(2)

    def race(index):
        _, quote, approval = purchases[index]
        barrier.wait(timeout=5)
        try:
            return accept(system, quote, approval, key=f"stock-race-{index}")
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, [0, 1]))
    assert results.count("OUT_OF_STOCK") == 1
    with system.factory() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert db.get(Product, "last-bar").reserved == 1


def test_ac05_fifty_concurrent_retries_create_one_execution(system, prepared):
    _, quote, approval = prepared()
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: accept(system, quote, approval), range(50)))
    assert len(set(ids)) == 1
    execution = drain(system, ids[0])
    assert execution.state == "COMPLETED"
    with system.factory() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
    with system.source_factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCommand)) == 3


def test_same_execution_key_cannot_select_a_different_checkout(system, prepared):
    _, quote, approval = prepared()
    accept(system, quote, approval)
    _, other, other_approval = prepared("bar-peanut")
    with pytest.raises(DomainError) as error:
        accept(system, other, other_approval)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("mutation", ["expired", "revoked"])
def test_ac06_inactive_approval_cannot_purchase(system, prepared, mutation):
    _, quote, approval = prepared()
    with system.factory.begin() as db:
        row = db.get(Approval, approval["id"])
        if mutation == "expired":
            row.expires_at = 0
        else:
            row.state = "REVOKED"
    with pytest.raises(DomainError):
        accept(system, quote, approval)


@pytest.mark.parametrize(
    "profile,expected_payment",
    [
        ("dispense_failed", "CANCELED"),
        ("captured_dispense_failed", "REFUNDED"),
        ("compensation_response_lost", "CANCELED"),
        ("payment_declined", "DECLINED"),
    ],
)
def test_ac07_failure_compensates_original_payment(system, prepared, profile, expected_payment):
    _, quote, approval = prepared()
    identifier = accept(system, quote, approval, profile=profile)
    execution = drain(system, identifier)
    assert execution.state == "CANCELED"
    assert execution.payment_state == expected_payment
    assert not outcome(execution)["success"]
    with system.factory() as db:
        product = db.get(Product, quote["product_id"])
        assert (product.stock, product.reserved) == (8, 0)


def test_dispensed_but_capture_declined_never_delivers_again(system, prepared):
    _, quote, approval = prepared()
    identifier = accept(system, quote, approval, profile="capture_declined")
    execution = drain(system, identifier)
    assert execution.state == "RECOVERY_REQUIRED"
    assert execution.fulfillment_state == "DISPENSED"
    assert not outcome(execution)["success"]
    for _ in range(3):
        system.worker.advance(identifier)
    with system.source_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(SourceCommand)
                .where(SourceCommand.action == "dispense")
            )
            == 1
        )


@pytest.mark.parametrize(
    "profile,unknown_field",
    [
        ("payment_response_lost", "payment_state"),
        ("dispense_response_lost", "fulfillment_state"),
        ("capture_response_lost", "payment_state"),
    ],
)
def test_ac08_lost_response_is_recovered_from_independent_source(
    system, prepared, profile, unknown_field
):
    _, quote, approval = prepared()
    identifier = accept(system, quote, approval, profile=profile)
    seen_unknown = False
    for _ in range(6):
        try:
            system.worker.advance(identifier)
        except SourceUnavailable:
            with system.factory() as db:
                execution = db.get(Execution, identifier)
                assert getattr(execution, unknown_field) == "UNKNOWN"
                assert not outcome(execution)["success"]
                assert db.get(Product, quote["product_id"]).reserved == 1
            # Simulate losing all in-process commerce state while source rows survive.
            from commerce.worker import Worker

            system.worker = Worker(system.factory, system.settings, system.worker.source)
            seen_unknown = True
    assert seen_unknown
    assert drain(system, identifier).state == "COMPLETED"
    with system.source_factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCommand)) == 3


def test_ac10_other_user_cannot_approve_or_execute(system, prepared):
    session_id, quote, approval = prepared()
    sam = Actor(user_id="sam")
    for action in [
        lambda: system.service.approve(sam, quote["id"], quote["digest"]),
        lambda: system.service.accept(
            sam,
            ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"]),
            "sam-attempt-key",
        ),
        lambda: system.service.session_detail(sam, session_id),
    ]:
        with pytest.raises(DomainError) as error:
            action()
        assert error.value.status == 404


def test_ac02_atomic_delegated_budget_includes_pending_purchases(system, prepared):
    grant = system.service.create_grant(
        system.actor,
        GrantRequest(
            product_ids=["bar-cocoa", "bar-peanut"],
            per_purchase_minor=400,
            total_minor=700,
            max_purchases=3,
        ),
    )
    quotes = [prepared(p)[1] for p in ["bar-cocoa", "bar-peanut"]]
    barrier = threading.Barrier(2)

    def race(index):
        barrier.wait(timeout=5)
        try:
            return system.service.accept(
                system.actor,
                ExecutionRequest(
                    quote_id=quotes[index]["id"],
                    grant_id=grant["id"],
                    grant_version=grant["version"],
                ),
                f"budget-race-{index}",
            )
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, [0, 1]))
    assert results.count("GRANT_EXHAUSTED") == 1
    with system.factory() as db:
        row = db.get(Grant, grant["id"])
        assert row.held_minor in {350, 375}
        assert row.held_count == 1


def test_revoked_grant_and_forbidden_product_fail_closed(system, prepared):
    grant = system.service.create_grant(
        system.actor,
        GrantRequest(product_ids=["bar-cocoa"], per_purchase_minor=400, total_minor=700),
    )
    _, quote, _ = prepared("bar-peanut")
    with pytest.raises(DomainError) as error:
        system.service.accept(
            system.actor,
            ExecutionRequest(quote_id=quote["id"], grant_id=grant["id"], grant_version=1),
            "scope-test-key",
        )
    assert error.value.code == "GRANT_SCOPE"
    system.service.revoke_grant(system.actor, grant["id"])
    _, quote, _ = prepared()
    with pytest.raises(DomainError) as error:
        system.service.accept(
            system.actor,
            ExecutionRequest(quote_id=quote["id"], grant_id=grant["id"], grant_version=1),
            "revoked-test-key",
        )
    assert error.value.code == "GRANT_INACTIVE"


def test_unknown_source_never_releases_inventory(system, prepared):
    _, quote, approval = prepared()
    identifier = accept(system, quote, approval, profile="source_unavailable")
    with pytest.raises(SourceUnavailable):
        system.worker.advance(identifier)
    with system.factory() as db:
        assert db.get(Product, quote["product_id"]).reserved == 1
        assert db.get(Execution, identifier).payment_state == "UNKNOWN"
