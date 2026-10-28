from collections.abc import Iterator
from datetime import date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from helper_bot.config import Settings
from helper_bot.models import BrowserSession
from helper_bot.services import EntryService
from helper_bot.storage import EntryRepository, NewEntry, create_session, resolve_session

router = APIRouter(prefix="/api/v1")
COOKIE = "helper_session"


def database() -> Iterator[Session]:
    engine = create_engine(Settings().database_url, connect_args={"connect_timeout": 5})
    try:
        with Session(engine, expire_on_commit=False) as db:
            yield db
    finally:
        engine.dispose()


Db = Annotated[Session, Depends(database)]


def same_origin(request: Request) -> None:
    if request.headers.get("origin") != Settings().app_origin:
        raise HTTPException(403, "Недопустимый источник запроса")


def owner(request: Request, db: Db) -> BrowserSession:
    token = request.cookies.get(COOKIE, "")
    found = resolve_session(db, token) if 1 <= len(token) <= 128 else None
    if found is None:
        raise HTTPException(401, "Создайте сессию")
    return found


Owner = Annotated[BrowserSession, Depends(owner)]


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError, ValueError:
            raise ValueError("Неизвестный часовой пояс IANA") from None
        return value


class EntryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    title: str
    details: str | None
    scheduled_at: datetime | None
    scheduled_on: date | None
    ends_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime


@router.post("/session", dependencies=[Depends(same_origin)])
def start_session(data: SessionInput, request: Request, response: Response, db: Db) -> SessionInput:
    token = request.cookies.get(COOKIE, "")
    existing = resolve_session(db, token) if 1 <= len(token) <= 128 else None
    if existing is not None:
        return SessionInput(timezone=existing.timezone)
    created, token = create_session(db, data.timezone)
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=Settings().app_origin.startswith("https://"),
        path="/",
    )
    return SessionInput(timezone=created.timezone)


@router.get("/session")
def get_session(current: Owner) -> SessionInput:
    return SessionInput(timezone=current.timezone)


@router.patch("/session", dependencies=[Depends(same_origin)])
def change_session(data: SessionInput, current: Owner, db: Db) -> SessionInput:
    current.timezone = data.timezone
    db.commit()
    return data


def service(db: Db, current: Owner) -> EntryService:
    return EntryService(EntryRepository(db, current.id), current)


Service = Annotated[EntryService, Depends(service)]


@router.post(
    "/entries", response_model=EntryOutput, status_code=201, dependencies=[Depends(same_origin)]
)
def create_entry(data: NewEntry, application: Service) -> EntryOutput:
    return EntryOutput.model_validate(application.create(data))


@router.get("/entries", response_model=list[EntryOutput])
def list_entries(
    application: Service,
    start: date | None = None,
    end: date | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[EntryOutput]:
    if q is not None and not q.strip():
        raise HTTPException(422, "Пустой поисковый запрос")
    try:
        return [
            EntryOutput.model_validate(entry)
            for entry in application.list(start, end, q, limit, offset)
        ]
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/entries/{entry_id}", response_model=EntryOutput)
def get_entry(entry_id: UUID, application: Service) -> EntryOutput:
    entry = application.get(entry_id)
    if entry is None:
        raise HTTPException(404, "Запись не найдена")
    return EntryOutput.model_validate(entry)
