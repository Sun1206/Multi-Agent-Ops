import pytest
from sqlalchemy import func, select

from app.models import AuthToken, EventRecord, User
from app.core.security import verify_password
from tests_fastapi.integration.test_rbac_reads import rbac_client


@pytest.mark.asyncio
async def test_user_role_group_lifecycle_and_effective_permissions(rbac_client):
    client, headers, _ = rbac_client
    permissions = (await client.get("/api/permissions/", headers=headers)).json()
    permission = next(item for item in permissions if item["code"] == "rbac.user.view")
    role = await client.post("/api/roles/", headers=headers, json={"code": "team-reader", "name": "Team reader", "permission_ids": [permission["id"], permission["id"]]})
    assert role.status_code == 201, role.text
    assert role.json()["permissions_count"] == 1
    role_id = role.json()["id"]
    user = await client.post("/api/users/", headers=headers, json={"username": "team-user", "password": "team-secret-123", "email": "team@example.com", "role_ids": [role_id]})
    assert user.status_code == 201, user.text
    user_id = user.json()["id"]
    assert user.json()["effective_permissions"] == ["rbac.user.view"]
    group = await client.post("/api/groups/", headers=headers, json={"code": "team", "name": "Team", "role_ids": [role_id], "user_ids": [user_id, user_id]})
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]
    assert group.json()["users_count"] == 1
    changed = await client.patch(f"/api/users/{user_id}/", headers=headers, json={"role_ids": [], "first_name": "Team"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["roles"] == []
    assert changed.json()["effective_permissions"] == ["rbac.user.view"]
    assert changed.json()["user_groups"][0]["id"] == group_id
    changed_role = await client.patch(f"/api/roles/{role_id}/", headers=headers, json={"description": "Changed", "permission_ids": []})
    assert changed_role.status_code == 200, changed_role.text
    assert (await client.get(f"/api/users/{user_id}/", headers=headers)).json()["effective_permissions"] == []
    assert (await client.patch(f"/api/groups/{group_id}/", headers=headers, json={"role_ids": [], "user_ids": []})).status_code == 200
    for path, id_ in (("groups", group_id), ("roles", role_id), ("users", user_id)):
        deleted = await client.delete(f"/api/{path}/{id_}/", headers=headers)
        assert deleted.status_code == 204 and deleted.content == b"", deleted.text
        assert (await client.get(f"/api/{path}/{id_}/", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_password_reset_and_disable_revoke_tokens_and_audit_is_safe(rbac_client, memory_session):
    client, headers, _ = rbac_client
    created = await client.post("/api/users/", headers=headers, json={"username": "password-user", "password": "first-secret-123"})
    assert created.status_code == 201, created.text
    id_ = created.json()["id"]
    login = await client.post("/api/auth/login/", json={"username": "password-user", "password": "first-secret-123"})
    assert login.status_code == 200, login.text
    old_headers = {"Authorization": "Token " + login.json()["token"]}
    reset = await client.post(f"/api/users/{id_}/reset_password/", headers=headers, json={"password": "second-secret-123"})
    assert reset.status_code == 200 and reset.json() == {"success": True}, reset.text
    assert (await client.get("/api/auth/me/", headers=old_headers)).status_code == 401
    assert (await client.post("/api/auth/login/", json={"username": "password-user", "password": "first-secret-123"})).status_code == 400
    login = await client.post("/api/auth/login/", json={"username": "password-user", "password": "second-secret-123"})
    assert login.status_code == 200, login.text
    changed = await client.patch(f"/api/users/{id_}/", headers=headers, json={"is_active": False})
    assert changed.status_code == 200 and changed.json()["is_active"] is False, changed.text
    assert (await client.get("/api/auth/me/", headers={"Authorization": "Token " + login.json()["token"]})).status_code == 401
    async with client._transport.app.state.session_factory() as session:
        user = await session.get(User, id_)
        assert verify_password("second-secret-123", user.password_hash)
        events = list((await session.scalars(select(EventRecord))).all())
        assert len(events) == 3
        metadata = str([item.event_metadata for item in events])
        assert "first-secret-123" not in metadata and "second-secret-123" not in metadata
        assert "argon2" not in metadata
        assert await session.scalar(select(func.count()).select_from(AuthToken).where(AuthToken.user_id == id_)) == 0


@pytest.mark.parametrize("path,payload,status", [
    ("users", {"username": "missing-password"}, 422),
    ("users", {"username": "weak", "password": "admin"}, 422),
    ("users", {"username": "  ", "password": "valid-secret"}, 422),
    ("users", {"username": "invalid-role", "password": "valid-secret", "role_ids": [999999]}, 400),
    ("users", {"username": "invalid-group", "password": "valid-secret", "group_ids": [999999]}, 400),
    ("users", {"username": "admin", "password": "valid-secret"}, 409),
    ("roles", {"code": "bad", "name": "Bad", "permission_ids": [999999]}, 400),
    ("roles", {"code": "bad", "name": "Bad", "is_builtin": True}, 422),
    ("groups", {"code": "bad", "name": "Bad", "user_ids": [999999]}, 400),
    ("groups", {"code": "bad", "name": "Bad", "role_ids": [999999]}, 400),
])
@pytest.mark.asyncio
async def test_invalid_create_is_atomic(rbac_client, path, payload, status):
    client, headers, _ = rbac_client
    before = (await client.get(f"/api/{path}/", headers=headers)).json()
    failed = await client.post(f"/api/{path}/", headers=headers, json=payload)
    assert failed.status_code == status, failed.text
    assert "valid-secret" not in failed.text
    after = await client.get(f"/api/{path}/", headers=headers)
    assert after.status_code == 200
    assert after.json() == before


@pytest.mark.asyncio
async def test_patch_missing_fields_preserves_bindings_and_null_is_rejected(rbac_client):
    client, headers, _ = rbac_client
    created = await client.post("/api/users/", headers=headers, json={"username": "patch-user", "password": "valid-secret"})
    assert created.status_code == 201, created.text
    id_ = created.json()["id"]
    changed = await client.patch(f"/api/users/{id_}/", headers=headers, json={"email": "new@example.com"})
    assert changed.status_code == 200 and changed.json()["username"] == "patch-user", changed.text
    for payload in ({"email": None}, {"role_ids": None}, {"password": ""}, {"is_active": None}, {"password_hash": "injected"}):
        failed = await client.patch(f"/api/users/{id_}/", headers=headers, json=payload)
        assert failed.status_code == 422, failed.text
    assert (await client.post("/api/auth/login/", json={"username": "patch-user", "password": "valid-secret"})).status_code == 200


@pytest.mark.asyncio
async def test_audit_records_safe_deduplicated_relation_ids(rbac_client):
    client, headers, app = rbac_client
    role_id = (await client.get("/api/roles/", headers=headers)).json()[0]["id"]
    result = await client.post("/api/users/", headers=headers, json={"username": "relation-audit", "password": "audit-secret", "role_ids": [role_id, role_id], "group_ids": []})
    assert result.status_code == 201, result.text
    async with app.state.session_factory() as session:
        event = await session.scalar(select(EventRecord).where(EventRecord.action == "create_user"))
        assert event.event_metadata["relations"] == {"role_ids": [role_id], "group_ids": []}
        assert "audit-secret" not in str(event.event_metadata)


@pytest.mark.parametrize("payload", [{"email": "role-user@example.com"}, {"is_active": False}])
@pytest.mark.asyncio
async def test_partial_update_of_role_bound_user_preserves_unsubmitted_relations(rbac_client, payload):
    client, headers, _ = rbac_client
    role_id = (await client.get("/api/roles/", headers=headers)).json()[0]["id"]
    created = await client.post("/api/users/", headers=headers, json={"username": "bound-patch", "password": "valid-secret", "role_ids": [role_id]})
    assert created.status_code == 201, created.text
    id_ = created.json()["id"]
    changed = await client.patch(f"/api/users/{id_}/", headers=headers, json=payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()["roles"][0]["id"] == role_id
