from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from helper_bot.api import database as database_dependency
from helper_bot.chat_api import interpreter
from helper_bot.demo import DemoInterpreter
from helper_bot.main import app
from helper_bot.speech_api import transcriber


def test_switching(monkeypatch):
    monkeypatch.setenv("AI_MODE", "demo")
    assert type(interpreter()).__name__ == "DemoInterpreter"
    assert type(transcriber()).__name__ == "DemoTranscriber"
    monkeypatch.setenv("AI_MODE", "openai")
    assert type(interpreter()).__name__ == "OpenAIInterpreter"
    assert type(transcriber()).__name__ == "OpenAITranscriber"


@pytest.mark.parametrize(
    "text",
    [
        "Привет",
        "Напомни завтра в 25:00 позвонить",
        "Создай задачу завтра сегодня купить хлеб",
        "Напомни через час позвонить",
    ],
)
def test_unknown_or_ambiguous_does_not_create(text):
    assert DemoInterpreter().interpret([text], datetime.now(UTC), "UTC").action == "clarify"


def test_demo_end_to_end(database, monkeypatch):
    connection, _ = database
    monkeypatch.setenv("AI_MODE", "demo")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    def forbidden(*args, **kwargs):
        raise AssertionError("Деморежим не должен обращаться к OpenAI")

    monkeypatch.setattr("helper_bot.ai.OpenAI", forbidden)
    monkeypatch.setattr("helper_bot.speech.OpenAI", forbidden)

    def session():
        with Session(connection, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[database_dependency] = session
    try:
        with TestClient(app) as client:
            client.headers["Origin"] = "http://127.0.0.1:8000"
            client.post("/api/v1/session", json={"timezone": "Europe/Moscow"})
            assert client.get("/api/v1/capabilities").json() == {"ai_mode": "demo"}

            def send(text, key=None):
                response = client.post(
                    "/api/v1/chat/messages", json={"text": text, "request_id": str(key or uuid4())}
                )
                assert response.status_code == 200, response.text
                return response.json()

            assert send("Напомни завтра позвонить Ивану")["status"] == "needs_clarification"
            key = uuid4()
            reply = send("в 10:00", key)
            assert reply["status"] == "completed"
            assert send("в 10:00", key) == reply
            assert len(send("Покажи планы на завтра")["entries"]) == 1
            assert len(send("Найди напоминание про Ивану")["entries"]) == 1
            assert send("Создай встречу с Анной завтра в 15:00")["entries"][0]["kind"] == "meeting"
            assert send("Создай задачу купить молоко")["entries"][0]["scheduled_at"] is None
            result = client.post(
                "/api/v1/speech/transcriptions",
                content=b"\x1aE\xdf\xa3demo",
                headers={"Content-Type": "audio/webm"},
            )
            assert result.status_code == 200
            assert result.json()["simulated"] is True
            assert len(client.get("/api/v1/entries").json()) == 3
    finally:
        app.dependency_overrides.clear()
