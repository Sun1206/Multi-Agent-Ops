import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.dependencies import AuthContext, get_auth_context
from app.core.database import get_session
from app.main import create_app
from app.models import EventRecord, User
from app.services.modules import sync_modules


@pytest.mark.asyncio
async def test_admin_module_write_keeps_required_modules_and_creates_audit(memory_session) -> None:
    await sync_modules(memory_session)
    admin = User(username="admin", password_hash="not-used", is_active=True, is_staff=True, is_superuser=True)
    memory_session.add(admin)
    await memory_session.commit()
    app = create_app(initialize_database=False)

    async def session_override():
        yield memory_session

    async def auth_override():
        return AuthContext(user=admin, raw_token="not-used")

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_auth_context] = auth_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/module-settings/",
            json=[{"code": "dashboard", "enabled": False}, {"code": "containers", "enabled": False}],
        )
        assert response.status_code == 200, response.text
        catalog = {item["code"]: item for item in response.json()["data"]}
        assert catalog["dashboard"]["enabled"] is True
        assert catalog["containers"]["enabled"] is False
        assert await memory_session.scalar(select(func.count()).select_from(EventRecord)) == 1
        invalid = await client.patch("/api/module-settings/", json=[{"code": "missing", "enabled": False}])
        assert invalid.status_code == 400, invalid.text
        assert set(invalid.json()) == {"detail"}
