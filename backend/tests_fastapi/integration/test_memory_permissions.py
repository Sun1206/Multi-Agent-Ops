import pytest
from httpx import ASGITransport, AsyncClient

from aidevops.dependencies import AuthContext, get_auth_context
from aidevops.database import get_session
from aidevops.main import create_app
from rbac.models import PermissionDefinition, Role, User, UserGroup
from rbac.selectors.permissions import effective_permission_codes, user_has_permissions


@pytest.mark.asyncio
async def test_direct_and_group_roles_combine_permissions(memory_session) -> None:
    direct_permission = PermissionDefinition(code="a.view", name="查看", category="test")
    group_permission = PermissionDefinition(code="b.manage", name="管理", category="test")
    direct_role = Role(code="direct", name="直属", permissions=[direct_permission])
    group_role = Role(code="group-role", name="组角色", permissions=[group_permission])
    group = UserGroup(code="group", name="用户组", roles=[group_role])
    user = User(username="demo", password_hash="not-used", roles=[direct_role], groups=[group])
    memory_session.add(user)
    await memory_session.flush()
    assert await effective_permission_codes(memory_session, user) == ["a.view", "b.manage"]
    assert await user_has_permissions(memory_session, user, ("a.view", "b.manage"))
    assert not await user_has_permissions(memory_session, user, ("missing",))


@pytest.mark.asyncio
async def test_ordinary_user_without_module_permission_is_denied(memory_session) -> None:
    user = User(username="ordinary", password_hash="not-used", is_active=True, is_superuser=False)
    memory_session.add(user)
    await memory_session.flush()
    app = create_app(initialize_database=False)

    async def session_override():
        yield memory_session

    async def auth_override():
        return AuthContext(user=user, raw_token="not-used")

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_auth_context] = auth_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put("/api/module-settings/", json=[{"code": "containers", "enabled": False}])
    assert response.status_code == 403
    assert set(response.json()) == {"detail"}
