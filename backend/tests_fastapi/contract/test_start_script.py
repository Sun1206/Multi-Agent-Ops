from pathlib import Path


def test_start_script_uses_project_fastapi_runtime() -> None:
    backend = Path(__file__).resolve().parents[2]
    source = (backend / "start.ps1").read_text(encoding="utf-8")
    assert "app.main:app" in source
    assert ".venv" in source
    assert "manage.py" not in source
