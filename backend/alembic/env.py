import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import settings
from app.core.db import connect_args
from app.models import Base

config = context.config

# Migrations run on the DIRECT (session) connection: DDL and long transactions cannot survive
# transaction pooling. ALEMBIC_DATABASE_URL overrides it so the test suite can migrate its own
# throwaway database. The URL goes straight to create_engine rather than through alembic.ini,
# whose configparser reads `%` as interpolation and rejects an encoded password (`%40`).
url = os.environ.get("ALEMBIC_DATABASE_URL") or settings.migration_url

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args(url))
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
