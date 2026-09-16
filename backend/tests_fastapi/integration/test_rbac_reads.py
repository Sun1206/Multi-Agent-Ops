import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker

from aidevops.main import create_app
from rbac.models import User
from rbac.services.accounts import ensure_admin, issue_token
from rbac.services.authorization import sync_rbac


@pytest_asyncio.fixture
async def rbac_client(memory_session):
    engine = memory_session.bind
    async with engine.connect() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    await sync_rbac(memory_session)
    admin = await ensure_admin(memory_session, "test-admin-secret")
    token = await issue_token(memory_session, admin)
    await memory_session.commit()
    app = create_app(initialize_database=False)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, {"Authorization": f"Token {token}"}, app


@pytest.mark.asyncio
async def test_lists_preserve_frontend_shapes(rbac_client):
    client, headers, _ = rbac_client
    users = await client.get("/api/users/", headers=headers)
    assert users.status_code == 200, users.text
    assert set(users.json()) == {"count", "next", "previous", "results"}
    user = users.json()["results"][0]
    assert user["username"] == "admin"
    assert "password" not in user and "password_hash" not in user
    assert user["date_joined"].endswith("Z") or user["date_joined"].endswith("+00:00")
    for path, count in (("roles", 5), ("groups", 0), ("permissions", 90)):
        result = await client.get(f"/api/{path}/", headers=headers)
        assert result.status_code == 200, result.text
        assert isinstance(result.json(), list) and len(result.json()) == count


@pytest.mark.asyncio
async def test_read_requires_token_and_resource_permission(rbac_client, memory_session):
    client, headers, _ = rbac_client
    for path in ("users", "roles", "groups", "permissions"):
        assert (await client.get(f"/api/{path}/")).status_code == 401
    user = User(username="reader-no-permission", password_hash="unused")
    memory_session.add(user)
    await memory_session.flush()
    raw = await issue_token(memory_session, user)
    await memory_session.commit()
    for path in ("users", "roles", "groups", "permissions"):
        result = await client.get(f"/api/{path}/", headers={"Authorization": f"Token {raw}"})
        assert result.status_code == 403, result.text


@pytest.mark.asyncio
async def test_user_pagination_search_and_detail(rbac_client, memory_session):
    client, headers, _ = rbac_client
    memory_session.add_all([User(username=f"account-{index:03}", email="team@example.com", password_hash="unused") for index in range(23)])
    await memory_session.commit()
    result = await client.get("/api/users/", headers=headers, params={"search": "account", "page_size": 10, "page": 2})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["count"] == 23 and len(body["results"]) == 10
    assert "page=3" in body["next"] and "page=1" in body["previous"]
    assert body["results"][0]["username"] == "account-010"
    detail = await client.get(f"/api/users/{body['results'][0]['id']}/", headers=headers)
    assert detail.status_code == 200 and detail.json()["username"] == "account-010"
    assert (await client.get("/api/users/999999/", headers=headers)).status_code == 404
    assert (await client.get("/api/users/", headers=headers, params={"page": 99})).status_code == 404
    assert (await client.get("/api/users/", headers=headers, params={"page_size": 0})).status_code == 422
    empty = await client.get("/api/users/", headers=headers, params={"search": "no-such-user"})
    assert empty.json()["count"] == 0 and empty.json()["results"] == []


@pytest.mark.asyncio
async def test_large_page_is_capped_and_permission_queries_are_batched(rbac_client, memory_session):
    client, headers, app = rbac_client
    memory_session.add_all([User(username=f"bulk-{index}", password_hash="unused") for index in range(205)])
    await memory_session.commit()
    queries = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(memory_session.bind.sync_engine, "before_cursor_execute", capture)
    try:
        result = await client.get("/api/users/", headers=headers, params={"page_size": 999})
    finally:
        event.remove(memory_session.bind.sync_engine, "before_cursor_execute", capture)
    assert result.status_code == 200, result.text
    assert len(result.json()["results"]) == 200
    assert len(queries) < 20, "列表权限不能逐用户查询"
