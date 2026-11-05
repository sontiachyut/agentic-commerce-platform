from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from commerce.domain import DomainError
from commerce.model_budget import reserve_call
from commerce.pharmacy.models import PickupRequest
from commerce.pharmacy.schemas import FamilyIntent
from commerce.service import record


class FamilyState(TypedDict, total=False):
    request_id: str
    intent: dict
    quote_id: str | None


class FamilyWorkflow:
    def __init__(self, service, planner, checkpointer):
        self.service, self.planner = service, planner
        graph = StateGraph(FamilyState)
        graph.add_node("understand", self.understand)
        graph.add_node("prepare", self.prepare)
        graph.add_node("place", self.place)
        graph.add_edge(START, "understand")
        graph.add_edge("understand", "prepare")
        graph.add_conditional_edges(
            "prepare", lambda state: "place" if state.get("quote_id") else END
        )
        graph.add_edge("place", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    def understand(self, state):
        actor, row = self.service.request_context(state["request_id"])
        if row.intent:
            return {"intent": row.intent}
        reserve_call(
            self.service.factory,
            self.service.settings,
            actor,
            row.id,
            "pharmacy-intent",
            self.planner.name,
        )
        intent = self.planner.family_intent(row.text)
        with self.service.factory.begin() as db:
            db.get(PickupRequest, row.id).intent = intent.model_dump()
            record(
                db,
                actor,
                row.id,
                "pharmacy.intent_understood",
                members=len(intent.members),
                clarification=bool(intent.clarification),
                provider=self.planner.name,
                usage=getattr(self.planner, "last_usage", {}),
            )
        return {"intent": intent.model_dump()}

    def prepare(self, state):
        actor, _ = self.service.request_context(state["request_id"])
        quote = self.service.prepare_quote(
            actor, state["request_id"], FamilyIntent.model_validate(state["intent"])
        )
        with self.service.factory() as db:
            if db.get(PickupRequest, state["request_id"]).state == "BUDGET_EXCEEDED":
                quote = None
        return {"quote_id": quote}

    def place(self, state):
        actor, _ = self.service.request_context(state["request_id"])
        try:
            self.service.accept(actor, state["quote_id"])
        except DomainError as exc:
            if exc.code == "PERMISSION_REQUIRED":
                self.service.stop(state["request_id"], "AWAITING_APPROVAL", exc.message)
            else:
                self.service.stop(state["request_id"], "BLOCKED", exc.message)
        return {}

    def run(self, identifier):
        self.graph.invoke(
            {"request_id": identifier},
            {"configurable": {"thread_id": "pharmacy:" + identifier}, "recursion_limit": 8},
        )
