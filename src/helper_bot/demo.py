"""Ограниченный локальный имитатор; не модель и не распознавание речи."""

import re
from datetime import date, datetime, time

from helper_bot.ai import Intent
from helper_bot.temporal import TemporalCandidate

HELP = (
    "Имитатор понимает шаблоны: «Создай задачу купить молоко завтра», "
    "«Напомни завтра в 10:00 позвонить Ивану», «Покажи планы на завтра», "
    "«Найди задачу про молоко». Даты: сегодня, завтра, послезавтра или ГГГГ-ММ-ДД."
)


def extract_time(text: str) -> tuple[str, TemporalCandidate | None]:
    """Удалить только поддерживаемые выражения; неоднозначности не угадывать."""
    clock = None
    clocks = list(re.finditer(r"\bв\s+(\d{1,2})(?::(\d{2}))?(?:\s+часов)?\b", text))
    if len(clocks) > 1:
        raise ValueError("Несколько времён")
    if clocks:
        match = clocks[0]
        clock = time(int(match[1]), int(match[2] or 0))
        text = text[: match.start()] + text[match.end() :]
    dates = list(re.finditer(r"\b(послезавтра|завтра|сегодня|\d{4}-\d{2}-\d{2})\b", text))
    if len(dates) > 1:
        raise ValueError("Несколько дат")
    if not dates:
        if clock:
            raise ValueError("Укажите дату вместе со временем")
        return text.strip(), None
    match = dates[0]
    value = match[0]
    relation = {"сегодня": "today", "завтра": "tomorrow", "послезавтра": "day_after_tomorrow"}
    candidate = TemporalCandidate.model_validate(
        {
            "relation": relation.get(value, "exact"),
            "local_time": clock,
            "local_date": None if value in relation else date.fromisoformat(value),
        }
    )
    return (text[: match.start()] + text[match.end() :]).strip(), candidate


class DemoInterpreter:
    def interpret(self, messages: list[str], now: datetime, timezone: str) -> Intent:
        result = Intent(
            action="clarify", kind=None, title=None, query=None, temporal=None, question=HELP
        )
        # Уточнение времени дополняет исходную команду, а не создаёт новую запись.
        text = " ".join(messages).strip()
        lowered = text.lower().replace("ё", "е")
        try:
            remainder, temporal = extract_time(lowered)
        except ValueError:
            result.question = (
                "Укажите одну корректную дату и время, например: завтра в 10:00. "
                "Для нового запроса нажмите «Отменить уточнение»."
            )
            return result
        result.temporal = temporal
        if re.match(r"^(покажи|какие|список|планы)\b", remainder):
            result.action = "list"
        elif match := re.match(
            r"^найди\s+(?:(?:задачу|встречу|напоминание)\s+)?(?:про\s+)?(.+)", remainder
        ):
            result.action = "search"
            result.query = match[1][:200]
        elif match := re.match(
            r"^(?:создай\s+|добавь\s+)?(задачу|задача|напоминание|встречу|встреча|напомни)\b[\s:,-]*(.*)",
            remainder,
        ):
            result.action = "create"
            if match[1] in {"задачу", "задача"}:
                result.kind = "task"
            elif match[1] in {"встречу", "встреча"}:
                result.kind = "meeting"
            else:
                result.kind = "reminder"
            result.title = match[2].strip(" ,.!?") or None
            # Неподдерживаемые сроки нельзя молча превращать в название записи.
            if re.search(
                r"\b(через|вечером|утром|недел\w*|понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b",
                match[2],
            ):
                result.action = "clarify"
        return result


class DemoTranscriber:
    def transcribe(self, audio: bytes, mime: str) -> str:
        return "Напомни завтра в 10:00 позвонить Ивану"
