import time

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from commerce.api import create_app
from commerce.models import Execution
from commerce.schemas import ExecutionRequest


def test_scrape_identity_is_read_only_and_exposes_stuck_purchase_without_identifiers(
    system, prepared
):
    _, quote, approval = prepared()
    execution = system.service.accept(
        system.actor,
        ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"]),
        "metrics-stuck-purchase",
    )
    with system.factory.begin() as db:
        db.get(Execution, execution).created_at = time.time() - 180
    system.settings.metrics_token = SecretStr("local-scrape-test-only-" * 3)
    app = create_app(system.settings, checkpointer=InMemorySaver(), source=system.worker.source)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + system.settings.metrics_token.get_secret_value()}
        assert client.get("/internal/metrics").status_code == 401
        response = client.get("/internal/metrics", headers=headers)
        assert response.status_code == 200
        assert "commerce_oldest_pending_execution_seconds 18" in response.text
        assert execution not in response.text and quote["id"] not in response.text
        assert client.get("/api/v1/operator/overview", headers=headers).status_code == 401
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 401
