"""Адаптеры Groq через совместимый HTTP-протокол; без отката на имитацию."""

import json
from datetime import datetime
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError
from pydantic import ValidationError

from helper_bot.ai import INSTRUCTIONS, AIUnavailable, Intent
from helper_bot.config import Settings
from helper_bot.speech import FORMATS, SpeechUnavailable

BASE_URL = "https://api.groq.com/openai/v1"


def provider_error(exc: OpenAIError) -> str:
    if isinstance(exc, APIConnectionError):
        return "Нет соединения с Groq. Проверьте сеть и доступность api.groq.com."
    if isinstance(exc, APIStatusError):
        if exc.status_code == 400:
            body = exc.body if isinstance(exc.body, dict) else {}
            if body.get("code") == "json_validate_failed":
                return "Groq вернул ответ, не соответствующий схеме. Уточните формулировку запроса."
            return "Groq отклонил параметры запроса. Проверьте настройку модели на сервере."
        if exc.status_code == 401:
            return "Groq: проверьте API-ключ на сервере."
        if exc.status_code == 429:
            return "Groq: исчерпан лимит запросов. Подождите и повторите."
        if exc.status_code == 403:
            return "Groq: доступ отклонён провайдером. Проверьте доступность сервиса."
    return "Groq временно недоступен или отклонил запрос. Повторите позже."


def intent_schema() -> dict[str, Any]:
    """Groq проверяет format=time как RFC 3339 со смещением; нам нужно местное время."""
    schema = Intent.model_json_schema()

    def strict(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("format") == "time":
                node.pop("format")
                node["pattern"] = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$"
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for child in node.values():
                strict(child)
        elif isinstance(node, list):
            for child in node:
                strict(child)

    strict(schema)
    return schema


class GroqInterpreter:
    def interpret(self, messages: list[str], now: datetime, timezone: str) -> Intent:
        settings = Settings()
        if not settings.groq_api_key.get_secret_value() or not settings.groq_model:
            raise AIUnavailable("Задайте GROQ_API_KEY и GROQ_MODEL на сервере.")
        try:
            with OpenAI(
                api_key=settings.groq_api_key.get_secret_value(),
                base_url=BASE_URL,
                timeout=25,
                max_retries=0,
            ) as client:
                result = client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[
                        {"role": "system", "content": INSTRUCTIONS},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "messages": messages,
                                    "now": now.isoformat(),
                                    "timezone": timezone,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "Intent",
                            "strict": True,
                            "schema": intent_schema(),
                        },
                    },
                    max_completion_tokens=2000,
                )
                if not result.choices or result.choices[0].finish_reason != "stop":
                    raise AIUnavailable("Groq не завершил разбор запроса. Переформулируйте его.")
                message = result.choices[0].message
                if message.refusal or not message.content:
                    raise AIUnavailable("Groq не вернул намерение. Переформулируйте запрос.")
                return Intent.model_validate_json(message.content)
        except OpenAIError as exc:
            raise AIUnavailable(provider_error(exc)) from None
        except ValidationError:
            raise AIUnavailable("Groq вернул некорректный ответ. Уточните запрос.") from None


class GroqTranscriber:
    def transcribe(self, audio: bytes, mime: str) -> str:
        settings = Settings()
        if not settings.groq_api_key.get_secret_value() or not settings.groq_stt_model:
            raise SpeechUnavailable("Задайте GROQ_API_KEY и GROQ_STT_MODEL на сервере.")
        try:
            with OpenAI(
                api_key=settings.groq_api_key.get_secret_value(),
                base_url=BASE_URL,
                timeout=30,
                max_retries=0,
            ) as client:
                result = client.audio.transcriptions.create(
                    model=settings.groq_stt_model,
                    file=(f"recording.{FORMATS[mime]}", audio, mime),
                    language="ru",
                )
                return result.text.strip()
        except OpenAIError as exc:
            raise SpeechUnavailable(provider_error(exc)) from None
