import importlib.util
from pathlib import Path


def test_backup_roundtrip_with_data(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "backup", Path(__file__).parents[1] / "scripts/backup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.backup()
    restored = module.restore(original, keep=True)
    target = restored["database"]
    try:
        module.command(
            "psql",
            "-U",
            "helper",
            "-d",
            target,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "INSERT INTO browser_sessions(id,token_hash,timezone) VALUES "
            "('00000000-0000-0000-0000-000000000001','backup-test','UTC'); "
            "INSERT INTO entries(id,session_id,kind,title) VALUES "
            "('00000000-0000-0000-0000-000000000002',"
            "'00000000-0000-0000-0000-000000000001','task','backup-sentinel');",
        )
        sample = tmp_path / "sample.dump"
        with sample.open("xb") as output:
            module.command("pg_dump", "-U", "helper", "-d", target, "-Fc", stdout=output)
        report = module.restore(sample)
        assert report["entries"] == restored["entries"] + 1
        assert report["sessions"] == restored["sessions"] + 1
        assert report["revision"] == restored["revision"]
    finally:
        module.command("dropdb", "-U", "helper", target)
