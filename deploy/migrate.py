"""Миграции от владельца схемы, приложению выдаются только необходимые права."""

import os

from alembic import command
from alembic.config import Config
from psycopg import connect, sql
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
with connect(
    host=url.host, port=url.port, user=url.username, password=url.password, dbname=url.database
) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'helper_app'")
        if cursor.fetchone() is None:
            cursor.execute("CREATE ROLE helper_app LOGIN")
        cursor.execute(
            sql.SQL("ALTER ROLE helper_app PASSWORD {}").format(
                sql.Literal(os.environ["DB_APP_PASSWORD"])
            )
        )
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
command.upgrade(Config("alembic.ini"), "head")
with connect(
    host=url.host, port=url.port, user=url.username, password=url.password, dbname=url.database
) as connection:
    with connection.cursor() as cursor:
        cursor.execute("GRANT CONNECT ON DATABASE helper TO helper_app")
        cursor.execute("GRANT USAGE ON SCHEMA public TO helper_app")
        cursor.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON "
            "browser_sessions, entries, chat_messages TO helper_app"
        )
