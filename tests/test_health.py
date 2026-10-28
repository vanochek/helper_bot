from fastapi.testclient import TestClient

from helper_bot.main import app

client = TestClient(app)


def test_live() -> None:
    assert client.get("/health/live").json() == {"status": "ok"}


def test_unavailable_database(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/x")
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
