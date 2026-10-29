# Подключение Groq
Владелец: Codex. Ветка: codex/groq-provider.
Область: адаптеры AI/STT, конфигурация, Docker, интерфейс, тесты, документация.
- [x] Адаптеры, переключатель demo/groq/openai и настройки.
- [x] 76 тестов, Ruff, mypy, smoke. PYTEST_ADDOPTS задаёт временную папку внутри проекта.
- [x] Docker Compose config --quiet, без раскрытия секретов.
- [x] Ключ из .env перенесён в deploy/.env; оба файла исключены из Git. AI_MODE=groq.
- [ ] Живой текст/STT: TLS к api.groq.com обрывается с UNEXPECTED_EOF_WHILE_READING до HTTP.
- [ ] Запуск Docker: загрузка образов прервана EOF от auth.docker.io; существующий PostgreSQL healthy.
- [ ] Живая проверка микрофона владельцем после восстановления сети.
Следующий шаг: проверить доступ к Groq и Docker Hub, повторить deploy-up и живую приёмку.
