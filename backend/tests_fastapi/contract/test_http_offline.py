from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from aidevops.dependencies import AuthContext, get_auth_context
from aidevops.database import get_session
from aidevops.main import create_app
from rbac.models import User
from rbac.schemas.auth import UserResponse


class FakeSession:
    """为离线 HTTP 契约测试记录提交次数。"""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def user_response() -> UserResponse:
    """构造前端当前用户接口的稳定示例响应。"""
    return UserResponse(
        id=1,
        username="admin",
        email="admin@example.com",
        first_name="",
        last_name="",
        is_active=True,
        is_staff=True,
        is_superuser=True,
        date_joined=datetime.now(timezone.utc),
        last_login=None,
        roles=[],
        user_groups=[],
        effective_permissions=["rbac.module.manage"],
        display_name="admin",
    )


@pytest.mark.asyncio
async def test_login_keeps_token_and_user_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from rbac.api import auth as auth_router

    app = create_app(initialize_database=False)
    fake_session = FakeSession()

    async def session_override():
        yield fake_session

    async def no_sync(_session):
        return None

    async def authenticated(_session, _username, _password):
        return SimpleNamespace(id=1)

    async def token(_session, _user):
        return "raw-token"

    async def serialized(_session, _user):
        return user_response()

    app.dependency_overrides[get_session] = session_override
    monkeypatch.setattr(auth_router, "sync_rbac", no_sync)
    monkeypatch.setattr(auth_router, "authenticate_credentials", authenticated)
    monkeypatch.setattr(auth_router, "issue_token", token)
    monkeypatch.setattr(auth_router, "serialize_user", serialized)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/auth/login/", json={"username": "admin", "password": "secret"})
    assert response.status_code == 200
    assert response.json()["token"] == "raw-token"
    assert response.json()["user"]["is_demo_account"] is False
    assert fake_session.commits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize(
    "payload",
    [
        [{"code": "containers", "enabled": False}],
        {"modules": [{"code": "containers", "enabled": False}]},
    ],
)
async def test_module_update_accepts_both_payload_shapes(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    payload: object,
) -> None:
    from aidevops import dependencies
    from ops.modules import api as module_settings

    app = create_app(initialize_database=False)
    fake_session = FakeSession()
    admin = User(
        id=1,
        username="admin",
        email="admin@example.com",
        password_hash="not-used",
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )

    async def session_override():
        yield fake_session

    async def auth_override():
        return AuthContext(user=admin, raw_token="not-persisted")

    async def allowed(_session, _user, _codes):
        return True

    async def update(_session, updates, _actor):
        assert updates[0].code == "containers"
        return []

    async def audit(*_args, **_kwargs):
        return None

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_auth_context] = auth_override
    monkeypatch.setattr(dependencies, "user_has_permissions", allowed)
    monkeypatch.setattr(module_settings, "update_module_settings", update)
    monkeypatch.setattr(module_settings, "record_event", audit)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, "/api/module-settings/", json=payload)
    assert response.status_code == 200
    assert response.json() == {"success": True, "data": []}
    assert fake_session.commits == 1
