import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from commerce.agent import ShoppingAgent
from commerce.domain import DomainError
from commerce.models import Execution, PurchaseSession
from commerce.planner import BaselinePlanner
from commerce.schemas import ExecutionRequest, Intent


@pytest.mark.parametrize(
    "phrase,expected",
    [("under", "lt"), ("below", "lt"), ("less than", "lt"), ("up to", "lte"), ("at most", "lte")],
)
def test_budget_operator_survives_interpretation_and_database_gate(system, phrase, expected):
    request = f"Buy a cocoa protein bar {phrase} $3.50 at Kiosk A"
    intent = BaselinePlanner().intent(request)
    assert intent.budget_comparison == expected
    identifier = system.service.create_session(
        system.actor, request, "boundary-" + expected + "-" + phrase
    )
    with system.factory.begin() as db:
        db.get(PurchaseSession, identifier).intent = intent.model_dump()
    if expected == "lt":
        with pytest.raises(DomainError) as error:
            system.service.quote(system.actor, identifier, "bar-cocoa")
        assert error.value.code == "OVER_BUDGET"
    else:
        assert system.service.quote(system.actor, identifier, "bar-cocoa")["amount_minor"] == 350


@pytest.mark.parametrize(
    "shopping_request", ["Buy a protein bar under €4", "Buy two protein bars under $8"]
)
def test_unsupported_currency_or_quantity_never_produces_checkout(system, shopping_request):
    identifier = system.service.create_session(
        system.actor, shopping_request, "unsupported-request"
    )
    agent = ShoppingAgent(system.service, BaselinePlanner(), InMemorySaver(), system.engine)
    agent.run(identifier)
    detail = system.service.session_detail(system.actor, identifier)
    assert detail["state"] == "CLARIFICATION_REQUIRED"
    assert detail["quote"] is None and detail["execution"] is None


def test_acceptance_rechecks_original_budget_even_with_approval(system, prepared):
    identifier, quote, approval = prepared()
    with system.factory.begin() as db:
        db.get(PurchaseSession, identifier).intent = Intent(
            max_amount_minor=350, budget_comparison="lt"
        ).model_dump()
    with pytest.raises(DomainError) as error:
        system.service.accept(
            system.actor,
            ExecutionRequest(quote_id=quote["id"], approval_id=approval["id"]),
            "strict-acceptance-key",
        )
    assert error.value.code == "REQUEST_CONSTRAINT"
    with system.factory() as db:
        assert db.scalar(select(Execution)) is None
