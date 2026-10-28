FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM python:3.14-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY deploy/migrate.py ./deploy/migrate.py
RUN uv sync --locked --no-dev && useradd --uid 10001 --create-home app
USER 10001
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "helper_bot.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers", "--limit-concurrency", "32"]
