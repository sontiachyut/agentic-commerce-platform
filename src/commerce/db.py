from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    return create_engine(
        url, pool_pre_ping=True, pool_size=8, max_overflow=4, connect_args={"connect_timeout": 5}
    )


def make_sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)


def transaction(factory) -> Iterator[Session]:
    with factory.begin() as session:
        yield session
