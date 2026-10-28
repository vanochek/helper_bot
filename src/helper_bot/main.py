from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from helper_bot.config import Settings

app = FastAPI(title="Голосовой помощник", version="0.1.0")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> JSONResponse:
    engine = create_engine(Settings().database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except SQLAlchemyError:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    finally:
        engine.dispose()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (
        '<html lang="ru"><meta charset="utf-8"><title>Помощник</title>'
        "<h1>Голосовой помощник</h1><p>Окружение подготовлено.</p>"
        "<p>Сценарии ассистента в разработке.</p></html>"
    )
