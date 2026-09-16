import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from aidevops.database import get_session
from aidevops.security import verify_password
from aidevops.main import create_app
from rbac.models import AuthToken, User
from rbac.services.accounts import ensure_admin
from ops.modules.services import sync_modules
from rbac.services.authorization import sync_rbac


@pytest.mark.asyncio
async def test_admin_bootstrap_and_rbac_are_idempotent(memory_session) -> None:
    await sync_rbac(memory_session)
    await sync_rbac(memory_session)
    await ensure_admin(memory_session, "first-secret")
    await ensure_admin(memory_session, "second-secret")
    await memory_session.commit()
    assert await memory_session.scalar(select(func.count()).select_from(User)) == 1
    admin = await memory_session.scalar(select(User).where(User.username == "admin"))
    assert admin.is_active and admin.is_staff and admin.is_superuser
    assert verify_password("second-secret", admin.password_hash)


@pytest.mark.asyncio
async def test_real_login_me_and_logout_contract(memory_session) -> None:
    await sync_rbac(memory_session)
    await sync_modules(memory_session)
    await ensure_admin(memory_session, "local-test-secret")
    await memory_session.commit()
    app = create_app(initialize_database=False)

    async def session_override():
        yield memory_session

    app.dependency_overrides[get_session] = session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/auth/login/", json={"username": "admin", "password": "local-test-secret"})
        assert login.status_code == 200, login.text
        raw_token = login.json()["token"]
        headers = {"Authorization": f"Token {raw_token}"}
        me = await client.get("/api/auth/me/", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["is_superuser"] is True
        assert me.json()["is_demo_account"] is False
        assert "rbac.module.manage" in me.json()["effective_permissions"]
        token = await memory_session.scalar(select(AuthToken))
        assert token.token_digest != raw_token
        assert len(token.token_digest) == 64
        logout = await client.post("/api/auth/logout/", headers=headers)
        assert logout.json() == {"success": True}
        assert (await client.get("/api/auth/me/", headers=headers)).status_code == 401
