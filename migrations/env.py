from alembic import context
from sqlalchemy import create_engine, pool

from commerce import models  # noqa: F401
from commerce.config import get_settings
from commerce.db import Base
from commerce.pharmacy import models as pharmacy_models  # noqa: F401

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
