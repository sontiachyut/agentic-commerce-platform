import os
from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from sqlalchemy.engine import make_url

from commerce.config import Settings
from commerce.db import Base, make_engine, make_sessions
from commerce.payments import SourceConflict, SourceUnavailable
from commerce.schemas import Actor, Intent
from commerce.service import CommerceService, seed
from commerce.simulator import SourceBase, StatefulSource
from commerce.worker import Worker


class LocalSource:
    def __init__(self, source):
        self.source = source

    def observe_or_send(self, request):
        result = self.source.inquire(request.execution_id, request.action)
        if result:
            return result
        try:
            return self.source.command(request)
        except HTTPException as exc:
            if exc.status_code == 409:
                raise SourceConflict() from exc
            raise SourceUnavailable() from exc


@dataclass
class System:
    settings: Settings
    engine: object
    factory: object
    service: CommerceService
    source: StatefulSource
    source_factory: object
    worker: Worker
    actor: Actor


@pytest.fixture
def system():
    url = os.environ.get(
        "COMMERCE_TEST_DATABASE_URL",
        "postgresql+psycopg://commerce:local-demo-only@127.0.0.1:55439/commerce_test",
    )
    source_url = os.environ.get(
        "COMMERCE_TEST_SOURCE_DATABASE_URL",
        "postgresql+psycopg://commerce:local-demo-only@127.0.0.1:55439/commerce_sources_test",
    )
    # Refuse destructive fixture setup anywhere except dedicated test databases.
    if (
        make_url(url).database != "commerce_test"
        or make_url(source_url).database != "commerce_sources_test"
    ):
        pytest.fail("Tests require isolated commerce_test and commerce_sources_test databases")
    settings = Settings(
        _env_file=None,
        database_url=url,
        simulator_database_url=source_url,
        signing_key="synthetic-test-signing-key-" * 3,
        source_token="synthetic-test-source-token-" * 3,
        worker_enabled=False,
        trace_enabled=False,
    )
    engine, source_engine = make_engine(url), make_engine(source_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    SourceBase.metadata.drop_all(source_engine)
    SourceBase.metadata.create_all(source_engine)
    factory, source_factory = make_sessions(engine), make_sessions(source_engine)
    seed(factory)
    service, source = CommerceService(factory, settings), StatefulSource(source_factory)
    worker = Worker(factory, settings, LocalSource(source))
    yield System(
        settings, engine, factory, service, source, source_factory, worker, Actor(user_id="alex")
    )
    engine.dispose()
    source_engine.dispose()


@pytest.fixture
def prepared(system):
    from commerce.models import PurchaseSession, new_id

    def prepare(product="bar-cocoa", actor=None):
        actor = actor or system.actor
        identifier = system.service.create_session(actor, "Buy a protein bar under $5", new_id())
        with system.factory.begin() as db:
            db.get(PurchaseSession, identifier).intent = Intent(
                category="protein-bar", max_amount_minor=500
            ).model_dump()
        quote = system.service.quote(actor, identifier, product)
        approval = system.service.approve(actor, quote["id"], quote["digest"])
        return identifier, quote, approval

    return prepare
