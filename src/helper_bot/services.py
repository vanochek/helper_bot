from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from helper_bot.models import BrowserSession, Entry
from helper_bot.storage import EntryRepository, NewEntry


class EntryService:
    def __init__(self, repository: EntryRepository, owner: BrowserSession):
        self.repository = repository
        self.owner = owner

    def create(self, data: NewEntry) -> Entry:
        entry = self.repository.create(data)
        self.repository.db.commit()
        return entry

    def get(self, entry_id: UUID) -> Entry | None:
        return self.repository.get(entry_id)

    def list(
        self, start: date | None, end: date | None, query: str | None, limit: int, offset: int
    ) -> list[Entry]:
        if (start is None) != (end is None) or (start and end and start >= end):
            raise ValueError("Задайте обе границы: начало строго раньше конца")
        zone = ZoneInfo(self.owner.timezone)
        return self.repository.find(
            start,
            end,
            datetime.combine(start, time.min, zone) if start else None,
            datetime.combine(end, time.min, zone) if end else None,
            query,
            limit,
            offset,
        )
