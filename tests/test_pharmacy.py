from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from commerce.domain import DomainError
from commerce.pharmacy.fixtures import ensure_demo
from commerce.pharmacy.models import (
    FamilyMember,
    FamilyOrder,
    PickupPermission,
    RoutineItem,
)
from commerce.pharmacy.planner import FamilyBaseline
from commerce.pharmacy.schemas import PermissionInput, PickupInput, StaffAction
from commerce.pharmacy.service import PharmacyService
from commerce.pharmacy.worker import PharmacyWorker
from commerce.pharmacy.workflow import FamilyWorkflow
from commerce.schemas import Actor
from commerce.simulator import SourceCommand


@pytest.fixture
def pharmacy(system):
    service = PharmacyService(
        system.factory,
        system.settings,
        clock=lambda: datetime.fromisoformat("2026-11-04T18:05:00-07:00").timestamp(),
    )
    service.workspace(system.actor)
    staff = Actor(user_id="pharmacy-team", role="operator")
    ensure_demo(system.factory, staff)
    workflow = FamilyWorkflow(service, FamilyBaseline(), InMemorySaver())
    worker = PharmacyWorker(service, workflow, system.worker.source)
    return service, workflow, worker, staff


def request(
    service,
    actor,
    workflow,
    permission=True,
    text="Order the regular medicines for my dad, mom, sister and myself nearest home, up to $50",
):
    if permission:
        service.create_permission(
            actor,
            PermissionInput(
                members=["self", "dad", "mom", "sister"], per_order_minor=5000, total_minor=15000
            ),
        )
    identifier = service.create_request(
        actor, PickupInput(text=text), "family-test-request-" + __import__("uuid").uuid4().hex
    )
    workflow.run(identifier)
    return identifier


def test_complete_family_customer_staff_and_pickup_flow(system, pharmacy):
    service, workflow, worker, staff = pharmacy
    identifier = request(service, system.actor, workflow)
    detail = service.request_detail(system.actor, identifier)
    assert len(detail["quote"]["terms"]["lines"]) == 4
    assert detail["quote"]["terms"]["amount_minor"] == 4098
    assert detail["quote"]["terms"]["facility"]["name"] == "Cedar Square"
    assert not detail["quote"]["terms"]["alternatives"][0]["eligible"]
    assert detail["order"]["state"] == "PAYMENT_PENDING"
    assert worker.advance_once()
    detail = service.request_detail(system.actor, identifier)
    order = detail["order"]
    assert detail["state"] == "ORDERED" and order["payment_state"] == "AUTHORIZED"
    assert order["pickup_code"] is None
    with system.source_factory() as db:
        assert not db.get(SourceCommand, order["id"] + ":capture")
    with pytest.raises(DomainError):
        service.staff_action(
            system.actor, order["id"], StaffAction(action="ready", clinical_review_confirmed=True)
        )
    with pytest.raises(DomainError):
        service.staff_action(staff, order["id"], StaffAction(action="ready"))
    service.staff_action(
        staff, order["id"], StaffAction(action="ready", clinical_review_confirmed=True)
    )
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).available_at = 0
    assert worker.advance_once()
    detail = service.request_detail(system.actor, identifier)
    order = detail["order"]
    assert (
        order["state"] == "READY_FOR_PICKUP"
        and order["payment_state"] == "CAPTURED"
        and order["pickup_code"]
    )
    with pytest.raises(DomainError):
        service.staff_action(
            staff, order["id"], StaffAction(action="collect", pickup_code="incorrect")
        )
    service.staff_action(
        staff, order["id"], StaffAction(action="collect", pickup_code=order["pickup_code"])
    )
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).available_at = 0
    worker.advance_once()
    final = service.request_detail(system.actor, identifier)
    assert final["state"] == "PICKED_UP" and final["order"]["fulfillment_state"] == "PICKED_UP"
    with system.factory() as db:
        grant = db.get(PickupPermission, db.get(FamilyOrder, order["id"]).permission_id)
        assert (grant.held_minor, grant.spent_minor) == (0, 4098)


