import pytest
from fastapi.testclient import TestClient

from helper_bot.guardrails import Guardrails
from helper_bot.main import app


def test_headers_and_oversized_json():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/session", content=b"x" * 16385, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert len(response.headers["X-Request-ID"]) == 32
        assert "frame-ancestors 'none'" in client.get("/").headers["Content-Security-Policy"]


def test_ai_rate_limit():
    with TestClient(app) as client:
        for _ in range(10):
            assert client.post("/api/v1/chat/messages").status_code != 429
        response = client.post("/api/v1/chat/messages")
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"


def test_limiter_window_and_capacity():
    limiter = Guardrails(app)
    assert limiter.allow("test", 1, 0)
    assert not limiter.allow("test", 1, 1)
    assert limiter.allow("test", 1, 60)
    for i in range(5000):
        limiter.allow(str(i), 1, 60)
    assert len(limiter.buckets) == 4096


def test_logs_exclude_private_input():
    import io
    import logging

    from helper_bot.guardrails import logger

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    logger.addHandler(handler)
    try:
        with TestClient(app) as client:
            client.get("/api/v1/entries?q=private-search", headers={"Cookie": "secret-cookie"})
        output = buffer.getvalue()
        assert "private-search" not in output
        assert "secret-cookie" not in output
        assert "request_id" in output
    finally:
        logger.removeHandler(handler)


@pytest.mark.anyio
async def test_chunked_request_limit():
    called = False

    async def target(scope, receive, send):
        nonlocal called
        called = True

    chunks = iter(
        [
            {"type": "http.request", "body": b"x" * 9000, "more_body": True},
            {"type": "http.request", "body": b"x" * 9000, "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    await Guardrails(target)(
        {
            "type": "http",
            "path": "/api/v1/session",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 1),
        },
        receive,
        send,
    )
    assert sent[0]["status"] == 413
    assert not called
