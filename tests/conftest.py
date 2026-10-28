from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from helper_bot.config import Settings


@pytest.fixture
def database():
    engine = create_engine(Settings().database_url, connect_args={"connect_timeout": 5})
    schema = "test_" + uuid4().hex
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, "head")
            connection.commit()
            yield connection, config
        finally:
            connection.rollback()
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.commit()
    engine.dispose()
