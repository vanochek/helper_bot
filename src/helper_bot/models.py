from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Computed, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    timezone: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint("kind IN ('task','reminder','meeting')", name="ck_entries_kind"),
        CheckConstraint("status IN ('open','done','cancelled')", name="ck_entries_status"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="ck_entries_title"),
        CheckConstraint("details IS NULL OR length(details) <= 10000", name="ck_entries_details"),
        CheckConstraint("scheduled_at IS NULL OR scheduled_on IS NULL", name="ck_entries_schedule"),
        CheckConstraint(
            "kind = 'task' OR scheduled_at IS NOT NULL", name="ck_entries_required_time"
        ),
        CheckConstraint(
            "ends_at IS NULL OR (kind = 'meeting' AND scheduled_at IS NOT NULL "
            "AND ends_at > scheduled_at)",
            name="ck_entries_end",
        ),
        Index("ix_entries_owner_time", "session_id", "scheduled_at"),
        Index("ix_entries_owner_date", "session_id", "scheduled_on"),
        Index("ix_entries_owner_created", "session_id", "created_at"),
        Index("ix_entries_search_ru", "search_vector", postgresql_using="gin"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("browser_sessions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(500))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', title || ' ' || coalesce(details, ''))", persisted=True),
    )
    details: Mapped[str | None]
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_on: Mapped[date | None]
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
