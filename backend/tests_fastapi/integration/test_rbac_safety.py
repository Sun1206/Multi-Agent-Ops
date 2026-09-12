import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models import EventRecord, PermissionDefinition, Role, User, UserGroup
from app.services.accounts import issue_token
from tests_fastapi.integration.test_rbac_reads import rbac_client


@pytest_asyncio.fixture
async def manager_objects(rbac_client, memory_session):
    codes = ["rbac.user.view", "rbac.user.manage", "rbac.role.view", "rbac.role.manage", "rbac.group.view", "rbac.group.manage", "rbac.permission.view"]
    perms = list((await memory_session.scalars(select(PermissionDefinition).where(PermissionDefinition.code.in_(codes)))).all())
    extra = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == "ops.host.terminal"))
    manager_role = Role(code="local-manager", name="Local manager", permissions=perms)
    high_role = Role(code="elevated-role", name="Elevated role", permissions=[extra])
    manager = User(username="local-manager", password_hash=hash_password("manager-secret"), roles=[manager_role], groups=[])
    target = User(username="ordinary-target", password_hash="unused", roles=[], groups=[])
    elevated = User(username="elevated-target", password_hash="unused", roles=[high_role], groups=[])
    group = UserGroup(code="elevated-group", name="Elevated group", roles=[high_role], users=[])
    builtin_group = UserGroup(code="builtin-group", name="Builtin group", is_builtin=True, roles=[], users=[])
    memory_session.add_all([manager_role, high_role, manager, target, elevated, group, builtin_group])
    await memory_session.flush()
    token = await issue_token(memory_session, manager)
    await memory_session.commit()
    return {"headers": {"Authorization": "Token " + token}, "manager": manager.id, "target": target.id, "elevated": elevated.id, "high_role": high_role.id, "high_group": group.id, "builtin_group": builtin_group.id, "extra_permission": extra.id}


