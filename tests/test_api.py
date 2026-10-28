import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from helper_bot.api import database as database_dependency
from helper_bot.main import app


@pytest.fixture
def clients(database):
    connection, _ = database

    def session():
        with Session(connection, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[database_dependency] = session
    try:
        with TestClient(app) as first, TestClient(app) as second:
            for client in (first, second):
                client.headers["Origin"] = "http://127.0.0.1:8000"
            yield first, second
    finally:
        app.dependency_overrides.clear()


def start(client, zone="Europe/Moscow"):
    response = client.post("/api/v1/session", json={"timezone": zone})
    assert response.status_code == 200
    return response


def create(client, **fields):
    response = client.post("/api/v1/entries", json={"kind": "task", "title": "Тема", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_sessions_isolation_search_and_period(clients):
    first, second = clients
    assert first.get("/api/v1/entries").status_code == 401
    response = start(first)
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    token = first.cookies.get("helper_session")
    start(first)
    assert first.cookies.get("helper_session") == token
    start(second)
    entry = create(first, title="Подготовить презентацию", scheduled_on="2026-10-28")
    create(first, kind="meeting", title="Встреча", scheduled_at="2026-10-27T21:00:00Z")
    create(first, kind="reminder", title="Позвонить", scheduled_at="2026-10-28T20:59:59Z")
    create(first, scheduled_at="2026-10-28T21:00:00Z")
    create(first)
    create(second, title="Секретная презентация", scheduled_on="2026-10-28")
    found = first.get("/api/v1/entries", params={"q": "презентация"}).json()
    assert [item["id"] for item in found] == [entry["id"]]
    period = first.get("/api/v1/entries", params={"start": "2026-10-28", "end": "2026-10-29"})
    assert period.status_code == 200
    assert len(period.json()) == 3
    assert second.get("/api/v1/entries/" + entry["id"]).status_code == 404
    assert first.get("/api/v1/entries/" + entry["id"]).json()["title"] == entry["title"]
    assert len(first.get("/api/v1/entries", params={"limit": 2}).json()) == 2
    assert first.patch("/api/v1/session", json={"timezone": "UTC"}).status_code == 200
    assert first.get("/api/v1/session").json() == {"timezone": "UTC"}


def test_invalid_requests_and_origin(clients):
    first, _ = clients
    assert first.post("/api/v1/session", json={"timezone": "Wrong/Zone"}).status_code == 422
    start(first)
    for origin in ("https://evil.example", "null", ""):
        assert (
            first.post(
                "/api/v1/entries",
                headers={"Origin": origin},
                json={"kind": "task", "title": "Не сохранять"},
            ).status_code
            == 403
        )
    for payload in (
        {"kind": "meeting", "title": "Без времени"},
        {"kind": "task", "title": "Тема", "session_id": "чужой"},
        {"kind": "task", "title": "Тема", "scheduled_at": "2026-10-28T10:00:00"},
    ):
        assert first.post("/api/v1/entries", json=payload).status_code == 422
    for params in (
        {"start": "2026-10-28"},
        {"start": "2026-10-29", "end": "2026-10-28"},
        {"limit": 101},
        {"offset": -1},
        {"q": "   "},
    ):
        assert first.get("/api/v1/entries", params=params).status_code == 422
    assert first.get("/api/v1/entries").json() == []
    first.cookies.clear()
    first.cookies.set("helper_session", "forged-token")
    assert first.get("/api/v1/entries").status_code == 401


def test_https_cookie(clients, monkeypatch):
    first, _ = clients
    monkeypatch.setenv("APP_ORIGIN", "https://testserver")
    first.headers["Origin"] = "https://testserver"
    assert "Secure" in start(first).headers["set-cookie"]


def test_failed_commit_does_not_confirm_or_save(clients, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    first, _ = clients
    start(first)

    def fail_commit(self):
        raise SQLAlchemyError("Внутренняя ошибка, которую нельзя отправлять клиенту")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        response = first.post("/api/v1/entries", json={"kind": "task", "title": "Не сохранено"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Хранилище временно недоступно"}
    response = first.get("/api/v1/entries")
    assert response.json() == []
    assert response.headers["Cache-Control"] == "no-store"