@pytest.mark.parametrize(
    "change", [("coverage", "PENDING"), ("eligibility", "TOO_SOON"), ("refills_remaining", 0)]
)
def test_prescription_blockers_do_not_create_order_or_money_effect(system, pharmacy, change):
    service, workflow, _, _ = pharmacy
    with system.factory.begin() as db:
        item = db.scalar(select(RoutineItem).where(RoutineItem.kind == "RX"))
        setattr(item, *change)
    identifier = request(service, system.actor, workflow)
    assert service.request_detail(system.actor, identifier)["state"] == "BLOCKED"
    with system.factory() as db:
        assert not db.scalars(select(FamilyOrder)).all()
    with system.source_factory() as db:
        assert not db.scalars(select(SourceCommand)).all()


def test_no_standing_permission_waits_for_exact_consent_and_duplicate_acceptance_is_one(
    system, pharmacy
):
    service, workflow, _, _ = pharmacy
    identifier = request(service, system.actor, workflow, permission=False)
    detail = service.request_detail(system.actor, identifier)
    assert detail["state"] == "AWAITING_APPROVAL" and not detail["order"]
    quote = detail["quote"]
    permission = service.create_permission(
        system.actor,
        PermissionInput(
            members=["self", "dad", "mom", "sister"],
            per_order_minor=4098,
            total_minor=4098,
            max_orders=1,
        ),
        exact_quote=quote["id"],
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        orders = list(
            pool.map(
                lambda _: service.accept(
                    system.actor, quote["id"], permission["id"], quote["digest"]
                ),
                range(20),
            )
        )
    assert len(set(orders)) == 1


def test_requested_budget_tightening_and_access_revocation_are_enforced(system, pharmacy):
    service, workflow, _, _ = pharmacy
    identifier = request(
        service, system.actor, workflow, text="Order regular medicines for my family under $40.98"
    )
    assert service.request_detail(system.actor, identifier)["state"] == "BUDGET_EXCEEDED"
    with system.factory() as db:
        assert not db.scalars(select(FamilyOrder)).all()
    identifier = request(service, system.actor, workflow, permission=False)
    order = service.request_detail(system.actor, identifier)["order"]
    with system.factory.begin() as db:
        mother = db.scalar(select(FamilyMember).where(FamilyMember.alias == "mom"))
        mother.access_approved = False
        mother.access_version += 1
    masked = service.request_detail(system.actor, identifier)
    assert any(line["kind"] == "HIDDEN" for line in masked["quote"]["terms"]["lines"])
    _, _, worker, staff = pharmacy
    worker.advance_once()
    with pytest.raises(DomainError):
        service.staff_action(
            staff, order["id"], StaffAction(action="ready", clinical_review_confirmed=True)
        )
    with pytest.raises(DomainError):
        service.request_detail(Actor(user_id="other-user"), identifier)


def test_unknown_authorization_inquires_without_duplicate_and_rejection_releases_holds(
    system, pharmacy
):
    service, workflow, worker, staff = pharmacy
    identifier = request(service, system.actor, workflow)
    order = service.request_detail(system.actor, identifier)["order"]
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).fault_profile = "payment_response_lost"
    worker.advance_once()
    assert service.request_detail(system.actor, identifier)["order"]["state"] == "PAYMENT_PENDING"
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).available_at = 0
    worker.advance_once()
    assert (
        service.request_detail(system.actor, identifier)["order"]["payment_state"] == "AUTHORIZED"
    )
    service.staff_action(staff, order["id"], StaffAction(action="reject"))
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).available_at = 0
    worker.advance_once()
    assert service.request_detail(system.actor, identifier)["state"] == "CANCELED"
    with system.factory() as db:
        assert all(r.refills_held == 0 for r in db.scalars(select(RoutineItem)))
        assert all(p.held_minor == 0 for p in db.scalars(select(PickupPermission)))
    with system.source_factory() as db:
        assert len(db.scalars(select(SourceCommand)).all()) == 2


