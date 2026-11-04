import threading
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import func, select, text

from commerce.domain import DomainError
from commerce.models import Approval, AuditEvent, Grant, PurchaseSession
from commerce.planner import ModelUnavailable
from commerce.schemas import Actor, ExecutionRequest, Intent
from commerce.service import own, record


class ShoppingState(TypedDict, total=False):
    session_id: str
    intent: dict
    candidates: list[dict]
    selection: dict
    quote: dict
    stopped: bool
    execution_id: str


class ShoppingAgent:
    def __init__(self, service, planner, checkpointer, engine):
        self.service, self.planner, self.engine = service, planner, engine
        self.local_lock = threading.Lock()
        graph = StateGraph(ShoppingState)
        graph.add_node("interpret", self.interpret)
        graph.add_node("discover", self.discover)
        graph.add_node("select", self.select_product)
        graph.add_node("quote", self.prepare_quote)
        graph.add_node("approval", self.await_approval)
        graph.add_node("execute", self.execute)
        graph.add_edge(START, "interpret")
        graph.add_conditional_edges("interpret", lambda s: END if s.get("stopped") else "discover")
        graph.add_conditional_edges("discover", lambda s: END if s.get("stopped") else "select")
        graph.add_conditional_edges("select", lambda s: END if s.get("stopped") else "quote")
        graph.add_edge("quote", "approval")
        graph.add_edge("approval", "execute")
        graph.add_edge("execute", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    def actor_and_session(self, session_id):
        with self.service.factory() as db:
            session = db.get(PurchaseSession, session_id)
            return Actor(user_id=session.user_id, tenant_id=session.tenant_id), session

    def event(self, session_id, name, **data):
        actor, _ = self.actor_and_session(session_id)
        with self.service.factory.begin() as db:
            record(db, actor, session_id, name, **data)

    def stop(self, session_id, message, state="CLARIFICATION_REQUIRED"):
        with self.service.factory.begin() as db:
            session = db.get(PurchaseSession, session_id)
            session.state, session.message = state, message
        return {"stopped": True}

    def interpret(self, state):
        actor, session = self.actor_and_session(state["session_id"])
        self.reserve_model_call(session.id, "intent")
        intent = self.planner.intent(session.original_request)
        with self.service.factory.begin() as db:
            row = db.get(PurchaseSession, session.id)
            row.intent = intent.model_dump()
            record(
                db,
                actor,
                session.id,
                "agent.intent",
                provider=self.planner.name,
                clarification=bool(intent.clarification),
                usage=getattr(self.planner, "last_usage", {}),
            )
        if intent.clarification:
            return {"intent": intent.model_dump(), **self.stop(session.id, intent.clarification)}
        if intent.kiosk_id != "kiosk-a":
            return {
                "intent": intent.model_dump(),
                **self.stop(
                    session.id,
                    "This workspace supports Kiosk A only. No purchase was requested.",
                    "POLICY_DENIED",
                ),
            }
        if intent.max_amount_minor is None:
            return {
                "intent": intent.model_dump(),
                **self.stop(session.id, "What is your maximum spending limit?"),
            }
        return {"intent": intent.model_dump(), "stopped": False}

    def discover(self, state):
        actor, _ = self.actor_and_session(state["session_id"])
        intent = Intent.model_validate(state["intent"])
        candidates = self.service.catalog(actor, intent.kiosk_id, intent)
        self.event(state["session_id"], "tool.search_products", count=len(candidates))
        if not candidates:
            return {
                "candidates": [],
                **self.stop(
                    state["session_id"],
                    "No available item matches this request and budget. Try a different product or limit.",
                    "NO_MATCH",
                ),
            }
        return {"candidates": candidates}

    def select_product(self, state):
        self.reserve_model_call(state["session_id"], "selection")
        selection = self.planner.select(Intent.model_validate(state["intent"]), state["candidates"])
        self.event(
            state["session_id"],
            "agent.selection",
            product_id=selection.product_id,
            usage=getattr(self.planner, "last_usage", {}),
        )
        if selection.clarification or selection.product_id is None:
            return {
                "selection": selection.model_dump(),
                **self.stop(
                    state["session_id"],
                    selection.clarification or "Please clarify which product you prefer.",
                ),
            }
        if selection.product_id not in {p["id"] for p in state["candidates"]}:
            self.event(state["session_id"], "policy.denied", code="INVENTED_PRODUCT")
            return self.stop(
                state["session_id"],
                "The model proposed an ineligible product. No purchase was requested.",
                "POLICY_DENIED",
            )
        return {"selection": selection.model_dump()}

    def reserve_model_call(self, session_id, purpose):
        if self.planner.name != "codex":
            return
        actor, _ = self.actor_and_session(session_id)
        with self.service.factory.begin() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(91470332)"))
            day_start = int(time.time() // 86400) * 86400
            daily = db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "model.call_reserved",
                    AuditEvent.created_at >= day_start,
                )
            )
            per_session = db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "model.call_reserved",
                    AuditEvent.resource_id == session_id,
                )
            )
            if (
                daily >= self.service.settings.max_daily_model_calls
                or per_session >= self.service.settings.max_model_calls_per_session
            ):
                raise ModelUnavailable("The configured local model-call budget is exhausted")
            record(db, actor, session_id, "model.call_reserved", purpose=purpose, provider="codex")

    def prepare_quote(self, state):
        actor, _ = self.actor_and_session(state["session_id"])
        quote = self.service.quote(actor, state["session_id"], state["selection"]["product_id"])
        self.event(state["session_id"], "tool.get_quote", quote_id=quote["id"])
        return {"quote": quote}

    def await_approval(self, state):
        actor, session = self.actor_and_session(state["session_id"])
        if session.grant_id:
            # The backend still checks the current grant at acceptance.
            return {}
        with self.service.factory() as db:
            approval = db.scalar(
                select(Approval).where(
                    Approval.quote_id == state["quote"]["id"],
                    Approval.state.in_(["ACTIVE", "CONSUMED"]),
                )
            )
        if approval is None:
            interrupt(
                {
                    "kind": "purchase_approval",
                    "quote_id": state["quote"]["id"],
                    "digest": state["quote"]["digest"],
                }
            )
        # A resume value does not confer approval. execute() reloads the trusted record.
        return {}

    def execute(self, state):
        actor, session = self.actor_and_session(state["session_id"])
        with self.service.factory() as db:
            approval = db.scalar(select(Approval).where(Approval.quote_id == state["quote"]["id"]))
            grant = own(db.get(Grant, session.grant_id), actor) if session.grant_id else None
            request = ExecutionRequest(
                quote_id=state["quote"]["id"],
                approval_id=approval.id if approval and not grant else None,
                grant_id=grant.id if grant else None,
                grant_version=grant.version if grant else None,
            )
        execution_id = self.service.accept(actor, request, "agent:" + session.id)
        self.event(session.id, "tool.request_checkout_execution", execution_id=execution_id)
        return {"execution_id": execution_id}

    def run(self, session_id):
        # Serialize graph checkpoint writes across API processes, not just threads.
        # One dedicated autocommit connection holds a session advisory lock, never
        # a transaction or inventory row lock, while a model call is in progress.
        with (
            self.local_lock,
            self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock,
        ):
            acquired = lock.scalar(text("SELECT pg_try_advisory_lock(91470331)"))
            if not acquired:
                raise ModelUnavailable("Another graph runner owns checkpoint execution")
            try:
                config = {"configurable": {"thread_id": session_id}, "recursion_limit": 12}
                snapshot = self.graph.get_state(config)
                if snapshot.next:
                    value = Command(resume={"recheck_trusted_approval": True})
                elif snapshot.values:
                    return
                else:
                    value = {"session_id": session_id}
                self.graph.invoke(value, config)
            except ModelUnavailable:
                self.stop(
                    session_id,
                    "The model is unavailable. Check your local Codex sign-in or usage allowance and retry.",
                    "MODEL_UNAVAILABLE",
                )
                raise
            except DomainError as exc:
                self.event(session_id, "policy.denied", code=exc.code)
                self.stop(session_id, exc.message, "POLICY_DENIED")
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(91470331)"))
