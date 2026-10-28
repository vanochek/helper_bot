from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from helper_bot.api import Owner, same_origin
from helper_bot.temporal import TemporalCandidate, TemporalResult, resolve

router = APIRouter(prefix="/api/v1/temporal")


def current_time() -> datetime:
    return datetime.now(UTC)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: TemporalCandidate
    purpose: Literal["task", "reminder", "meeting", "period"]


@router.post("/resolve", dependencies=[Depends(same_origin)])
def resolve_time(
    data: ResolveRequest, owner: Owner, now: Annotated[datetime, Depends(current_time)]
) -> TemporalResult:
    return resolve(data.candidate, now=now, timezone=owner.timezone, purpose=data.purpose)
