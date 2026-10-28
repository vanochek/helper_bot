# Голосовой помощник

Прототип управления задачами, напоминаниями и встречами через речь и текст.
Сейчас подготовлен каркас разработки; пользовательские сценарии ещё не реализованы.

## Запуск в Windows

Нужны Python 3.14, Git и запущенный Docker Desktop с Linux containers.

```powershell
python -m pip install uv
python dev.py bootstrap
python dev.py check
python dev.py smoke
python dev.py serve
```

Открыть http://127.0.0.1:8000; API: /docs, проверки: /health/live и /health/ready.
Bootstrap создаёт .env с локальным случайным паролем, окружение из uv.lock и запускает PostgreSQL.
Повторный запуск сохраняет .env и данные. Остановка БД: `docker compose stop`.
Не удаляйте volume: он хранит данные. Порт 55432 должен быть свободен.
Ключ OpenAI потребуется при реализации AI; текущие проверки работают без него.

## Навигация

- [Состояние](docs/STATE.md), [план](docs/ROADMAP.md), [решения](docs/DECISIONS.md).
- [Архитектурное предложение](voice_assistant_architecture.md), [ТЗ](Testovoe_zadanie_golosovoj.pdf).
- [Разбор образцов](docs/REFERENCE_REVIEW.md), [правила агентов](AGENTS.md).

`src/helper_bot` — приложение, `tests` — тесты, `migrations` — изменения схемы,
`.ai` — исходные инструкции, `dev.py` — единые команды.
Для нового агента: прочитать AGENTS.md и документы состояния до изменения файлов.
