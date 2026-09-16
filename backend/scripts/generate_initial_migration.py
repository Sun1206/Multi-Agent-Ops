# 在不连接数据库的情况下生成不可变 MySQL 初始迁移快照。

from pathlib import Path

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from aidevops.database import load_domain_models
from aidevops.database import Base


OUTPUT = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_fastapi_initial.py"


load_domain_models()

def render_migration() -> str:
    dialect = mysql.dialect()
    tables = list(Base.metadata.sorted_tables)
    upgrade_sql: list[str] = []
    for table in tables:
        upgrade_sql.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        upgrade_sql.extend(
            str(CreateIndex(index).compile(dialect=dialect)).strip()
            for index in sorted(table.indexes, key=lambda item: item.name or "")
        )
    downgrade_sql = [f"DROP TABLE {dialect.identifier_preparer.quote(table.name)}" for table in reversed(tables)]
    return f'''"""Immutable MySQL 8 schema snapshot for the FastAPI backend.

Revision ID: 0001_fastapi_initial
Revises:
"""

from alembic import op


revision = "0001_fastapi_initial"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE_SQL = {upgrade_sql!r}
DOWNGRADE_SQL = {downgrade_sql!r}


def upgrade() -> None:
    """执行固定 MySQL 8 初始表结构和索引快照。"""
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    """按外键逆序删除初始迁移创建的全部表。"""
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
'''


def main() -> None:
    OUTPUT.write_text(render_migration(), encoding="utf-8", newline="\n")
    print(f"generated immutable migration {OUTPUT}")


if __name__ == "__main__":
    main()
