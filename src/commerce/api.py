import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres import PostgresSaver
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commerce.agent import ShoppingAgent
from commerce.auth import IdentityService
from commerce.boundary import Boundary
from commerce.config import Settings, get_settings
from commerce.db import make_engine, make_sessions
from commerce.domain import DomainError
from commerce.metrics import refresh_workflow_metrics
from commerce.models import (
    Approval,
    AuditEvent,
    Execution,
    Grant,
    Job,
    Product,
    ProtocolEnvelope,
    PurchaseSession,
)
from commerce.observability import configure_tracing
from commerce.payments import HttpSource
from commerce.pharmacy.api import register_pharmacy
from commerce.pharmacy.planner import FamilyBaseline, FamilyCodex
from commerce.pharmacy.service import PharmacyService
from commerce.pharmacy.worker import PharmacyWorker
from commerce.pharmacy.workflow import FamilyWorkflow
from commerce.planner import BaselinePlanner, CodexPlanner
from commerce.protocol_gateway import ProtocolGateway
from commerce.protocol_security import LocalKeys
from commerce.schemas import (
    Actor,
    ApprovalRequest,
    ExecutionRequest,
    GrantRequest,
    LoginRequest,
    PriceUpdate,
    SessionRequest,
)
from commerce.service import CommerceService, enqueue, own, record, seed
from commerce.worker import Worker

