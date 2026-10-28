from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from helper_bot.ai import AIUnavailable, Interpreter, OpenAIInterpreter
from helper_bot.api import Db, Owner, same_origin
from helper_bot.chat import MessageInput, Reply, RequestConflict, handle_message
from helper_bot.config import Settings
from helper_bot.demo import DemoInterpreter
from helper_bot.models import ChatMessage
from helper_bot.temporal_api import current_time

router = APIRouter(prefix="/api/v1/chat")


def interpreter() -> Interpreter:
    return DemoInterpreter() if Settings().ai_mode == "demo" else OpenAIInterpreter()


@router.post("/messages", dependencies=[Depends(same_origin)])
def send(
    message: MessageInput, db: Db, owner: Owner, ai: Annotated[Interpreter, Depends(interpreter)]
) -> Reply:
    try:
        return handle_message(db, owner.id, message, ai, current_time())
    except AIUnavailable as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from exc
    except RequestConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            422, "Не удалось проверить параметры действия. Уточните запрос."
        ) from exc


@router.get("/messages")
def history(db: Db, owner: Owner) -> list[dict[str, object]]:
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == owner.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.request_id)
            .limit(50)
        )
    )
    return [
        {"request_id": str(row.request_id), "text": row.text, "response": row.response}
        for row in reversed(rows)
    ]
