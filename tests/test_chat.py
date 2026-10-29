from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from helper_bot.ai import AIUnavailable, Intent
from helper_bot.api import database as database_dependency
from helper_bot.chat_api import interpreter
from helper_bot.main import app
from helper_bot.temporal import TemporalCandidate


class FakeInterpreter:
    def __init__(self):
        self.results = []
        self.calls = []

    def interpret(self, messages, now, timezone):
        self.calls.append((messages, now, timezone))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def intent(action="create", **fields):
    return Intent(
        action=action,
        **{
            "kind": "task",
            "title": "Презентация",
            "query": None,
            "temporal": None,
            "question": None,
            **fields,
        },
    )


@pytest.fixture
def chat(database, monkeypatch):
    connection, _ = database
    fake = FakeInterpreter()

    def session():
        with Session(connection, expire_on_commit=False) as db:
            yield db

    monkeypatch.setattr(
        "helper_bot.chat_api.current_time", lambda: datetime(2026, 10, 28, 12, tzinfo=UTC)
    )
    app.dependency_overrides[database_dependency] = session
    app.dependency_overrides[interpreter] = lambda: fake
    try:
        with TestClient(app) as client:
            client.headers["Origin"] = "http://127.0.0.1:8000"
            assert (
                client.post("/api/v1/session", json={"timezone": "Europe/Moscow"}).status_code
                == 200
            )
            yield client, fake
    finally:
        app.dependency_overrides.clear()


def send(client, text, request_id=None):
    return client.post(
        "/api/v1/chat/messages", json={"request_id": str(request_id or uuid4()), "text": text}
    )


def test_create_retry_conflict_and_history(chat):
    client, fake = chat
    fake.results.append(intent())
    key = uuid4()
    first = send(client, "Подготовить презентацию", key)
    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert send(client, "Подготовить презентацию", key).json() == first.json()
    assert send(client, "Другая задача", key).status_code == 409
    assert len(fake.calls) == 1
    assert len(client.get("/api/v1/entries").json()) == 1
    assert len(client.get("/api/v1/chat/messages").json()) == 1
    client.cookies.clear()
    assert client.get("/api/v1/chat/messages").status_code == 401
    client.post("/api/v1/session", json={"timezone": "UTC"})
    assert client.get("/api/v1/chat/messages").json() == []


def test_clarification_preserves_context_and_cancel(chat):
    client, fake = chat
    fake.results.extend(
        [
            intent(kind="meeting", temporal=TemporalCandidate(relation="tomorrow")),
            intent(
                kind="meeting", temporal=TemporalCandidate(relation="tomorrow", local_time="15:00")
            ),
            intent(kind="reminder"),
        ]
    )
    assert send(client, "Встреча завтра").json()["status"] == "needs_clarification"
    assert client.get("/api/v1/entries").json() == []
    response = send(client, "В 15 часов").json()
    assert response["entries"][0]["scheduled_at"] == "2026-10-29T12:00:00Z"
    assert fake.calls[1][0] == ["Встреча завтра", "В 15 часов"]
    assert fake.calls[0][1] == fake.calls[1][1]
    send(client, "Напомни позвонить")
    assert send(client, "Отмена").json()["status"] == "cancelled"
    assert len(fake.calls) == 3


def test_search_list_and_isolation(chat):
    client, fake = chat
    fake.results.extend(
        [
            intent(),
            intent(
                kind="meeting", temporal=TemporalCandidate(relation="tomorrow", local_time="15:00")
            ),
            intent("search", kind=None, query="презентация"),
            intent("list", kind="meeting", temporal=TemporalCandidate(relation="tomorrow")),
        ]
    )
    send(client, "Задача презентация")
    send(client, "Встреча презентация завтра в 15")
    assert len(send(client, "Найди презентации").json()["entries"]) == 2
    assert len(send(client, "Встречи завтра").json()["entries"]) == 1


