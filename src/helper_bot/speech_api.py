from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from helper_bot.api import Owner, same_origin
from helper_bot.config import Settings
from helper_bot.demo import DemoTranscriber
from helper_bot.groq import GroqTranscriber
from helper_bot.speech import (
    FORMATS,
    MAX_AUDIO_BYTES,
    OpenAITranscriber,
    SpeechUnavailable,
    Transcriber,
    valid_header,
)

router = APIRouter(prefix="/api/v1/speech")


def transcriber() -> Transcriber:
    if Settings().ai_mode == "groq":
        return GroqTranscriber()
    return DemoTranscriber() if Settings().ai_mode == "demo" else OpenAITranscriber()


class Transcript(BaseModel):
    text: str
    simulated: bool = False


@router.post("/transcriptions", dependencies=[Depends(same_origin)])
async def transcribe(
    request: Request, owner: Owner, adapter: Annotated[Transcriber, Depends(transcriber)]
) -> Transcript:
    mime = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime not in FORMATS:
        raise HTTPException(415, "Поддерживаются WebM, MP4 и WAV.")
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Запись превышает 10 МиБ. Запишите более короткое сообщение.")
        audio.extend(chunk)
    if not audio or not valid_header(audio, mime):
        raise HTTPException(422, "Пустая запись или неверный формат аудио.")
    try:
        result = (await run_in_threadpool(adapter.transcribe, bytes(audio), mime)).strip()
    except SpeechUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not result:
        raise HTTPException(422, "Речь не распознана. Попробуйте ещё раз или введите текст.")
    if len(result) > 2000:
        raise HTTPException(422, "Распознанный текст слишком длинный. Сократите сообщение.")
    return Transcript(text=result, simulated=isinstance(adapter, DemoTranscriber))
