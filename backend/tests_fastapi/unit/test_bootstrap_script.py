from pathlib import Path


def test_bootstrap_password_is_read_from_environment_only() -> None:
    backend = Path(__file__).resolve().parents[2]
    source = (backend / "scripts" / "bootstrap_data.py").read_text(encoding="utf-8")
    assert "aiops_admin_initial_password" in source
    assert "argparse" not in source
    assert "sys.argv" not in source
