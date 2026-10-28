from datetime import date
from uuid import UUID

from helper_bot.models import BrowserSession, Entry
from helper_bot.storage import EntryRepository, NewEntry
from helper_bot.temporal import period_bounds


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
        start_at, end_at = (
            period_bounds(start, end, self.owner.timezone)
            if start is not None and end is not None
            else (None, None)
        )
        return self.repository.find(
            start,
            end,
            start_at,
            end_at,
            query,
            limit,
            offset,
        )
