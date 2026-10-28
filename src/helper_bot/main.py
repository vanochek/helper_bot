from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from helper_bot.api import router
from helper_bot.config import Settings

app = FastAPI(title="Голосовой помощник", version="0.1.0")
app.include_router(router)


@app.middleware("http")
async def private_responses(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse({"detail": "Хранилище временно недоступно"}, status_code=503)


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
