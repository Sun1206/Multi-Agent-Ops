import pytest

from scripts.create_databases import quote_identifier


@pytest.mark.parametrize("name", ["ai_ops; DROP DATABASE mysql", "ai-ops", "`ai_ops`"]) 
def test_database_identifier_rejects_unsafe_characters(name: str) -> None:
    with pytest.raises(ValueError, match="数据库名称只能包含"):
        quote_identifier(name)


def test_database_identifier_is_quoted() -> None:
    assert quote_identifier("ai_ops_test") == "`ai_ops_test`"
