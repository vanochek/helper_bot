"""Детерминированное разрешение временных кандидатов без обращения к LLM."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TemporalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    relation: Literal[
        "today",
        "tomorrow",
        "day_after_tomorrow",
        "weekday",
        "this_week",
        "next_week",
        "week_end",
        "after",
        "exact",
    ]
    local_date: date | None = None
    local_time: time | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    minutes: int | None = Field(default=None, ge=1, le=525600)

    @model_validator(mode="after")
    def valid_fields(self) -> "TemporalCandidate":
        for name, relation in (
            ("local_date", "exact"),
            ("weekday", "weekday"),
            ("minutes", "after"),
        ):
            if (getattr(self, name) is not None) != (self.relation == relation):
                raise ValueError(f"Поле {name} требуется только для {relation}")
        if self.local_time is not None:
            if self.local_time.tzinfo is not None:
                raise ValueError("Локальное время должно быть без смещения")
            if self.relation in {"after", "this_week", "next_week"}:
                raise ValueError("Время несовместимо с выбранным периодом")
        return self


class TemporalResult(BaseModel):
    status: Literal["resolved", "needs_clarification"]
    scheduled_at: datetime | None = None
    scheduled_on: date | None = None
    start: date | None = None
    end: date | None = None
    start_utc: datetime | None = None
    end_utc: datetime | None = None
    question: str | None = None
    is_past: bool = False


class AmbiguousTime(ValueError):
    pass


def local_instant(day: date, clock: time, zone: ZoneInfo) -> datetime:
    wall = datetime.combine(day, clock).replace(tzinfo=None)
    candidates = set()
    for fold in (0, 1):
        utc = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.add(utc)
    if not candidates:
        raise AmbiguousTime("Такого местного времени не существует. Укажите другое время.")
    if len(candidates) > 1:
        raise AmbiguousTime("Местное время повторяется. Укажите точный момент со смещением UTC.")
    return candidates.pop()


def period_bounds(start: date, end: date, timezone: str) -> tuple[datetime, datetime]:
    if start >= end:
        raise ValueError("Начало периода должно быть раньше конца")
    zone = ZoneInfo(timezone)
    return local_instant(start, time.min, zone), local_instant(end, time.min, zone)


def resolve(
    candidate: TemporalCandidate,
    *,
    now: datetime,
    timezone: str,
    purpose: Literal["task", "reminder", "meeting", "period"],
) -> TemporalResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Текущее время должно содержать часовой пояс")
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()

    def clarify(question: str) -> TemporalResult:
        return TemporalResult(status="needs_clarification", question=question)

    try:
        if candidate.relation == "after":
            if purpose == "period":
                return clarify("Укажите начало и конец периода.")
            assert candidate.minutes is not None
            return TemporalResult(
                status="resolved",
                scheduled_at=now.astimezone(UTC) + timedelta(minutes=candidate.minutes),
            )
        monday = today - timedelta(days=today.weekday())
        if candidate.relation in {"this_week", "next_week"}:
            if purpose != "period":
                return clarify("Укажите конкретный день и, при необходимости, время.")
            start = monday + timedelta(days=7 if candidate.relation == "next_week" else 0)
            end = start + timedelta(days=7)
        else:
            match candidate.relation:
                case "today":
                    start = today
                case "tomorrow":
                    start = today + timedelta(days=1)
                case "day_after_tomorrow":
                    start = today + timedelta(days=2)
                case "week_end":
                    start = monday + timedelta(days=6)
                case "weekday":
                    assert candidate.weekday is not None
                    delta = (candidate.weekday - today.weekday()) % 7
                    if delta == 0:
                        return clarify(
                            "Вы имеете в виду сегодня или этот день на следующей неделе?"
                        )
                    start = today + timedelta(days=delta)
                case "exact":
                    assert candidate.local_date is not None
                    start = candidate.local_date
                case _:
                    raise ValueError("Неизвестный временной кандидат")
            if purpose != "period":
                if candidate.local_time is None:
                    if purpose != "task":
                        return clarify("На какое время запланировать запись?")
                    return TemporalResult(
                        status="resolved", scheduled_on=start, is_past=start < today
                    )
                instant = local_instant(start, candidate.local_time, zone)
                return TemporalResult(
                    status="resolved", scheduled_at=instant, is_past=instant < now.astimezone(UTC)
                )
            if candidate.local_time is not None:
                return clarify("Для календарного периода укажите даты без времени.")
            end = start + timedelta(days=1)
        start_utc, end_utc = period_bounds(start, end, timezone)
        return TemporalResult(
            status="resolved",
            start=start,
            end=end,
            start_utc=start_utc,
            end_utc=end_utc,
            is_past=end_utc <= now.astimezone(UTC),
        )
    except AmbiguousTime as exc:
        return clarify(str(exc))
    except OverflowError:
        return clarify("Дата выходит за поддерживаемый диапазон. Укажите другую дату.")
