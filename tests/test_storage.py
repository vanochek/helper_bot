from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from helper_bot.config import Settings
from helper_bot.storage import EntryRepository, NewEntry, create_session, resolve_session


def test_persistence_isolation_and_rollback(database):
    connection, config = database
    with Session(connection) as db, db.begin():
        owner, token = create_session(db, "Europe/Moscow")
        other, _ = create_session(db, "UTC")
        owner_id, other_id = owner.id, other.id
        entry = EntryRepository(db, owner_id).create(NewEntry(kind="task", title="  Отчёт  "))
        entry_id = entry.id
        assert owner.token_hash != token
        assert entry.status == "open"
    command.upgrade(config, "head")
    connection.commit()
    with Session(connection) as db:
        restored = resolve_session(db, token)
        assert restored.id == owner_id
        assert resolve_session(db, "неверный токен") is None
        entry = EntryRepository(db, owner_id).get(entry_id)
        assert entry.title == "Отчёт"
        assert entry.created_at.tzinfo is not None
        assert EntryRepository(db, other_id).get(entry_id) is None
        assert EntryRepository(db, other_id).list_recent() == []
        EntryRepository(db, owner_id).create(NewEntry(kind="task", title="Откат"))
        db.rollback()
    with Session(connection) as db:
        assert len(EntryRepository(db, owner_id).list_recent()) == 1
    schema = connection.scalar(text("SELECT current_schema()"))
    fresh_engine = create_engine(
        Settings().database_url,
        connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"},
    )
    try:
        with Session(fresh_engine) as db:
            assert EntryRepository(db, owner_id).get(entry_id).title == "Отчёт"
    finally:
        fresh_engine.dispose()
    command.check(config)
    connection.commit()
    command.downgrade(config, "base")
    connection.commit()
    command.upgrade(config, "head")
    connection.commit()


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "meeting", "title": "Встреча"},
        {"kind": "task", "title": "   "},
        {"kind": "unknown", "title": "Тема"},
        {"kind": "task", "title": "Тема", "scheduled_at": datetime(2026, 1, 1)},
        {"kind": "task", "title": "Тема", "session_id": str(uuid4())},
        {
            "kind": "task",
            "title": "Тема",
            "scheduled_at": datetime.now(UTC),
            "scheduled_on": date(2026, 1, 1),
        },
    ],
)
def test_invalid_input(fields):
    with pytest.raises(ValidationError):
        NewEntry(**fields)


def test_time_and_database_constraints(database):
    connection, _ = database
    moment = datetime.now(UTC)
    with Session(connection) as db, db.begin():
        owner, _ = create_session(db, "UTC")
        owner_id = owner.id
        repo = EntryRepository(db, owner_id)
        entry = repo.create(
            NewEntry(
                kind="meeting",
                title="Обсуждение",
                scheduled_at=moment,
                ends_at=moment + timedelta(hours=1),
            )
        )
        entry_id = entry.id
        repo.create(NewEntry(kind="task", title="Дата", scheduled_on=date(2026, 10, 30)))
        repo.create(NewEntry(kind="reminder", title="Звонок", scheduled_at=moment))
    with Session(connection) as db:
        assert EntryRepository(db, owner_id).get(entry_id).scheduled_at == moment
    for values in [
        "'meeting', 'Тема', NULL, NULL, NULL",
        "'task', ' ', NULL, NULL, NULL",
        "'wrong', 'Тема', NULL, NULL, NULL",
        "'task', 'Тема', now(), current_date, NULL",
        "'task', 'Тема', now(), NULL, now()",
        "'meeting', 'Тема', now(), NULL, now() - interval '1 hour'",
    ]:
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO entries(id, session_id, kind, title, "
                    "scheduled_at, scheduled_on, ends_at) "
                    f"VALUES (:id, :owner, {values})"
                ),
                {"id": uuid4(), "owner": owner_id},
            )
