from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from helper_bot.temporal import TemporalCandidate, period_bounds, resolve

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "relation,expected",
    [
        ("today", date(2026, 10, 28)),
        ("tomorrow", date(2026, 10, 29)),
        ("day_after_tomorrow", date(2026, 10, 30)),
        ("week_end", date(2026, 11, 1)),
    ],
)
def test_calendar_dates(relation, expected):
    result = resolve(
        TemporalCandidate(relation=relation), now=NOW, timezone="Europe/Moscow", purpose="task"
    )
    assert result.scheduled_on == expected
    assert result.scheduled_at is None


def test_next_week_and_weekday():
    result = resolve(
        TemporalCandidate(relation="next_week"), now=NOW, timezone="Europe/Moscow", purpose="period"
    )
    assert (result.start, result.end) == (date(2026, 11, 2), date(2026, 11, 9))
    friday = resolve(
        TemporalCandidate(relation="weekday", weekday=4), now=NOW, timezone="UTC", purpose="task"
    )
    assert friday.scheduled_on == date(2026, 10, 30)
    same_day = resolve(
        TemporalCandidate(relation="weekday", weekday=2), now=NOW, timezone="UTC", purpose="task"
    )
    assert same_day.status == "needs_clarification"


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25)])
def test_dst_gap_and_fold(day):
    result = resolve(
        TemporalCandidate(relation="exact", local_date=day, local_time=time(2, 30)),
        now=NOW,
        timezone="Europe/Berlin",
        purpose="meeting",
    )
    assert result.status == "needs_clarification"
    assert result.scheduled_at is None


@pytest.mark.parametrize(
    "start,end,hours",
    [
        (date(2026, 3, 29), date(2026, 3, 30), 23),
        (date(2026, 10, 25), date(2026, 10, 26), 25),
    ],
)
def test_dst_day_lengths(start, end, hours):
    lower, upper = period_bounds(start, end, "Europe/Berlin")
    assert upper - lower == timedelta(hours=hours)


def test_elapsed_hours_and_local_tomorrow():
    anchor = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    result = resolve(
        TemporalCandidate(relation="after", minutes=120),
        now=anchor,
        timezone="Europe/Berlin",
        purpose="reminder",
    )
    assert result.scheduled_at == anchor + timedelta(hours=2)
    result = resolve(
        TemporalCandidate(relation="tomorrow", local_time=time(10)),
        now=datetime(2026, 12, 31, 22, tzinfo=UTC),
        timezone="Europe/Moscow",
        purpose="meeting",
    )
    assert result.scheduled_at == datetime(2027, 1, 2, 7, tzinfo=UTC)


def test_missing_time_past_and_leap_day():
    result = resolve(
        TemporalCandidate(relation="tomorrow"), now=NOW, timezone="UTC", purpose="meeting"
    )
    assert result.status == "needs_clarification"
    past = resolve(
        TemporalCandidate(relation="today", local_time=time(1)),
        now=NOW,
        timezone="UTC",
        purpose="task",
    )
    assert past.is_past and past.scheduled_at.date() == NOW.date()
    leap = resolve(
        TemporalCandidate(relation="tomorrow"),
        now=datetime(2028, 2, 28, tzinfo=UTC),
        timezone="UTC",
        purpose="task",
    )
    assert leap.scheduled_on == date(2028, 2, 29)


@pytest.mark.parametrize(
    "fields",
    [
        {"relation": "after"},
        {"relation": "weekday", "weekday": 7},
        {"relation": "exact"},
        {"relation": "today", "minutes": 1},
        {"relation": "today", "local_time": "10:00:00+03:00"},
        {"relation": "after", "minutes": 0},
    ],
)
def test_invalid_candidate(fields):
    with pytest.raises(ValidationError):
        TemporalCandidate(**fields)


def test_limits_and_naive_anchor():
    candidate = TemporalCandidate(relation="tomorrow")
    with pytest.raises(ValueError, match="часовой пояс"):
        resolve(candidate, now=datetime(2026, 1, 1), timezone="UTC", purpose="task")
    result = resolve(
        candidate, now=datetime(9999, 12, 31, tzinfo=UTC), timezone="UTC", purpose="task"
    )
    assert result.status == "needs_clarification"
    result = resolve(
        TemporalCandidate(relation="next_week"), now=NOW, timezone="UTC", purpose="meeting"
    )
    assert result.status == "needs_clarification"


def test_ordinary_local_time_and_this_week():
    result = resolve(
        TemporalCandidate(relation="today", local_time=time(16)),
        now=NOW,
        timezone="Europe/Moscow",
        purpose="meeting",
    )
    assert result.scheduled_at == datetime(2026, 10, 28, 13, tzinfo=UTC)
    result = resolve(
        TemporalCandidate(relation="this_week"), now=NOW, timezone="UTC", purpose="period"
    )
    assert (result.start, result.end) == (date(2026, 10, 26), date(2026, 11, 2))