REQUESTS = Counter("commerce_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("commerce_http_request_seconds", "HTTP latency", ["route"])
log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, checkpointer=None, planner=None, source=None):
    settings = settings or get_settings()
    settings.require_secrets()
    engine = make_engine(settings.database_url)
    factory = make_sessions(engine)
    service = CommerceService(factory, settings)
    pharmacy = PharmacyService(factory, settings)
    identity_service = IdentityService(factory, settings)
    protocol_gateway = ProtocolGateway(
        service, identity_service, LocalKeys(Path(".local/protocol-keys.json"))
    )

    @asynccontextmanager
    async def lifespan(app):
        configure_tracing(settings.trace_enabled)
        if settings.product_mode == "retail":
            seed(factory)
        connection = None
        try:
            if checkpointer is None:
                # Checkpoint tables have a distinct namespace and no business authority.
                if settings.schema_bootstrap:
                    with engine.begin() as db:
                        db.execute(text("CREATE SCHEMA IF NOT EXISTS agent_checkpoints"))
                connection = psycopg.connect(
                    settings.database_url.replace("postgresql+psycopg://", "postgresql://"),
                    autocommit=True,
                    prepare_threshold=0,
                    options="-csearch_path=agent_checkpoints",
                )
                saver = PostgresSaver(connection)
                if settings.schema_bootstrap:
                    saver.setup()
            else:
                saver = checkpointer
            active_planner = planner or (
                CodexPlanner(settings) if settings.model_provider == "codex" else BaselinePlanner()
            )
            active_source = source or HttpSource(settings)
            agent = ShoppingAgent(service, active_planner, saver, engine)
            agent.protocol_gateway = protocol_gateway
            worker = Worker(factory, settings, active_source, agent, kinds={"EXECUTION"})
            agent_worker = Worker(factory, settings, active_source, agent, kinds={"AGENT"})
            app.state.worker, app.state.agent, app.state.agent_worker = worker, agent, agent_worker
            family_planner = (
                FamilyCodex(settings) if settings.model_provider == "codex" else FamilyBaseline()
            )
            family_worker = PharmacyWorker(
                pharmacy, FamilyWorkflow(pharmacy, family_planner, saver), active_source
            )
            app.state.pharmacy_worker = family_worker
            if settings.worker_enabled:
                worker.start()
                if settings.product_mode == "retail":
                    agent_worker.start()
                else:
                    family_worker.start()
            async with mcp_server.session_manager.run():
                yield
        finally:
            if hasattr(app.state, "speaker"):
                app.state.speaker.close()
            if hasattr(app.state, "pharmacy_worker"):
                app.state.pharmacy_worker.stop()
            if hasattr(app.state, "worker"):
                app.state.worker.stop()
                if hasattr(app.state, "agent_worker"):
                    app.state.agent_worker.stop()
                if hasattr(app.state.worker.source, "close"):
                    app.state.worker.source.close()
            if connection:
                connection.close()
            identity_service.close()
            engine.dispose()

    app = FastAPI(
        title="Agentic Commerce",
        version="0.1.0",
        lifespan=lifespan,
        description="Local synthetic commerce. Approval and business state are authoritative; model output is not.",
    )
    app.state.service, app.state.factory, app.state.settings = service, factory, settings
    app.state.pharmacy = pharmacy
    app.state.identity = identity_service
    app.state.protocol_gateway = protocol_gateway
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "Idempotency-Key",
            "Authorization",
            "Mcp-Protocol-Version",
            "Mcp-Session-Id",
            "Mcp-Method",
            "Mcp-Name",
        ],
        expose_headers=["Mcp-Session-Id", "WWW-Authenticate"],
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )

    app.add_middleware(Boundary, settings=settings, requests=REQUESTS, latency=LATENCY)

    def actor(request: Request):
        if settings.product_mode == "pharmacy" and request.url.path.startswith(
            (
                "/api/v1/catalog",
                "/api/v1/sessions",
                "/api/v1/quotes",
                "/api/v1/executions",
                "/api/v1/grants",
                "/api/v1/operator",
            )
        ):
            raise HTTPException(404, "This product uses the pharmacy workflow.")
        return identity_service.authenticate(request)

    def operator(identity: Actor = Depends(actor)):
        if identity.role != "operator":
            raise DomainError("OPERATOR_REQUIRED", "Operator access required.", 403)
        return identity

    def request_key(idempotency_key: str = Header(alias="Idempotency-Key")):
        if not 8 <= len(idempotency_key) <= 100:
            raise DomainError(
                "INVALID_REQUEST_KEY", "Use an idempotency key of 8–100 characters.", 422
            )
        return idempotency_key

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        identity = getattr(request.state, "actor", None)
        if identity:
            service.audit_denial(identity, "request", error.code)
        return JSONResponse(
            {
                "error": {"code": error.code, "message": error.message},
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=error.status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic errors include rejected input by default; omit it from responses.
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request does not match the API contract.",
                    "fields": [".".join(map(str, e["loc"])) for e in error.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_execution_request":
            return JSONResponse(
                {
                    "error": {
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "This execution key belongs to another checkout.",
                    }
                },
                status_code=409,
            )
        log.error("database_constraint_rejected category=%s", constraint or "unknown")
        return JSONResponse(
            {
                "error": {
                    "code": "STATE_CONFLICT",
                    "message": "The requested state change could not be accepted.",
                }
            },
            status_code=409,
        )

    @app.get("/api/v1/product")
    def product():
        return {
            "mode": settings.product_mode,
            "name": "Asterfield Pharmacy"
            if settings.product_mode == "pharmacy"
            else "Agentic Commerce",
            "synthetic": True,
        }

    register_pharmacy(app, pharmacy, actor, request_key)

    @app.get("/health/live")
    def live():
        return {"status": "ok", "version": "0.1.0", "mode": "local-synthetic"}

    @app.get("/health/ready")
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                {"status": "not_ready", "dependency": "commerce_database"}, status_code=503
            )
        return {
            "status": "ready",
            "model_provider": settings.model_provider,
            "product_mode": settings.product_mode,
            "worker": bool(
                getattr(app.state, "worker", None)
                and app.state.worker.thread
                and app.state.worker.thread.is_alive()
            ),
        }

    @app.get("/metrics", dependencies=[Depends(operator)])
    def metrics():
        refresh_workflow_metrics(factory)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/internal/metrics")
    def scrape_metrics(authorization: str = Header(default="")):
        configured = settings.metrics_token.get_secret_value()
        if len(configured) < 32 or not hmac.compare_digest(authorization, "Bearer " + configured):
            raise HTTPException(401, "Metrics credential required")
        refresh_workflow_metrics(factory)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    def session_cookie(response, token):
        response.set_cookie(
            "commerce_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            max_age=settings.session_ttl_seconds,
        )

    @app.get("/api/v1/auth/config")
    def auth_config():
        return {
            "mode": settings.auth_mode,
            "login_url": "/api/v1/auth/login" if settings.auth_mode == "oidc" else None,
        }

    @app.post("/api/v1/auth/demo")
    def login(body: LoginRequest, response: Response):
        if settings.auth_mode != "demo":
            raise HTTPException(404, "Demonstration login is disabled")
        identity = Actor(
            user_id=body.persona,
            role="operator" if body.persona == "operator" else "shopper",
            display_name=body.persona.title(),
        )
        token, csrf = identity_service.issue_session(identity)
        session_cookie(response, token)
        return {"actor": identity.model_dump(), "csrf_token": csrf, "local_demo": True}

    @app.get("/api/v1/auth/login")
    def oidc_login():
        if settings.auth_mode != "oidc":
            raise HTTPException(404, "OIDC login is disabled")
        url, binding = identity_service.start_login()
        response = RedirectResponse(url, status_code=302)
        response.set_cookie(
            "commerce_login",
            binding,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=300,
            path="/api/v1/auth/callback",
        )
        return response

    @app.get("/api/v1/auth/callback")
    def oidc_callback(request: Request, state: str = "", code: str = ""):
        if settings.auth_mode != "oidc":
            raise HTTPException(404, "OIDC login is disabled")
        token, _, _ = identity_service.finish_login(
            state, code, request.cookies.get("commerce_login", "")
        )
        response = RedirectResponse("/", status_code=302)
        session_cookie(response, token)
        response.delete_cookie("commerce_login", path="/api/v1/auth/callback")
        return response

    @app.get("/api/v1/auth/me")
    def me(request: Request, identity: Actor = Depends(actor)):
        return {
            "actor": identity.model_dump(),
            "csrf_token": request.state.principal.csrf,
            "local_demo": settings.auth_mode == "demo",
        }

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response, identity: Actor = Depends(actor)):
        identity_service.revoke(request.state.principal)
        response.delete_cookie("commerce_session")
        return {"signed_out": True}

    @app.get("/api/v1/catalog")
    def catalog(kiosk_id: str = "kiosk-a", identity: Actor = Depends(actor)):
        return {"products": service.catalog(identity, kiosk_id)}

    @app.post("/api/v1/sessions", status_code=202)
    def create_session(
        body: SessionRequest, identity: Actor = Depends(actor), key: str = Depends(request_key)
    ):
        identifier = service.create_session(identity, body.request, key, body.grant_id)
        return {"session_id": identifier, "status_url": f"/api/v1/sessions/{identifier}"}

    @app.get("/api/v1/sessions")
    def sessions(identity: Actor = Depends(actor)):
        with factory() as db:
            rows = db.scalars(
                select(PurchaseSession)
                .where(
                    PurchaseSession.tenant_id == identity.tenant_id,
                    PurchaseSession.user_id == identity.user_id,
                )
                .order_by(PurchaseSession.created_at.desc())
                .limit(40)
            ).all()
            return {
                "sessions": [
                    {
                        "id": row.id,
                        "request": row.original_request,
                        "state": db.get(Execution, row.execution_id).state
                        if row.execution_id
                        else row.state,
                        "created_at": row.created_at,
                    }
                    for row in rows
                ]
            }

    @app.get("/api/v1/sessions/{session_id}")
    def session_detail(session_id: str, identity: Actor = Depends(actor)):
        return service.session_detail(identity, session_id)

    @app.post("/api/v1/sessions/{session_id}/retry", status_code=202)
    def retry_session(session_id: str, identity: Actor = Depends(actor)):
        with factory.begin() as db:
            own(db.get(PurchaseSession, session_id), identity)
            enqueue(db, "AGENT", session_id, revive=True)
        return {"session_id": session_id, "state": "QUEUED"}

    @app.post("/api/v1/quotes/{quote_id}/approval")
    def approve(quote_id: str, body: ApprovalRequest, identity: Actor = Depends(actor)):
        envelope = protocol_gateway.authorize(identity, quote_id, quote_digest=body.quote_digest)
        with factory() as db:
            approval = db.scalar(select(Approval).where(Approval.quote_id == quote_id))
            return {"id": approval.id, "state": approval.state, "quote_id": quote_id, **envelope}

    @app.post("/api/v1/executions", status_code=202)
    def execute(
        body: ExecutionRequest, identity: Actor = Depends(actor), key: str = Depends(request_key)
    ):
        with factory() as db:
            envelope = db.scalar(
                select(ProtocolEnvelope).where(
                    ProtocolEnvelope.quote_id == body.quote_id,
                    ProtocolEnvelope.tenant_id == identity.tenant_id,
                    ProtocolEnvelope.user_id == identity.user_id,
                )
            )
        if envelope:
            if {k: v for k, v in envelope.authority.items() if k != "fault_profile"} != {
                k: v for k, v in body.model_dump().items() if k != "fault_profile"
            }:
                raise DomainError(
                    "AUTHORITY_CONFLICT", "Checkout authority differs from its signed mandate.", 403
                )
            identifier = protocol_gateway.execute(
                identity, envelope.id, key, fault_profile=body.fault_profile
            )
        else:
            identifier = service.accept(identity, body, key)
        with factory.begin() as db:
            row = db.get(Execution, identifier)
            session_id = db.scalar(
                select(PurchaseSession.id).where(PurchaseSession.execution_id == identifier)
            )
            if session_id:
                enqueue(db, "AGENT", session_id, revive=True)
            return service.execution_dict(row)

    @app.get("/api/v1/protocols")
    def protocols(identity: Actor = Depends(actor)):
        return {
            "ap2": "local-ap2-v0.2-es256",
            "mcp": "SDK 2.3.0 Streamable HTTP read-only",
            "recognition": "local RFC9421 profile; not Visa-enrolled",
        }

    @app.get("/api/v1/protocols/ap2/envelopes/{envelope_id}")
    def mandate_bundle(envelope_id: str, identity: Actor = Depends(actor)):
        return protocol_gateway.bundle(identity, envelope_id)

    @app.get("/api/v1/protocols/ap2/envelopes/{envelope_id}/receipts")
    def mandate_receipts(envelope_id: str, identity: Actor = Depends(actor)):
        return protocol_gateway.receipts(identity, envelope_id)

    @app.get("/api/v1/executions/{execution_id}")
    def execution_detail(execution_id: str, identity: Actor = Depends(actor)):
        with factory() as db:
            return service.execution_dict(own(db.get(Execution, execution_id), identity))

    @app.get("/api/v1/grants")
    def grants(identity: Actor = Depends(actor)):
        with factory() as db:
            return {
                "grants": [
                    service.grant_dict(g)
                    for g in db.scalars(
                        select(Grant)
                        .where(
                            Grant.tenant_id == identity.tenant_id, Grant.user_id == identity.user_id
                        )
                        .order_by(Grant.created_at.desc())
                    ).all()
                ]
            }

    @app.post("/api/v1/grants", status_code=201)
    def create_grant(body: GrantRequest, identity: Actor = Depends(actor)):
        return service.create_grant(identity, body)

    @app.post("/api/v1/grants/{grant_id}/revoke")
    def revoke(grant_id: str, identity: Actor = Depends(actor)):
        return service.revoke_grant(identity, grant_id)

    @app.post("/api/v1/operator/products/{product_id}/price")
    def update_price(product_id: str, body: PriceUpdate, identity: Actor = Depends(operator)):
        with factory.begin() as db:
            row = db.scalar(
                select(Product)
                .where(Product.id == product_id, Product.tenant_id == identity.tenant_id)
                .with_for_update()
            )
            if row is None:
                raise DomainError("NOT_FOUND", "Product not found.", 404)
            row.price_minor, row.version = body.price_minor, row.version + 1
            record(db, identity, row.id, "catalog.price_changed", version=row.version)
            return {"id": row.id, "price_minor": row.price_minor, "version": row.version}

    @app.get("/api/v1/operator/overview")
    def overview(identity: Actor = Depends(operator)):
        with factory() as db:
            executions = db.scalars(
                select(Execution)
                .where(Execution.tenant_id == identity.tenant_id)
                .order_by(Execution.created_at.desc())
                .limit(50)
            ).all()
            jobs = db.scalars(
                select(Job).where(Job.state.in_(["READY", "RUNNING", "NEEDS_REVIEW"])).limit(100)
            ).all()
            events = db.scalars(
                select(AuditEvent)
                .where(AuditEvent.tenant_id == identity.tenant_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(100)
            ).all()
            return {
                "executions": [service.execution_dict(e) for e in executions],
                "jobs": [
                    {
                        "id": j.id,
                        "kind": j.kind,
                        "state": j.state,
                        "attempts": j.attempts,
                        "resource_id": j.resource_id,
                        "last_error": j.last_error,
                    }
                    for j in jobs
                ],
                "events": [
                    {
                        "id": e.id,
                        "type": e.event_type,
                        "resource_id": e.resource_id,
                        "actor": e.actor_id,
                        "data": e.data,
                        "created_at": e.created_at,
                    }
                    for e in events
                ],
            }

    @app.post("/api/v1/operator/executions/{execution_id}/retry", status_code=202)
    def retry_execution(execution_id: str, identity: Actor = Depends(operator)):
        with factory.begin() as db:
            row = db.scalar(
                select(Execution)
                .where(Execution.id == execution_id, Execution.tenant_id == identity.tenant_id)
                .with_for_update()
            )
            if row is None:
                raise DomainError("NOT_FOUND", "Execution not found.", 404)
            if row.fault_profile != "source_unavailable" or row.state not in {
                "EXECUTING",
                "RECOVERY_REQUIRED",
            }:
                raise DomainError(
                    "MANUAL_REVIEW_REQUIRED",
                    "Only a resolved synthetic source outage can be retried here.",
                )
            row.fault_profile, row.state, row.failure_code = "none", "EXECUTING", None
            enqueue(db, "EXECUTION", row.id, revive=True)
            record(db, identity, row.id, "operator.recovery_requested", stage=row.stage)
            return {"execution_id": row.id, "state": row.state}

    # MCP is an authenticated bounded tool transport, not an approval channel.
    from commerce.mcp import register_mcp

    mcp_server = register_mcp(app, service, identity_service, pharmacy)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready,metrics")
    built = Path(__file__).resolve().parents[2] / "web" / "dist"
    if built.is_dir():
        app.mount("/", StaticFiles(directory=built, html=True), name="web")
    return app
