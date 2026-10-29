import json
from datetime import UTC, datetime

import httpx
import pytest
from openai import OpenAI

from helper_bot.ai import AIUnavailable
from helper_bot.chat_api import interpreter
from helper_bot.groq import GroqInterpreter, GroqTranscriber
from helper_bot.speech import SpeechUnavailable
from helper_bot.speech_api import transcriber


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AI_MODE", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

    def install(handler):
        def client(**kwargs):
            assert kwargs["base_url"] == "https://api.groq.com/openai/v1"
            assert kwargs["max_retries"] == 0
            return OpenAI(
                **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))
            )

        monkeypatch.setattr("helper_bot.groq.OpenAI", client)

    return install


def completion(content, finish="stop"):
    return {
        "id": "test",
        "object": "chat.completion",
        "created": 0,
        "model": "test",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": json.dumps(content)},
            }
        ],
    }


def test_structured_intent(provider):
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/openai/v1/chat/completions"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert json.loads(body["messages"][1]["content"])["timezone"] == "Europe/Moscow"
        return httpx.Response(
            200,
            json=completion(
                {
                    "action": "create",
                    "kind": "reminder",
                    "title": "Позвонить Ивану",
                    "query": None,
                    "question": None,
                    "temporal": {"relation": "tomorrow", "local_time": "10:00:00"},
                }
            ),
        )

    provider(handler)
    assert isinstance(interpreter(), GroqInterpreter)
    result = interpreter().interpret(
        ["Напомни завтра в 10 позвонить Ивану"], datetime.now(UTC), "Europe/Moscow"
    )
    assert result.temporal.relation == "tomorrow"
    assert result.title == "Позвонить Ивану"


def test_meeting_uses_local_time_schema(provider):
    def handler(request):
        schema = json.loads(request.content)["response_format"]["json_schema"]["schema"]
        temporal = schema["$defs"]["TemporalCandidate"]
        clock = temporal["properties"]["local_time"]["anyOf"][0]
        assert "format" not in clock
        assert "pattern" in clock
        assert set(temporal["required"]) == set(temporal["properties"])
        assert temporal["additionalProperties"] is False
        return httpx.Response(
            200,
            json=completion(
                {
                    "action": "create",
                    "kind": "meeting",
                    "title": "Встреча с Анной",
                    "query": None,
                    "question": None,
                    "temporal": {"relation": "tomorrow", "local_time": "15:00:00"},
                }
            ),
        )

    provider(handler)
    result = interpreter().interpret(
        ["Создай встречу с Анной завтра в 15:00"], datetime.now(UTC), "Europe/Moscow"
    )
    assert result.temporal.local_time.hour == 15
    assert result.temporal.local_time.tzinfo is None


@pytest.mark.parametrize("clock", ["15:00:00+03:00", "25:00:00"])
def test_provider_time_still_validated_by_domain(provider, clock):
    provider(
        lambda request: httpx.Response(
            200,
            json=completion(
                {
                    "action": "create",
                    "kind": "meeting",
                    "title": "Встреча",
                    "query": None,
                    "question": None,
                    "temporal": {"relation": "tomorrow", "local_time": clock},
                }
            ),
        )
    )
    with pytest.raises(AIUnavailable, match="некорректный ответ"):
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_errors_are_sanitized(provider, status):
    provider(lambda request: httpx.Response(status, json={"error": {"message": "SECRET"}}))
    with pytest.raises(AIUnavailable) as error:
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")
    assert "SECRET" not in str(error.value)
    with pytest.raises(SpeechUnavailable) as error:
        transcriber().transcribe(b"audio", "audio/wav")
    assert "SECRET" not in str(error.value)


def test_invalid_response_does_not_produce_intent(provider):
    provider(lambda request: httpx.Response(200, json=completion({"action": "delete"})))
    with pytest.raises(AIUnavailable):
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")


def test_transcription(provider):
    def handler(request):
        assert request.url.path == "/openai/v1/audio/transcriptions"
        assert b"whisper-large-v3-turbo" in request.content
        assert b"recording.webm" in request.content
        return httpx.Response(200, json={"text": " Позвонить Ивану "})

    provider(handler)
    assert isinstance(transcriber(), GroqTranscriber)
    assert transcriber().transcribe(b"audio", "audio/webm") == "Позвонить Ивану"


def test_no_key_does_not_call_network(provider, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    provider(lambda request: pytest.fail("Не должно быть сетевого запроса"))
    with pytest.raises(AIUnavailable):
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")


def test_connection_failure_is_clear(provider):
    def handler(request):
        raise httpx.ConnectError("TLS failure", request=request)

    provider(handler)
    with pytest.raises(AIUnavailable, match="Нет соединения"):
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")


def test_single_connection_retry_recovers(provider, monkeypatch):
    monkeypatch.setattr("helper_bot.groq.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("Temporary EOF", request=request)
        return httpx.Response(
            200,
            json=completion(
                {
                    "action": "create",
                    "kind": "task",
                    "title": "Купить молоко",
                    "query": None,
                    "question": None,
                    "temporal": None,
                }
            ),
        )

    provider(handler)
    assert interpreter().interpret(["Тест"], datetime.now(UTC), "UTC").action == "create"
    assert len(calls) == 2


def test_connection_retry_is_bounded(provider, monkeypatch):
    monkeypatch.setattr("helper_bot.groq.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("Persistent EOF", request=request)

    provider(handler)
    with pytest.raises(AIUnavailable):
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")
    assert len(calls) == 2


def test_quota_is_not_automatically_retried(provider):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "quota"}})

    provider(handler)
    with pytest.raises(AIUnavailable):
        interpreter().interpret(["Тест"], datetime.now(UTC), "UTC")
    assert len(calls) == 1