def test_competing_family_quotes_cannot_reserve_same_refill_twice(system, pharmacy):
    service, workflow, _, _ = pharmacy
    first = request(service, system.actor, workflow, permission=False)
    second = request(service, system.actor, workflow, permission=False)
    quotes = [service.request_detail(system.actor, i)["quote"] for i in (first, second)]
    permission = service.create_permission(
        system.actor,
        PermissionInput(
            members=["self", "dad", "mom", "sister"], per_order_minor=5000, total_minor=15000
        ),
    )

    def accept(quote):
        try:
            return service.accept(system.actor, quote["id"], permission["id"])
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(accept, quotes))
    assert outcomes.count("REFILL_ALREADY_REQUESTED") == 1
    with system.factory() as db:
        assert len(db.scalars(select(FamilyOrder)).all()) == 1
        assert all(
            r.refills_held == 1
            for r in db.scalars(select(RoutineItem).where(RoutineItem.kind == "RX"))
        )
        grant = db.get(PickupPermission, permission["id"])
        assert (grant.held_count, grant.held_minor) == (1, 4098)


def test_capture_response_loss_is_inquired_and_does_not_prematurely_claim_ready(system, pharmacy):
    service, workflow, worker, staff = pharmacy
    identifier = request(service, system.actor, workflow)
    order = service.request_detail(system.actor, identifier)["order"]
    worker.advance_once()
    service.staff_action(
        staff, order["id"], StaffAction(action="ready", clinical_review_confirmed=True)
    )
    with system.factory.begin() as db:
        row = db.get(FamilyOrder, order["id"])
        row.available_at, row.fault_profile = 0, "capture_response_lost"
    worker.advance_once()
    uncertain = service.request_detail(system.actor, identifier)["order"]
    assert uncertain["state"] == "CAPTURE_PENDING"
    assert uncertain["pickup_code"] is None
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).available_at = 0
    worker.advance_once()
    ready = service.request_detail(system.actor, identifier)["order"]
    assert ready["state"] == "READY_FOR_PICKUP" and ready["payment_state"] == "CAPTURED"
    with system.source_factory() as db:
        commands = db.scalars(select(SourceCommand)).all()
        assert len(commands) == 2  # One authorization and one capture, including the lost response.


def test_revoked_permission_blocks_staff_capture_and_rejection_releases_budget(system, pharmacy):
    service, workflow, worker, staff = pharmacy
    identifier = request(service, system.actor, workflow)
    order = service.request_detail(system.actor, identifier)["order"]
    worker.advance_once()
    with system.factory() as db:
        permission_id = db.get(FamilyOrder, order["id"]).permission_id
    service.revoke_permission(system.actor, permission_id)
    with pytest.raises(DomainError) as exc:
        service.staff_action(
            staff, order["id"], StaffAction(action="ready", clinical_review_confirmed=True)
        )
    assert exc.value.code == "PERMISSION_CHANGED"
    with system.source_factory() as db:
        assert not db.get(SourceCommand, order["id"] + ":capture")
    service.staff_action(staff, order["id"], StaffAction(action="reject"))
    with system.factory.begin() as db:
        db.get(FamilyOrder, order["id"]).available_at = 0
    worker.advance_once()
    assert service.request_detail(system.actor, identifier)["state"] == "CANCELED"