@pytest.mark.parametrize("data", [{"is_active": False}, {"is_superuser": False}])
@pytest.mark.asyncio
async def test_last_enabled_superuser_cannot_be_disabled_or_demoted(rbac_client, data):
    client, headers, _ = rbac_client
    id_ = (await client.get("/api/auth/me/", headers=headers)).json()["id"]
    result = await client.patch(f"/api/users/{id_}/", headers=headers, json=data)
    assert result.status_code == 400, result.text
    assert (await client.get("/api/auth/me/", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_self_delete_is_rejected_and_second_admin_allows_safe_changes(rbac_client):
    client, headers, _ = rbac_client
    id_ = (await client.get("/api/auth/me/", headers=headers)).json()["id"]
    assert (await client.delete(f"/api/users/{id_}/", headers=headers)).status_code == 400
    second = await client.post("/api/users/", headers=headers, json={"username": "second-admin", "password": "second-secret", "is_superuser": True, "is_staff": True})
    assert second.status_code == 201, second.text
    other_id = second.json()["id"]
    changed = await client.patch(f"/api/users/{other_id}/", headers=headers, json={"is_active": False})
    assert changed.status_code == 200, changed.text
    assert (await client.patch(f"/api/users/{id_}/", headers=headers, json={"is_active": False})).status_code == 400
    assert (await client.delete(f"/api/users/{other_id}/", headers=headers)).status_code == 204


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
@pytest.mark.asyncio
async def test_ordinary_manager_cannot_elevate_identity(rbac_client, manager_objects, flag):
    client, _, _ = rbac_client
    headers = manager_objects["headers"]
    result = await client.post("/api/users/", headers=headers, json={"username": "elevated-create", "password": "valid-secret", flag: True})
    assert result.status_code == 403, result.text
    result = await client.patch(f"/api/users/{manager_objects['target']}/", headers=headers, json={flag: True})
    assert result.status_code == 403, result.text
    result = await client.patch(f"/api/users/{manager_objects['target']}/", headers=headers, json={"email": "changed@example.com", "is_staff": False, "is_superuser": False})
    assert result.status_code == 200, result.text


@pytest.mark.asyncio
async def test_ordinary_manager_cannot_modify_or_reset_superuser(rbac_client, manager_objects):
    client, admin_headers, _ = rbac_client
    id_ = (await client.get("/api/auth/me/", headers=admin_headers)).json()["id"]
    headers = manager_objects["headers"]
    assert (await client.patch(f"/api/users/{id_}/", headers=headers, json={"email": "hijack@example.com"})).status_code == 403
    assert (await client.post(f"/api/users/{id_}/reset_password/", headers=headers, json={"password": "hijack-secret"})).status_code == 403
    assert (await client.delete(f"/api/users/{id_}/", headers=headers)).status_code == 403


@pytest.mark.parametrize("kind", ["role_user", "group_user", "group_role", "group_member", "role_permissions", "existing_role", "existing_group", "existing_user"])
@pytest.mark.asyncio
async def test_indirect_privilege_escalation_is_rejected(rbac_client, manager_objects, kind):
    client, _, _ = rbac_client
    obj = manager_objects
    cases = {
        "role_user": ("post", "/api/users/", {"username": "grant-role", "password": "valid-secret", "role_ids": [obj["high_role"]]}),
        "group_user": ("patch", f"/api/users/{obj['target']}/", {"group_ids": [obj["high_group"]]}),
        "group_role": ("post", "/api/groups/", {"code": "grant-group", "name": "Grant", "role_ids": [obj["high_role"]]}),
        "group_member": ("post", "/api/groups/", {"code": "grant-member", "name": "Grant member", "user_ids": [obj["elevated"]]}),
        "role_permissions": ("post", "/api/roles/", {"code": "grant-permission", "name": "Grant permission", "permission_ids": [obj["extra_permission"]]}),
        "existing_role": ("patch", f"/api/roles/{obj['high_role']}/", {"permission_ids": []}),
        "existing_group": ("patch", f"/api/groups/{obj['high_group']}/", {"role_ids": []}),
        "existing_user": ("patch", f"/api/users/{obj['elevated']}/", {"role_ids": []}),
    }
    method, path, payload = cases[kind]
    result = await getattr(client, method)(path, headers=obj["headers"], json=payload)
    assert result.status_code == 403, result.text


@pytest.mark.asyncio
async def test_builtin_role_and_group_code_and_delete_are_protected(rbac_client, manager_objects):
    client, headers, _ = rbac_client
    role = (await client.get("/api/roles/", headers=headers)).json()[0]
    assert role["is_builtin"]
    for path, id_, code in (("roles", role["id"], role["code"]), ("groups", manager_objects["builtin_group"], "builtin-group")):
        assert (await client.delete(f"/api/{path}/{id_}/", headers=headers)).status_code == 400
        changed = await client.patch(f"/api/{path}/{id_}/", headers=headers, json={"code": "changed-code"})
        assert changed.status_code == 400, changed.text
        unchanged = await client.patch(f"/api/{path}/{id_}/", headers=headers, json={"code": code})
        assert unchanged.status_code == 200, unchanged.text


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_business_write(rbac_client, monkeypatch):
    from app.api import audit
    client, headers, app = rbac_client
    async def fail(*args, **kwargs):
        raise RuntimeError("deliberate audit failure")
    monkeypatch.setattr(audit, "record_event", fail)
    result = await client.post("/api/users/", headers=headers, json={"username": "rollback-user", "password": "rollback-secret"})
    assert result.status_code == 500, result.text
    assert "rollback-secret" not in result.text
    async with app.state.session_factory() as session:
        assert await session.scalar(select(User).where(User.username == "rollback-user")) is None
        assert await session.scalar(select(func.count()).select_from(EventRecord)) == 0


@pytest.mark.parametrize("method", ["patch", "delete"])
@pytest.mark.asyncio
async def test_role_changes_check_members_inheriting_via_groups(rbac_client, manager_objects, method):
    client, admin_headers, _ = rbac_client
    permission = next(item for item in (await client.get("/api/permissions/", headers=admin_headers)).json() if item["code"] == "rbac.user.view")
    role = await client.post("/api/roles/", headers=admin_headers, json={"code": "indirect-low", "name": "Indirect low", "permission_ids": [permission["id"]]})
    id_ = role.json()["id"]
    group = await client.post("/api/groups/", headers=admin_headers, json={"code": "indirect-elevated", "name": "Indirect elevated", "role_ids": [id_], "user_ids": [manager_objects["elevated"]]})
    assert group.status_code == 201, group.text
    if method == "patch":
        response = await client.patch(f"/api/roles/{id_}/", headers=manager_objects["headers"], json={"permission_ids": []})
    else:
        response = await client.delete(f"/api/roles/{id_}/", headers=manager_objects["headers"])
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_only_superusers_can_edit_builtin_role(rbac_client, manager_objects, memory_session):
    client, headers, _ = rbac_client
    permission = await memory_session.scalar(select(PermissionDefinition).where(PermissionDefinition.code == "rbac.user.view"))
    role = Role(code="builtin-low", name="Builtin low", is_builtin=True, permissions=[permission], users=[])
    memory_session.add(role)
    await memory_session.commit()
    result = await client.patch(f"/api/roles/{role.id}/", headers=manager_objects["headers"], json={"name": "Hijacked"})
    assert result.status_code == 403, result.text
    result = await client.patch(f"/api/roles/{role.id}/", headers=headers, json={"description": "Allowed admin edit"})
    assert result.status_code == 200, result.text
