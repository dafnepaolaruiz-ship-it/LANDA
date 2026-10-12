from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

import models  # noqa: F401  (registra las tablas)
from config import get_settings
from database import Base, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata
URL = get_settings().database_url


def run_migrations_offline() -> None:
    from database import normalize_url

    context.configure(url=normalize_url(URL), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(URL)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
