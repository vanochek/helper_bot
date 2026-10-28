import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("dev", Path(__file__).parents[1] / "dev.py")
assert spec and spec.loader
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


def test_sync_detects_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    module = tmp_path / ".ai/universal/rules.md"
    module.parent.mkdir(parents=True)
    module.write_text("Правила", encoding="utf-8")
    dev.sync()
    dev.sync(True)
    (tmp_path / "CLAUDE.md").write_text("Устарело", encoding="utf-8")
    with pytest.raises(RuntimeError, match="CLAUDE.md"):
        dev.sync(True)
