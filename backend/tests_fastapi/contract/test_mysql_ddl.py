from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from aidevops import model_registry as models  # noqa: F401
from aidevops.database import Base


def test_every_table_compiles_for_mysql_8() -> None:
    dialect = mysql.dialect()
    statements = {
        table.name: str(CreateTable(table).compile(dialect=dialect))
        for table in Base.metadata.sorted_tables
    }
    assert len(statements) >= 70
    assert "ENGINE=InnoDB" in statements["users"]
    assert "CREATE TABLE event_records" in statements["event_records"]
