from pathlib import Path
import os
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[2]


def test_alembic_runtime_uses_fastapi_metadata() -> None:
    env = (BACKEND / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "Base.metadata" in env
    assert "async_engine_from_config" in env
    assert "django" not in env.lower()


def test_initial_revision_has_upgrade_and_downgrade() -> None:
    revision = BACKEND / "alembic" / "versions" / "0001_fastapi_initial.py"
    content = revision.read_text(encoding="utf-8")
    assert "def upgrade()" in content
    assert "def downgrade()" in content
    assert "UPGRADE_SQL" in content
    assert "DOWNGRADE_SQL" in content
    assert "from app" not in content
    assert "CREATE TABLE users" in content
    assert "DROP TABLE users" in content


def test_offline_alembic_accepts_password_with_reserved_characters() -> None:
    environment = {
        **os.environ,
        "MYSQL_USER": "offline",
        "MYSQL_PASSWORD": "p@ss%word",
        "AIOPS_DATABASE_MODE": "test",
        "PYTHONUTF8": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "p%40ss%25word" not in result.stderr
    assert "CREATE TABLE users" in result.stdout
