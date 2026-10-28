import hashlib
import secrets
from datetime import date
from typing import Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from helper_bot.models import BrowserSession, Entry


class NewEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    kind: Literal["task", "reminder", "meeting"]
    title: str = Field(min_length=1, max_length=500)
    details: str | None = Field(default=None, max_length=10000)
    scheduled_at: AwareDatetime | None = None
    scheduled_on: date | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        if self.scheduled_at is not None and self.scheduled_on is not None:
            raise ValueError("Нельзя одновременно задать дату и точное время")
        if self.kind != "task" and self.scheduled_at is None:
            raise ValueError("Встреча и напоминание требуют точного времени")
        if self.ends_at is not None and (
            self.kind != "meeting" or self.scheduled_at is None or self.ends_at <= self.scheduled_at
        ):
            raise ValueError("Окончание встречи должно быть позже начала")
        return self


def create_session(db: Session, timezone: str) -> tuple[BrowserSession, str]:
    ZoneInfo(timezone)
    token = secrets.token_urlsafe(32)
    owner = BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), timezone=timezone)
    db.add(owner)
    db.flush()
    return owner, token


def resolve_session(db: Session, token: str) -> BrowserSession | None:
    return db.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )


class EntryRepository:
    """Область владельца задаёт доверенный вызывающий код; транзакцией управляет сервис."""

    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id

    def create(self, data: NewEntry) -> Entry:
        entry = Entry(session_id=self.owner_id, **data.model_dump())
        self.db.add(entry)
        self.db.flush()
        return entry

    def get(self, entry_id: UUID) -> Entry | None:
        return self.db.scalar(
            select(Entry).where(Entry.session_id == self.owner_id, Entry.id == entry_id)
        )

    def list_recent(self, limit: int = 50, offset: int = 0) -> list[Entry]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Некорректная пагинация")
        return list(
            self.db.scalars(
                select(Entry)
                .where(Entry.session_id == self.owner_id)
                .order_by(Entry.created_at.desc(), Entry.id)
                .limit(limit)
                .offset(offset)
            )
        )
