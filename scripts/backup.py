"""Копирование Compose-БД и восстановление только в новую изолированную БД."""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PREFIX = ["docker", "compose", "exec", "-T", "db"]
DB_USER = "helper"
PROFILE = "development"


def command(*args: str, **kwargs):
    return subprocess.run([*PREFIX, *args], check=True, **kwargs)


def backup() -> Path:
    directory = Path("backups")
    directory.mkdir(exist_ok=True)
    path = directory / f"{PROFILE}-helper-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.dump"
    try:
        with path.open("xb") as output:
            command("pg_dump", "-U", DB_USER, "-d", "helper", "-Fc", stdout=output)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    print(f"Резервная копия: {path}")
    return path


def restore(path: Path, keep: bool = False) -> dict:
    if not path.is_file():
        raise ValueError("Файл резервной копии не найден")
    target = "restore_" + uuid4().hex
    command("createdb", "-U", DB_USER, target)
    try:
        with path.open("rb") as source:
            command(
                "pg_restore",
                "-U",
                DB_USER,
                "-d",
                target,
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                stdin=source,
            )
        sql = """SELECT json_build_object(
            'revision', (SELECT version_num FROM alembic_version),
            'sessions', (SELECT count(*) FROM browser_sessions),
            'entries', (SELECT count(*) FROM entries),
            'messages', (SELECT count(*) FROM chat_messages));"""
        result = command(
            "psql",
            "-U",
            DB_USER,
            "-d",
            target,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
            capture_output=True,
            text=True,
        )
        report = {"database": target, "retained": keep, **json.loads(result.stdout)}
        print(json.dumps(report, ensure_ascii=False))
        return report
    finally:
        if not keep:
            if not re.fullmatch(r"restore_[a-f0-9]{32}", target):
                raise ValueError("Недопустимое имя временной БД")
            command("dropdb", "-U", DB_USER, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "verify", "restore-new"])
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument(
        "--production",
        action="store_true",
        help="Использовать отдельный профиль deploy/compose.yaml",
    )
    args = parser.parse_args()
    if args.production:
        PREFIX = [
            "docker",
            "compose",
            "--env-file",
            "deploy/.env",
            "-f",
            "deploy/compose.yaml",
            "exec",
            "-T",
            "db",
        ]
        DB_USER = "helper_owner"
        PROFILE = "production"
    if args.action == "backup":
        backup()
    else:
        restore(args.path or backup(), keep=args.action == "restore-new")