def test_pharmacy_api_identity_csrf_cancel_voice_limits_and_read_only_mcp(system):
    import io
    import wave

    from fastapi.testclient import TestClient

    from commerce.api import create_app

    system.settings.product_mode = "pharmacy"
    system.settings.voice_enabled = False
    system.settings.pharmacy_demo_minute = 1085
    app = create_app(system.settings, checkpointer=InMemorySaver(), source=system.worker.source)
    with TestClient(app) as client:
        assert client.get("/api/v1/product").json()["mode"] == "pharmacy"
        assert client.get("/api/v1/pharmacy/workspace").status_code == 401
        login = client.post("/api/v1/auth/demo", json={"persona": "alex"}).json()
        headers = {"X-CSRF-Token": login["csrf_token"], "Idempotency-Key": "pharmacy-api-request"}
        assert client.get("/api/v1/catalog").status_code == 404
        assert client.get("/api/v1/pharmacy/staff").status_code == 403
        assert (
            client.post(
                "/api/v1/pharmacy/requests", json={"text": "My family up to $50"}
            ).status_code
            == 403
        )
        body = {"text": "My family up to $50"}
        first = client.post("/api/v1/pharmacy/requests", json=body, headers=headers)
        second = client.post("/api/v1/pharmacy/requests", json=body, headers=headers)
        assert first.status_code == 202 and first.json() == second.json()
        identifier = first.json()["request_id"]
        assert (
            client.post(
                f"/api/v1/pharmacy/requests/{identifier}/cancel", headers=headers
            ).status_code
            == 200
        )
        app.state.pharmacy_worker.plan_once()
        app.state.pharmacy.stop(identifier, "BLOCKED", "late worker message")
        assert client.get(f"/api/v1/pharmacy/requests/{identifier}").json()["state"] == "CANCELED"
        assert (
            client.post(
                "/api/v1/pharmacy/voice/transcribe", content=b"x" * 1440045, headers=headers
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/v1/pharmacy/voice/transcribe", content=b"not a WAV", headers=headers
            ).status_code
            == 422
        )
        valid_audio = io.BytesIO()
        with wave.open(valid_audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(bytes(16000))
        unavailable = client.post(
            "/api/v1/pharmacy/voice/transcribe", content=valid_audio.getvalue(), headers=headers
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "VOICE_UNAVAILABLE"
        tools = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer " + client.cookies["commerce_session"],
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        ).json()
        assert {tool["name"] for tool in tools["result"]["tools"]} == {
            "get_family_regulars",
            "get_family_pickup_status",
        }
        client.post("/api/v1/auth/demo", json={"persona": "sam"})
        assert client.get(f"/api/v1/pharmacy/requests/{identifier}").status_code == 404


def test_spoken_updates_are_derived_from_owned_current_status_not_client_prose(system):
    from fastapi.testclient import TestClient

    from commerce.api import create_app

    system.settings.product_mode = "pharmacy"
    system.settings.pharmacy_demo_minute = 1085
    app = create_app(system.settings, checkpointer=InMemorySaver(), source=system.worker.source)
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/demo", json={"persona": "alex"}).json()
        headers = {"X-CSRF-Token": login["csrf_token"], "Idempotency-Key": "spoken-status-request"}
        identifier = client.post(
            "/api/v1/pharmacy/requests", json={"text": "Order my family up to $35"}, headers=headers
        ).json()["request_id"]
        app.state.pharmacy_worker.plan_once()
        calls = []

        def speak(text):
            calls.append(text)
            return {"text": text, "engine": "test-boundary"}

        app.state.speaker.speak = speak
        path = f"/api/v1/pharmacy/requests/{identifier}/speech"
        assert client.post(path, json={"state": "ORDERED"}, headers=headers).status_code == 409
        assert (
            client.post(
                path,
                json={"state": "BUDGET_EXCEEDED", "text": "Your payment succeeded"},
                headers=headers,
            ).status_code
            == 422
        )
        assert calls == []
        response = client.post(path, json={"state": "BUDGET_EXCEEDED"}, headers=headers)
        assert response.status_code == 200 and "40.98" in calls[0]
        client.post("/api/v1/auth/demo", json={"persona": "sam"})
        assert (
            client.post(
                path,
                json={"state": "BUDGET_EXCEEDED"},
                headers={"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]},
            ).status_code
            == 404
        )
        assert len(calls) == 1
