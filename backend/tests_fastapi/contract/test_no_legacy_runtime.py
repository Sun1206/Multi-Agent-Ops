import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]


def test_django_source_and_migration_generator_are_removed() -> None:
    legacy = (
        "aiops", "common", "config", "eventwall", "ops", "rbac", "tests",
        "manage.py", "db.sqlite3", "scripts/generate_domain_models.py",
    )
    remaining = [name for name in legacy if (BACKEND / name).exists()]
    assert remaining == []


def test_python_runtime_has_no_django_or_legacy_imports() -> None:
    forbidden = {"django", "rest_framework", "aiops", "common", "config", "eventwall", "ops", "rbac"}
    for folder in ("app", "scripts", "alembic"):
        for path in (BACKEND / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                assert not any(name.split(".")[0] in forbidden for name in names), str(path)
