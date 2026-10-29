"""Переключить адаптеры, сохранив секреты и остальные настройки."""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["demo", "openai", "groq"])
    parser.add_argument("--production", action="store_true", help="Конфигурация Docker")
    args = parser.parse_args()
    path = Path("deploy/.env" if args.production else ".env")
    if not path.exists():
        parser.error("Сначала запустите deploy-init для Docker или bootstrap для разработки.")
    lines = path.read_text(encoding="utf-8").splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    prefix = "GROQ" if args.mode == "groq" else "OPENAI"
    if args.mode != "demo" and not all(
        values.get(key, "").strip().strip("\"'")
        for key in (f"{prefix}_API_KEY", f"{prefix}_MODEL", f"{prefix}_STT_MODEL")
    ):
        parser.error(
            f"Заполните {prefix}_API_KEY, {prefix}_MODEL, {prefix}_STT_MODEL; режим не изменён."
        )
    lines = [line for line in lines if not line.startswith("AI_MODE=")]
    path.write_text("\n".join([*lines, f"AI_MODE={args.mode}", ""]), encoding="utf-8")
    print(f"Режим: {args.mode}. Настройки сохранены в {path}.")
    print(
        "Выполните python dev.py deploy-up." if args.production else "Перезапустите dev.py serve."
    )


if __name__ == "__main__":
    main()
