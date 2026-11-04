import time

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import func, select, text

from commerce.agent import ShoppingAgent
from commerce.domain import DomainError
from commerce.models import AuditEvent, Execution, Job, Product
from commerce.planner import BaselinePlanner, ModelUnavailable
from commerce.schemas import ExecutionRequest
from commerce.simulator import SourceCommand, SourceRequest


def test_postgres_checkpoint_survives_connection_and_agent_recreation(system):
    with system.engine.begin() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS agent_checkpoints_test"))
    dsn = system.settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    identifier = system.service.create_session(
        system.actor, "A cocoa protein bar under $4", "durable-graph-key"
    )
    with psycopg.connect(
        dsn, autocommit=True, prepare_threshold=0, options="-csearch_path=agent_checkpoints_test"
    ) as connection:
        saver = PostgresSaver(connection)
        saver.setup()
        first = ShoppingAgent(system.service, BaselinePlanner(), saver, system.engine)
        first.run(identifier)
    before = system.service.session_detail(system.actor, identifier)
    assert before["state"] == "AWAITING_APPROVAL"
    quote = before["quote"]
    system.service.approve(system.actor, quote["id"], quote["digest"])
    with psycopg.connect(
        dsn, autocommit=True, prepare_threshold=0, options="-csearch_path=agent_checkpoints_test"
    ) as connection:
        second = ShoppingAgent(
            system.service, BaselinePlanner(), PostgresSaver(connection), system.engine
        )
        second.run(identifier)
    after = system.service.session_detail(system.actor, identifier)
    assert after["execution"]["quote_id"] == quote["id"]
    assert after["execution"]["state"] == "EXECUTING"


def test_expired_worker_lease_recovers_original_effect(system, prepared):
    _, quote, approval = prepared()
    identifier = system.service.accept(
        system.actor,
        ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"]),
        "lease-recovery-key",
    )
    system.source.command(
        SourceRequest(
            execution_id=identifier,
            action="authorize",
            amount_minor=quote["amount_minor"],
            currency="USD",
            quote_digest=quote["digest"],
        )
    )
    with system.factory.begin() as db:
        job = db.scalar(select(Job).where(Job.kind == "EXECUTION", Job.resource_id == identifier))
        job.state, job.lease_until, job.lease_token = "RUNNING", time.time() - 1, "old-owner"
    system.worker.kinds = {"EXECUTION"}
    assert system.worker.tick()
    with system.factory() as db:
        assert db.get(Execution, identifier).stage == "DISPENSE"
    with system.source_factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCommand)) == 1


def test_admission_is_bounded_and_idempotent_retry_does_not_consume_a_slot(system):
    system.settings.max_active_sessions_per_user = 1
    identifier = system.service.create_session(
        system.actor, "A protein bar under $4", "first-queue-key"
    )
    assert (
        system.service.create_session(system.actor, "A protein bar under $4", "first-queue-key")
        == identifier
    )
    with pytest.raises(DomainError) as error:
        system.service.create_session(system.actor, "A protein bar under $4", "second-queue-key")
    assert error.value.status == 429


def test_subscription_model_budget_is_durable_and_failed_calls_do_not_auto_retry(system):
    class SubscriptionFixture(BaselinePlanner):
        name = "codex"
        calls = 0

        def intent(self, text):
            self.calls += 1
            raise ModelUnavailable("Synthetic model quota exhausted")

    planner = SubscriptionFixture()
    agent = ShoppingAgent(system.service, planner, InMemorySaver(), system.engine)
    system.worker.agent, system.worker.kinds = agent, {"AGENT"}
    identifier = system.service.create_session(
        system.actor, "A protein bar under $4", "quota-test-key"
    )
    system.worker.tick()
    assert planner.calls == 1
    assert not system.worker.tick()
    with system.factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "model.call_reserved")
            )
            == 1
        )
        assert db.scalar(select(Job).where(Job.resource_id == identifier)).state == "NEEDS_REVIEW"


def test_daily_model_budget_stops_before_a_second_actual_call(system):
    class SubscriptionFixture(BaselinePlanner):
        name = "codex"
        selection_calls = 0

        def select(self, intent, candidates):
            self.selection_calls += 1
            return super().select(intent, candidates)

    system.settings.max_daily_model_calls = 1
    planner = SubscriptionFixture()
    agent = ShoppingAgent(system.service, planner, InMemorySaver(), system.engine)
    identifier = system.service.create_session(
        system.actor, "A protein bar under $4", "daily-quota-key"
    )
    with pytest.raises(ModelUnavailable):
        agent.run(identifier)
    assert planner.selection_calls == 0
    assert system.service.session_detail(system.actor, identifier)["state"] == "MODEL_UNAVAILABLE"


def test_database_rejects_negative_inventory_even_outside_application_checks(system):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), system.factory.begin() as db:
        db.get(Product, "last-bar").reserved = 2


def test_completed_execution_does_not_exhaust_active_session_admission(system, prepared):
    from commerce.schemas import ExecutionRequest

    system.settings.max_active_sessions_per_user = 1
    _, quote, approval = prepared()
    identifier = system.service.accept(
        system.actor,
        ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"]),
        "completed-admission-key",
    )
    for _ in range(3):
        system.worker.advance(identifier)
    with system.factory() as db:
        from commerce.models import Execution

        assert db.get(Execution, identifier).state == "COMPLETED"
    assert system.service.create_session(
        system.actor, "Buy water under $3", "after-completed-purchase"
    )
