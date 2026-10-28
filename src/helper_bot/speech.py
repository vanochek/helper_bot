from typing import Protocol

from openai import OpenAI, OpenAIError

from helper_bot.config import Settings

MAX_AUDIO_BYTES = 10 * 1024 * 1024
FORMATS = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/wav": "wav"}


class SpeechUnavailable(Exception):
    pass


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, mime: str) -> str: ...


def valid_header(audio: bytes | bytearray, mime: str) -> bool:
    if mime == "audio/webm":
        return audio.startswith(b"\x1a\x45\xdf\xa3")
    if mime == "audio/mp4":
        return len(audio) >= 12 and audio[4:8] == b"ftyp"
    return len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"


class OpenAITranscriber:
    def transcribe(self, audio: bytes, mime: str) -> str:
        settings = Settings()
        if not settings.openai_api_key or not settings.openai_stt_model:
            raise SpeechUnavailable("Распознавание не настроено. Используйте текстовый ввод.")
        try:
            with OpenAI(
                api_key=settings.openai_api_key.get_secret_value(), timeout=30, max_retries=0
            ) as client:
                result = client.audio.transcriptions.create(
                    model=settings.openai_stt_model,
                    file=(f"recording.{FORMATS[mime]}", audio, mime),
                    language="ru",
                )
            return result.text.strip()
        except OpenAIError as exc:
            raise SpeechUnavailable(
                "Не удалось распознать запись. Повторите или введите текст."
            ) from exc