def test_failure_retry_and_past_confirmation(chat):
    client, fake = chat
    fake.results.extend(
        [
            AIUnavailable("Временно недоступен"),
            intent(temporal=TemporalCandidate(relation="today", local_time="09:00")),
        ]
    )
    key = uuid4()
    assert send(client, "Сегодня в девять", key).status_code == 503
    assert client.get("/api/v1/chat/messages").json() == []
    assert send(client, "Сегодня в девять", key).json()["status"] == "needs_clarification"
    assert client.get("/api/v1/entries").json() == []
    assert send(client, "да").json()["status"] == "completed"
    assert len(fake.calls) == 2


def test_chat_commit_failure_is_atomic(chat, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    client, fake = chat
    fake.results.extend([intent(), intent()])
    key = uuid4()

    def fail(self):
        raise SQLAlchemyError("Ошибка commit")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        assert send(client, "Создай задачу", key).status_code == 503
    assert client.get("/api/v1/entries").json() == []
    assert client.get("/api/v1/chat/messages").json() == []
    assert send(client, "Создай задачу", key).status_code == 200


def test_origin_limits_and_ui(chat):
    client, _ = chat
    assert (
        client.post(
            "/api/v1/chat/messages",
            headers={"Origin": "https://evil.example"},
            json={"request_id": str(uuid4()), "text": "Привет"},
        ).status_code
        == 403
    )
    assert send(client, "x" * 2001).status_code == 422
    assert send(client, "   ").status_code == 422
    assert "textarea" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_real_adapter_payload_without_network(monkeypatch):
    from types import SimpleNamespace

    from helper_bot.ai import OpenAIInterpreter

    captured = {}

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_parsed=intent(), status="completed")

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    monkeypatch.setattr("helper_bot.ai.OpenAI", Client)
    result = OpenAIInterpreter().interpret(["Задача"], datetime.now(UTC), "UTC")
    assert result.action == "create"
    assert captured["store"] is False
    assert captured["text_format"] is Intent
    assert captured["model"] == "configured-model"


def test_concurrent_duplicate_requests(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import create_engine, text

    from helper_bot.chat import MessageInput, handle_message
    from helper_bot.config import Settings
    from helper_bot.storage import create_session

    connection, _ = database
    with Session(connection) as db:
        owner, _ = create_session(db, "UTC")
        owner_id = owner.id
        db.commit()
    schema = connection.scalar(text("SELECT current_schema()"))
    connection.commit()
    engine = create_engine(
        Settings().database_url,
        connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 5},
    )
    fake = FakeInterpreter()
    fake.results.append(intent())
    message = MessageInput(request_id=uuid4(), text="Создай задачу")
    barrier = Barrier(2)

    def worker():
        with Session(engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            return handle_message(db, owner_id, message, fake, datetime.now(UTC)).model_dump()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            replies = [future.result(timeout=20) for future in futures]
        assert replies[0] == replies[1]
        assert len(fake.calls) == 1
    finally:
        engine.dispose()


def test_missing_key_is_explicit(monkeypatch):
    from helper_bot.ai import OpenAIInterpreter

    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    with pytest.raises(AIUnavailable, match="AI не настроен"):
        OpenAIInterpreter().interpret(["Привет"], datetime.now(UTC), "UTC")


def test_same_text_new_request_failure_and_recovery(chat):
    client, fake = chat
    text = "Создай задачу купить молоко завтра"
    fake.results.extend([intent(), AIUnavailable("Нет соединения с Groq"), intent()])
    first = send(client, text)
    assert first.status_code == 200
    key = uuid4()
    failed = send(client, text, key)
    assert failed.status_code == 503
    assert failed.headers["X-Request-Outcome"] == "not-applied"
    assert len(client.get("/api/v1/entries").json()) == 1
    assert len(client.get("/api/v1/chat/messages").json()) == 1
    recovered = send(client, text, key)
    assert recovered.status_code == 200
    assert send(client, text, key).json() == recovered.json()
    assert len(fake.calls) == 3
    assert len(client.get("/api/v1/entries").json()) == 2
