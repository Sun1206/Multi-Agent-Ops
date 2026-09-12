import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import models
from app.core.database import Base


def test_aiops_models_have_only_one_prefix() -> None:
    assert models.AIOpsModelProvider.__tablename__ == "aiops_modelprovider"
    assert not any(name.startswith("aiops_aiops") for name in Base.metadata.tables)
    for name in models.__all__:
        if name.startswith("AIOps"):
            assert getattr(models, name).__tablename__ == "aiops_" + name.removeprefix("AIOps").lower()


def test_rename_migration_is_reversible_and_preserves_tables() -> None:
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0002_normalize_aiops_names.py"
    assert path.exists(), "需要独立的重命名迁移，不能修改已执行的初始迁移"
    spec = importlib.util.spec_from_file_location("rename_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0001_fastapi_initial"
    assert len(module.TABLE_RENAMES) == 14
    for method in (module.upgrade, module.downgrade):
        output = StringIO()
        context = MigrationContext.configure(dialect_name="mysql", opts={"as_sql": True, "output_buffer": output})
        with Operations.context(context):
            method()
        sql = output.getvalue()
        assert sql.count("RENAME TABLE") == 1
        assert "DROP TABLE" not in sql and "CREATE TABLE" not in sql
        for old, new in module.TABLE_RENAMES:
            expected = f"`{old}` TO `{new}`" if method == module.upgrade else f"`{new}` TO `{old}`"
            assert expected in sql
