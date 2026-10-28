"""Единые команды разработки и проверки."""

import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def uv(*args: str) -> None:
    run(sys.executable, "-m", "uv", *args)


def sync(check: bool = False) -> None:
    modules = sorted((ROOT / ".ai/universal").glob("*.md")) + sorted(
        (ROOT / ".ai/project").glob("*.md")
    )
    if not modules:
        raise RuntimeError("Отсутствуют исходные правила")
    content = (
        "<!-- Создано dev.py sync-agents; редактируйте .ai -->\n\n"
        + "\n\n".join(p.read_text(encoding="utf-8").strip() for p in modules)
        + "\n"
    )
    for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        path = ROOT / name
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise RuntimeError(f"Рассинхронизация: {name}")
        else:
            path.write_text(content, encoding="utf-8")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command == "sync-agents":
        sync("--check" in sys.argv)
    elif command == "bootstrap":
        env = ROOT / ".env"
        if not env.exists():
            password = secrets.token_hex(24)
            env.write_text(
                f"POSTGRES_PASSWORD={password}\n"
                f"DATABASE_URL=postgresql+psycopg://helper:{password}@127.0.0.1:55432/helper\n"
                "OPENAI_API_KEY=\n",
                encoding="utf-8",
            )
        uv("sync", "--locked")
        run("docker", "compose", "up", "-d", "--wait")
        uv("run", "--locked", "alembic", "upgrade", "head")
    elif command == "check":
        sync(True)
        uv("lock", "--check")
        uv("run", "--locked", "ruff", "check", ".")
        uv("run", "--locked", "ruff", "format", "--check", ".")
        uv("run", "--locked", "mypy")
        uv("run", "--locked", "pytest")
    elif command == "smoke":
        uv("run", "--locked", "alembic", "upgrade", "head")
        uv("run", "--locked", "python", "scripts/smoke.py")
    elif command == "serve":
        uv("run", "--locked", "uvicorn", "helper_bot.main:app", "--reload", "--no-access-log")
    elif command in {"backup", "restore-check", "restore-new"}:
        action = {"backup": "backup", "restore-check": "verify", "restore-new": "restore-new"}[
            command
        ]
        run(sys.executable, "scripts/backup.py", action, *sys.argv[2:])
    elif command == "doctor":
        run("git", "--version")
        uv("--version")
        run("docker", "info", "--format", "{{.ServerVersion}}")
    else:
        print(
            "Команды: bootstrap, check, smoke, serve, doctor, sync-agents [--check], "
            "backup, restore-check [файл], restore-new [файл]"
        )
        if command != "help":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
