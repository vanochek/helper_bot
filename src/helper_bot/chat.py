from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from helper_bot.ai import Interpreter
from helper_bot.api import EntryOutput
from helper_bot.models import BrowserSession, ChatMessage
from helper_bot.services import EntryService
from helper_bot.storage import EntryRepository, NewEntry
from helper_bot.temporal import resolve


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    text: str = Field(min_length=1, max_length=2000)


class Reply(BaseModel):
    status: Literal["completed", "needs_clarification", "cancelled"]
    text: str
    entries: list[EntryOutput] = Field(default_factory=list)


class Draft(BaseModel):
    messages: list[str]
    anchor: datetime
    timezone: str
    pending: NewEntry | None = None


class RequestConflict(Exception):
    pass


def handle_message(
    db: Session, owner_id: UUID, message: MessageInput, interpreter: Interpreter, now: datetime
) -> Reply:
    # Блокировка владельца сериализует вкладки и защищает общий черновик и повторные запросы.
    db.execute(text("SET LOCAL lock_timeout = '5s'"))
    owner = db.scalars(
        select(BrowserSession)
        .where(BrowserSession.id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    previous = db.get(ChatMessage, (owner_id, message.request_id))
    if previous is not None:
        if previous.text != message.text:
            raise RequestConflict("Этот request_id уже использован для другого сообщения.")
        return Reply.model_validate(previous.response)
    draft = Draft.model_validate(owner.draft) if owner.draft else None
    if draft and now - draft.anchor > timedelta(minutes=30):
        draft = None
    repository = EntryRepository(db, owner_id)

    def save(reply: Reply, pending: Draft | None = None) -> Reply:
        owner.draft = pending.model_dump(mode="json") if pending else None
        db.add(
            ChatMessage(
                session_id=owner_id,
                request_id=message.request_id,
                text=message.text,
                response=reply.model_dump(mode="json"),
            )
        )
        db.commit()
        return reply

    def created(data: NewEntry) -> Reply:
        entry = repository.create(data)
        output = EntryOutput.model_validate(entry)
        return save(Reply(status="completed", text=f"Сохранено: {entry.title}", entries=[output]))

    normalized = message.text.casefold().strip(" .!")
    if normalized in {"отмена", "отмени", "отменить", "cancel"}:
        return save(Reply(status="cancelled", text="Незавершённое действие отменено."))
    if draft and draft.pending and normalized in {"да", "подтверждаю"}:
        return created(draft.pending)
    messages = [*draft.messages, message.text] if draft else [message.text]
    anchor = draft.anchor if draft else now
    timezone = draft.timezone if draft else owner.timezone
    if len(messages) > 6:
        return save(
            Reply(status="cancelled", text="Слишком много уточнений. Начните запрос заново.")
        )
    intent = interpreter.interpret(messages, anchor, timezone)

    def clarify(question: str, pending: NewEntry | None = None) -> Reply:
        return save(
            Reply(status="needs_clarification", text=question),
            Draft(messages=messages, anchor=anchor, timezone=timezone, pending=pending),
        )

    if intent.action == "clarify":
        return clarify(intent.question or "Уточните, какую задачу или встречу нужно обработать.")
    if intent.action == "create":
        if not intent.kind or not intent.title or not intent.title.strip():
            return clarify("Укажите тип и название записи.")
        at, on = None, None
        past = False
        if intent.temporal:
            result = resolve(intent.temporal, now=anchor, timezone=timezone, purpose=intent.kind)
            if result.status == "needs_clarification":
                return clarify(result.question or "Уточните дату и время.")
            at, on, past = result.scheduled_at, result.scheduled_on, result.is_past
            # За время уточнения момент тоже мог оказаться в прошлом.
            past = past or (at is not None and at < now.astimezone(UTC))
            past = past or (on is not None and on < now.astimezone(ZoneInfo(timezone)).date())
        elif intent.kind != "task":
            return clarify("На какую дату и время запланировать запись?")
        data = NewEntry(kind=intent.kind, title=intent.title, scheduled_at=at, scheduled_on=on)
        if past:
            return clarify(
                "Это время уже прошло. Сохранить? Ответьте «да» или укажите новую дату.", data
            )
        return created(data)
    start, end = None, None
    if intent.temporal:
        result = resolve(intent.temporal, now=anchor, timezone=timezone, purpose="period")
        if result.status == "needs_clarification":
            return clarify(result.question or "Уточните период.")
        start, end = result.start, result.end
    if intent.action == "search" and not (intent.query and intent.query.strip()):
        return clarify("Какие слова искать?")
    # Для уточняемого запроса используем ту же зону, что и в начале диалога.
    application = EntryService(repository, owner)
    entries = application.list(
        start,
        end,
        intent.query if intent.action == "search" else None,
        50,
        0,
        kind=intent.kind,
        timezone=timezone,
    )
    return save(
        Reply(
            status="completed",
            text=(
                "Ничего не найдено."
                if not entries
                else f"Найдено записей: {len(entries)} (не более 50)."
            ),
            entries=[EntryOutput.model_validate(entry) for entry in entries],
        )
    )
