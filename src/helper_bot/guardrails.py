"""Ограничения одного процесса прототипа; общий бюджет задаётся у провайдера."""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("helper_bot.requests")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


class Guardrails:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.buckets: OrderedDict[str, tuple[int, int]] = OrderedDict()

    def allow(self, key: str, limit: int, now: int) -> bool:
        window = now // 60
        previous, count = self.buckets.get(key, (window, 0))
        count = count if previous == window else 0
        self.buckets[key] = (window, count + 1)
        self.buckets.move_to_end(key)
        while len(self.buckets) > 4096:
            self.buckets.popitem(last=False)
        return count < limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        started = time.monotonic()
        status = 500

        async def safe_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-frame-options", b"DENY"),
                        (b"permissions-policy", b"microphone=(self), camera=()"),
                    ]
                )
                if scope["path"] not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
                    headers.append(
                        (
                            b"content-security-policy",
                            b"default-src 'self'; object-src 'none'; "
                            b"base-uri 'none'; frame-ancestors 'none'",
                        )
                    )
                if scope["path"].startswith("/api/"):
                    headers = [(k, v) for k, v in headers if k.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        async def reject(code: int, detail: str) -> None:
            headers = {"Retry-After": "60"} if code == 429 else None
            await JSONResponse({"detail": detail}, status_code=code, headers=headers)(
                scope, receive, safe_send
            )

        try:
            api = scope["path"].startswith("/api/")
            if api:
                now = int(time.time())
                client = str((scope.get("client") or ("unknown", 0))[0])
                key = hashlib.sha256(client.encode()).hexdigest()
                if not self.allow("all", 600, now) or not self.allow(key, 120, now):
                    await reject(429, "Слишком много запросов. Подождите минуту.")
                    return
                if scope["method"] == "POST" and scope["path"] in {
                    "/api/v1/chat/messages",
                    "/api/v1/speech/transcriptions",
                }:
                    if not self.allow("ai-all", 40, now) or not self.allow("ai-" + key, 10, now):
                        await reject(429, "Лимит AI-запросов. Повторите через минуту.")
                        return
            if api and scope["method"] in {"POST", "PATCH", "PUT"}:
                limit = (
                    10 * 1024 * 1024 if scope["path"] == "/api/v1/speech/transcriptions" else 16384
                )
                data = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(data) + len(chunk) > limit:
                        await reject(413, "Тело запроса превышает допустимый размер.")
                        return
                    data.extend(chunk)
                    if not message.get("more_body", False):
                        break
                delivered = False

                async def replay() -> Message:
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(data), "more_body": False}
                    return await receive()

                await self.app(scope, replay, safe_send)
            else:
                await self.app(scope, receive, safe_send)
        finally:
            route = scope.get("route")
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": getattr(route, "path", "unmatched"),
                        "status": status,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    },
                    ensure_ascii=False,
                )
            )
