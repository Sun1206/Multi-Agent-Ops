from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]


def test_default_requirements_only_install_fastapi_runtime() -> None:
    content = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "fastapi" in content
    assert "django" not in content
    assert "djangorestframework" not in content


def test_default_pytest_entry_uses_fastapi_suite() -> None:
    content = (BACKEND / "pytest.ini").read_text(encoding="utf-8")
    assert "testpaths = tests_fastapi" in content
