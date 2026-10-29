"""Создать локальную конфигурацию, не перезаписывая существующие секреты."""

import secrets
from pathlib import Path

path = Path("deploy/.env")
with path.open("x", encoding="utf-8") as output:
    output.write(
        "DOMAIN=http://localhost\nAPP_ORIGIN=http://localhost:18080\n"
        "HTTP_PORT=18080\nHTTPS_PORT=18443\n"
        "BIND_HOST=127.0.0.1\n"
        f"DB_OWNER_PASSWORD={secrets.token_hex(32)}\n"
        f"DB_APP_PASSWORD={secrets.token_hex(32)}\n"
        "GROQ_API_KEY=\nGROQ_MODEL=openai/gpt-oss-120b\n"
        "GROQ_STT_MODEL=whisper-large-v3-turbo\n"
        "AI_MODE=demo\nOPENAI_API_KEY=\nOPENAI_MODEL=\nOPENAI_STT_MODEL=\n"
    )
print("Создан deploy/.env. Для публикации задайте домен, origin, порты 80/443 и AI-настройки.")
