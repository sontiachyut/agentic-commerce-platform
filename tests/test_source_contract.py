import json

import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from commerce.observability import LocalExporter
from commerce.payments import HttpSource, SourceConflict, SourceUnavailable
from commerce.simulator import SourceRequest, create_source_app


def command():
    return SourceRequest(
        execution_id="00000000-0000-0000-0000-000000000001",
        action="authorize",
        amount_minor=350,
        currency="USD",
        quote_digest="a" * 64,
    )


def observation(request):
    return {
        "execution_id": request.execution_id,
        "action": request.action,
        "amount_minor": request.amount_minor,
        "currency": request.currency,
        "quote_digest": request.quote_digest,
        "command_id": f"{request.execution_id}:{request.action}",
        "source": "local-stateful-simulator-v1",
        "state": "AUTHORIZED",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount_minor", 1),
        ("currency", "EUR"),
        ("execution_id", "other"),
        ("quote_digest", "b" * 64),
        ("action", "capture"),
        ("source", "untrusted"),
        ("command_id", "invented"),
    ],
)
def test_mismatched_source_observation_is_rejected(system, field, value):
    request = command()
    result = observation(request)
    result[field] = value
    source = HttpSource(system.settings)
    source.client.close()
    source.client = httpx.Client(
        base_url="http://source.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=result)),
    )
    with pytest.raises(SourceConflict):
        source.observe_or_send(request)
    source.close()


def test_missing_observation_reuses_same_command_identity(system):
    request = command()
    calls = []

    def respond(http_request):
        calls.append(http_request)
        if http_request.method == "GET":
            return httpx.Response(404)
        assert json.loads(http_request.content)["execution_id"] == request.execution_id
        return httpx.Response(200, json=observation(request))

    source = HttpSource(system.settings)
    source.client.close()
    source.client = httpx.Client(
        base_url="http://source.test", transport=httpx.MockTransport(respond)
    )
    assert source.observe_or_send(request)["state"] == "AUTHORIZED"
    assert [c.method for c in calls] == ["GET", "POST"]
    source.close()


def test_source_outage_is_not_a_decline(system):
    source = HttpSource(system.settings)
    source.client.close()
    source.client = httpx.Client(
        base_url="http://source.test", transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    with pytest.raises(SourceUnavailable):
        source.observe_or_send(command())
    source.close()


def test_source_api_requires_service_auth_and_persists_effect_before_lost_response(system):
    app = create_source_app(system.settings)
    with TestClient(app) as client:
        request = command()
        assert client.post("/v1/commands", json=request.model_dump()).status_code == 401
        headers = {"Authorization": "Bearer " + system.settings.source_token.get_secret_value()}
        lost = request.model_copy(update={"fault_profile": "payment_response_lost"})
        assert (
            client.post("/v1/commands", json=lost.model_dump(), headers=headers).status_code == 503
        )
        observed = client.get(f"/v1/commands/{request.execution_id}/authorize", headers=headers)
        assert observed.json()["state"] == "AUTHORIZED"
        assert (
            client.post("/v1/commands", json=lost.model_dump(), headers=headers).json()
            == observed.json()
        )


def test_trace_exporter_drops_unapproved_payloads_and_keeps_files_private(tmp_path):
    path = tmp_path / "private" / "traces.jsonl"
    exporter = LocalExporter(path)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("test").start_as_current_span("safe-span") as span:
        span.set_attribute("http.route", "/api/v1/sessions")
        span.set_attribute("user.prompt", "SYNTHETIC_PRIVATE_CANARY")
        span.set_attribute("authorization", "SYNTHETIC_SERVICE_SECRET")
    data = path.read_text()
    assert "CANARY" not in data and "SERVICE_SECRET" not in data
    assert json.loads(data)["attributes"]["http.route"] == "/api/v1/sessions"
    assert path.stat().st_mode & 0o777 == 0o600
    provider.shutdown()


def test_unknown_source_state_requires_review_without_retries(system, prepared):
    from sqlalchemy import select

    from commerce.models import Execution, Job, Product
    from commerce.schemas import ExecutionRequest

    _, quote, approval = prepared()
    identifier = system.service.accept(
        system.actor,
        ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"]),
        "invalid-source-state",
    )

    class InvalidState:
        def observe_or_send(self, request):
            return {"state": "MAYBE_PAID"}

    system.worker.source = InvalidState()
    system.worker.kinds = {"EXECUTION"}
    assert system.worker.tick()
    with system.factory() as db:
        execution = db.get(Execution, identifier)
        job = db.scalar(select(Job).where(Job.resource_id == identifier, Job.kind == "EXECUTION"))
        product = db.get(Product, quote["product_id"])
        assert execution.state == "RECOVERY_REQUIRED"
        assert execution.failure_code == "SOURCE_CONFLICT"
        assert job.state == "DONE"
        assert product.reserved == 1
        assert not system.worker.advance(identifier)
