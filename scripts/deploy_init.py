"""Создать локальную конфигурацию, не перезаписывая существующие секреты."""

import secrets
from pathlib import Path

path = Path("deploy/.env")
with path.open("x", encoding="utf-8") as output:
    output.write(
        "DOMAIN=localhost\nAPP_ORIGIN=https://localhost:18443\n"
        "HTTP_PORT=18080\nHTTPS_PORT=18443\n"
        "BIND_HOST=127.0.0.1\n"
        f"DB_OWNER_PASSWORD={secrets.token_hex(32)}\n"
        f"DB_APP_PASSWORD={secrets.token_hex(32)}\n"
        "OPENAI_API_KEY=\nOPENAI_MODEL=\nOPENAI_STT_MODEL=\n"
    )
print("Создан deploy/.env. Для публикации задайте домен, origin, порты 80/443 и AI-настройки.")
