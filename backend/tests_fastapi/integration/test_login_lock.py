import pytest
from sqlalchemy.dialects import mysql

from app.core.security import hash_password
from app.models import User
from app.services.accounts import authenticate_credentials


@pytest.mark.asyncio
async def test_login_current_read_locks_password_until_token_transaction_ends(memory_session, monkeypatch):
    user = User(username="locked-login", password_hash=hash_password("valid-secret"), roles=[], groups=[])
    memory_session.add(user)
    await memory_session.commit()
    statements = []
    original = memory_session.execute
    async def capture(statement, *args, **kwargs):
        statements.append(str(statement.compile(dialect=mysql.dialect())))
        return await original(statement, *args, **kwargs)
    monkeypatch.setattr(memory_session, "execute", capture)
    result = await authenticate_credentials(memory_session, "locked-login", "valid-secret")
    assert result is not None
    assert "FOR UPDATE" in statements[0], "校验密码前必须锁定当前账号，以串行化密码重置和令牌签发"
