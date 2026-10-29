"""Адаптеры Groq через совместимый HTTP-протокол; без отката на имитацию."""

import json
from datetime import datetime

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
        if exc.status_code == 401:
            return "Groq: проверьте API-ключ на сервере."
        if exc.status_code == 429:
            return "Groq: исчерпан лимит запросов. Подождите и повторите."
        if exc.status_code == 403:
            return "Groq: доступ отклонён провайдером. Проверьте доступность сервиса."
    return "Groq временно недоступен или отклонил запрос. Повторите позже."


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
                result = client.chat.completions.parse(
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
                    response_format=Intent,
                    max_completion_tokens=2000,
                )
                if not result.choices or result.choices[0].finish_reason != "stop":
                    raise AIUnavailable("Groq не завершил разбор запроса. Переформулируйте его.")
                parsed = result.choices[0].message.parsed
                if parsed is None:
                    raise AIUnavailable("Groq не вернул намерение. Переформулируйте запрос.")
                return parsed
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
