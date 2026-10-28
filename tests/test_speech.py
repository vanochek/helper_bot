import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from helper_bot.api import database as database_dependency
from helper_bot.main import app
from helper_bot.speech import MAX_AUDIO_BYTES, SpeechUnavailable
from helper_bot.speech_api import transcriber

WEBM = b"\x1a\x45\xdf\xa3" + b"test-audio"


class FakeTranscriber:
    result = "Позвонить Ивану завтра в 10"

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, mime):
        self.calls.append((audio, mime))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def speech(database):
    connection, _ = database
    fake = FakeTranscriber()

    def session():
        with Session(connection) as db:
            yield db

    app.dependency_overrides[database_dependency] = session
    app.dependency_overrides[transcriber] = lambda: fake
    try:
        with TestClient(app) as client:
            client.headers["Origin"] = "http://127.0.0.1:8000"
            yield client, fake
    finally:
        app.dependency_overrides.clear()


def upload(client, data=WEBM, mime="audio/webm;codecs=opus", **headers):
    return client.post(
        "/api/v1/speech/transcriptions", content=data, headers={"Content-Type": mime, **headers}
    )


def start(client):
    assert client.post("/api/v1/session", json={"timezone": "UTC"}).status_code == 200


def test_auth_origin_and_transcription(speech):
    client, fake = speech
    assert upload(client).status_code == 401
    start(client)
    assert upload(client, Origin="https://evil.example").status_code == 403
    response = upload(client)
    assert response.json() == {"text": fake.result}
    assert response.headers["Cache-Control"] == "no-store"
    assert fake.calls == [(WEBM, "audio/webm")]
    assert client.get("/api/v1/entries").json() == []
    assert client.get("/api/v1/chat/messages").json() == []


@pytest.mark.parametrize(
    "data,mime,status",
    [
        (b"", "audio/webm", 422),
        (b"wrong", "audio/webm", 422),
        (b"<html>", "text/html", 415),
        (b"x" * (MAX_AUDIO_BYTES + 1), "audio/webm", 413),
    ],
)
def test_reject_audio(speech, data, mime, status):
    client, fake = speech
    start(client)
    assert upload(client, data, mime).status_code == status
    assert fake.calls == []


@pytest.mark.parametrize(
    "result,status", [("", 422), ("x" * 2001, 422), (SpeechUnavailable("Нет распознавания"), 503)]
)
def test_provider_failures(speech, result, status):
    client, fake = speech
    start(client)
    fake.result = result
    assert upload(client).status_code == status


def test_stt_adapter(monkeypatch):
    from types import SimpleNamespace

    from helper_bot.speech import OpenAITranscriber

    captured = {}

    class Client:
        def __init__(self, **kwargs):
            self.audio = SimpleNamespace(transcriptions=self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=" Текст ")

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_STT_MODEL", "configured-stt")
    monkeypatch.setattr("helper_bot.speech.OpenAI", Client)
    assert OpenAITranscriber().transcribe(WEBM, "audio/webm") == "Текст"
    assert captured["file"] == ("recording.webm", WEBM, "audio/webm")
    assert captured["language"] == "ru"
    monkeypatch.setenv("OPENAI_STT_MODEL", "")
    with pytest.raises(SpeechUnavailable):
        OpenAITranscriber().transcribe(WEBM, "audio/webm")


def test_transcript_to_existing_dialog(speech):
    from uuid import uuid4

    from helper_bot.ai import Intent
    from helper_bot.chat_api import interpreter

    client, fake = speech
    start(client)

    class AI:
        def interpret(self, messages, now, timezone):
            assert messages == [fake.result]
            return Intent(
                action="create",
                kind="task",
                title="Позвонить Ивану",
                query=None,
                temporal=None,
                question=None,
            )

    app.dependency_overrides[interpreter] = AI
    transcript = upload(client).json()["text"]
    message = {"request_id": str(uuid4()), "text": transcript}
    response = client.post("/api/v1/chat/messages", json=message)
    assert response.status_code == 200
    assert response.json()["entries"][0]["title"] == "Позвонить Ивану"
    assert client.post("/api/v1/chat/messages", json=message).json() == response.json()
    assert len(client.get("/api/v1/entries").json()) == 1
