import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from langgraph.checkpoint.postgres import PostgresSaver
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commerce.agent import ShoppingAgent
from commerce.config import Settings, get_settings
from commerce.db import make_engine, make_sessions
from commerce.domain import DomainError
from commerce.models import AuditEvent, Execution, Grant, Job, Product, PurchaseSession
from commerce.observability import configure_tracing
from commerce.payments import HttpSource
from commerce.planner import BaselinePlanner, CodexPlanner
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
    signer = URLSafeTimedSerializer(
        settings.signing_key.get_secret_value(), salt="commerce-session-v1"
    )

    @asynccontextmanager
    async def lifespan(app):
        configure_tracing(settings.trace_enabled)
        seed(factory)
        connection = None
        try:
            if checkpointer is None:
                # Checkpoint tables have a distinct namespace and no business authority.
                with engine.begin() as db:
                    db.execute(text("CREATE SCHEMA IF NOT EXISTS agent_checkpoints"))
                connection = psycopg.connect(
                    settings.database_url.replace("postgresql+psycopg://", "postgresql://"),
                    autocommit=True,
                    prepare_threshold=0,
                    options="-csearch_path=agent_checkpoints",
                )
                saver = PostgresSaver(connection)
                saver.setup()
            else:
                saver = checkpointer
            active_planner = planner or (
                CodexPlanner(settings) if settings.model_provider == "codex" else BaselinePlanner()
            )
            active_source = source or HttpSource(settings)
            agent = ShoppingAgent(service, active_planner, saver, engine)
            worker = Worker(factory, settings, active_source, agent, kinds={"EXECUTION"})
            agent_worker = Worker(factory, settings, active_source, agent, kinds={"AGENT"})
            app.state.worker, app.state.agent, app.state.agent_worker = worker, agent, agent_worker
            if settings.worker_enabled:
                worker.start()
                agent_worker.start()
            yield
        finally:
            if hasattr(app.state, "worker"):
                app.state.worker.stop()
                if hasattr(app.state, "agent_worker"):
                    app.state.agent_worker.stop()
                if hasattr(app.state.worker.source, "close"):
                    app.state.worker.source.close()
            if connection:
                connection.close()
            engine.dispose()

    app = FastAPI(
        title="Agentic Commerce",
        version="0.1.0",
        lifespan=lifespan,
        description="Local synthetic commerce. Approval and business state are authoritative; model output is not.",
    )
    app.state.service, app.state.factory, app.state.settings = service, factory, settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "Authorization"],
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        identifier, started = str(uuid4()), time.monotonic()
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse(
                {
                    "error": {
                        "code": "LOCAL_ONLY",
                        "message": "This release accepts loopback clients only.",
                    }
                },
                status_code=403,
            )
        if request.method in {"POST", "PUT", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and origin not in settings.allowed_origins:
                return JSONResponse(
                    {"error": {"code": "ORIGIN_DENIED", "message": "Origin not allowed."}},
                    status_code=403,
                )
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse(
                        {
                            "error": {
                                "code": "REQUEST_TOO_LARGE",
                                "message": "Request exceeds 64 KiB.",
                            }
                        },
                        status_code=413,
                    )
            request._body = bytes(body)
        request.state.request_id = identifier
        response = await call_next(request)
        route = request.scope.get("route")
        route_name = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, route_name, str(response.status_code)).inc()
        LATENCY.labels(route_name).observe(time.monotonic() - started)
        response.headers.update(
            {
                "X-Request-ID": identifier,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
            }
        )
        return response

    def actor(request: Request):
        bearer = request.headers.get("authorization", "")
        token = (
            bearer[7:]
            if bearer.startswith("Bearer ")
            else request.cookies.get("commerce_session", "")
        )
        try:
            value = signer.loads(token, max_age=8 * 3600)
            identity = Actor.model_validate(value["actor"])
        except (BadSignature, SignatureExpired, ValueError, KeyError):
            raise HTTPException(401, "Sign in to the local demonstration") from None
        if not bearer and request.method != "GET":
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), value["csrf"]):
                raise HTTPException(403, "CSRF token required")
        request.state.actor = identity
        return identity

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
            "worker": bool(
                getattr(app.state, "worker", None)
                and app.state.worker.thread
                and app.state.worker.thread.is_alive()
            ),
        }

    @app.get("/metrics", dependencies=[Depends(operator)])
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/api/v1/auth/demo")
    def login(body: LoginRequest, response: Response):
        # No fake production authentication: this route is deliberately local/demo-only.
        identity = Actor(
            user_id=body.persona, role="operator" if body.persona == "operator" else "shopper"
        )
        csrf = secrets.token_urlsafe(24)
        token = signer.dumps({"actor": identity.model_dump(), "csrf": csrf})
        response.set_cookie(
            "commerce_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            max_age=8 * 3600,
        )
        return {"actor": identity.model_dump(), "csrf_token": csrf, "local_demo": True}

    @app.get("/api/v1/auth/me")
    def me(request: Request, identity: Actor = Depends(actor)):
        bearer = request.headers.get("authorization", "")
        token = (
            bearer[7:]
            if bearer.startswith("Bearer ")
            else request.cookies.get("commerce_session", "")
        )
        value = signer.loads(token, max_age=8 * 3600)
        return {"actor": identity.model_dump(), "csrf_token": value["csrf"], "local_demo": True}

    @app.post("/api/v1/auth/logout")
    def logout(response: Response, identity: Actor = Depends(actor)):
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
        return service.approve(identity, quote_id, body.quote_digest)

    @app.post("/api/v1/executions", status_code=202)
    def execute(
        body: ExecutionRequest, identity: Actor = Depends(actor), key: str = Depends(request_key)
    ):
        identifier = service.accept(identity, body, key)
        with factory.begin() as db:
            row = db.get(Execution, identifier)
            session_id = db.scalar(
                select(PurchaseSession.id).where(PurchaseSession.execution_id == identifier)
            )
            if session_id:
                enqueue(db, "AGENT", session_id, revive=True)
            return service.execution_dict(row)

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

    register_mcp(app, service, actor)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready,metrics")
    built = Path(__file__).resolve().parents[2] / "web" / "dist"
    if built.is_dir():
        app.mount("/", StaticFiles(directory=built, html=True), name="web")
    return app
