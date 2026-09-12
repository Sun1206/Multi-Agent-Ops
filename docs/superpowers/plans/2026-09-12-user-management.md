# User Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Preserve the user's established inline, in-place execution preference. Steps use checkbox syntax for tracking.

**Goal:** Complete Users.vue's user, role, group and permission contracts with secure FastAPI services and atomic audit writes.

**Architecture:** Reuse current models and session/auth dependencies. Separate schemas, read selectors, mutation services and authorization policy; HTTP routers own commit. Preserve current API compatibility and existing admin credentials.

**Tech Stack:** FastAPI, SQLAlchemy async, MySQL 8, Pydantic 2, HTTPX, pytest, memory SQLite.

---

## Execution constraints

### Execution record (2026-09-12)

The original step checkboxes below preserve the pre-execution checklist; this record is the authoritative completion summary.

- [x] Task 1: read contracts, shared serializer, authorization, search and pagination implemented and tested through real ASGI sessions.
- [x] Task 2: validated mutations, relation replacement, password hashing, token revocation and atomic safe auditing implemented; failures reproduced before fixes.
- [x] Task 3: identity, permission-boundary, inherited-role, builtin, self-delete and final-admin protections implemented and regression-tested. Login now locks the account row before checking credentials to serialize against password reset.
- [x] Full default suite: 94 passed, 3 skipped. compileall and pip check pass. OpenAPI registers 24 HTTP operations.
- [x] Development MySQL HTTP smoke: unique temporary user/role/group CRUD, relations, role-bound partial update, password reset and token revocation verified. Created objects and smoke tokens cleaned; existing admin password unchanged; normal audit records retained.
- [x] Browser read smoke: all four Users.vue tabs load, admin appears as superuser. Test browser logged out and closed. Frontend production build succeeds with --configLoader runner.
- [x] Bounded read-only security review completed; independently reproduced and fixed indirect-role boundary, builtin edit, audit metadata and unloaded-role partial-update findings through regression tests.
- [x] README updated with endpoints, security rules and pending verification scope. No frontend source changes or new migrations.
- [ ] Independent MySQL concurrency/transaction suite: tests implemented but blocked by MySQL 1044 access denial for ai_ops_test (three tests skipped). No grants or databases changed.
- [ ] Browser create/edit/reset/delete dialogs: not exhaustively exercised; underlying HTTP contracts verified separately.
- [ ] Git commit/integration: not performed; repository has no initial commit and previously denied index writes. No ACL changes or blanket staging.

Code for this phase is handed off with these explicit acceptance gaps, not marked as fully production-accepted. Temporary backend process stopped after verification; user-owned frontend left running.

Approved design: `C:\Users\sunyupeng\PycharmProjects\AI-Ops\docs\superpowers\specs\2026-09-12-user-management-design.md`. No changes to existing migrations, frontend contract, development data or admin password. Current baseline: 54 tests pass. Git has no initial commit; previous index writes were ACL-blocked. Do not change ACLs, force-reset files or create a second worktree against user preference. Commit only exact new/modified task files if Git permits; never stage `.env`.

## File responsibilities

- `backend/app/schemas/rbac.py`: validated create/patch/reset input, permission/role/group/pagination output.
- `backend/app/selectors/users.py`: user detail and count/offset/search selection.
- `backend/app/selectors/rbac.py`: loaded role/group reads, dictionary selection, ID validation.
- `backend/app/services/user_serialization.py`: shared user response and batched permission map, extracted from auth router.
- `backend/app/services/rbac_policy.py`: status/identity/permission boundary checks and ordered admin row lock.
- `backend/app/services/users.py`: account mutations and token revocation.
- `backend/app/services/role_management.py`, `group_management.py`: relation mutations with builtin protection.
- `backend/app/api/routers/users.py`, `roles.py`, `groups.py`, `permissions.py`: thin endpoints.
- `backend/app/api/audit.py`: safe common audit context and single commit.
- `backend/app/main.py`, `api/routers/auth.py`: register routes and reuse serializer.
- `backend/tests_fastapi/integration/test_rbac_reads.py`, `test_rbac_writes.py`, `test_rbac_safety.py`: real in-memory HTTP flow, policy and rollback.
- `backend/tests_fastapi/integration/test_mysql_rbac.py`: explicitly gated standalone MySQL test database verification.

## Task 1: Read contracts and shared output

- [ ] Add a fixture that seeds only the in-memory database with sync_rbac and ensure_admin, creates a session factory from the memory engine, and uses ASGITransport with normal auth/session dependencies.
- [ ] Write tests for GET /api/users/, /roles/, /groups/, /permissions/, anonymous 401, ordinary user 403, stable search/pagination and user schema without password fields.

```python
async def test_lists(rbac_client):
    client, headers = rbac_client
    users = await client.get('/api/users/', headers=headers)
    assert users.status_code == 200
    assert set(users.json()) == {'count', 'next', 'previous', 'results'}
    for path in ('roles', 'groups', 'permissions'):
        result = await client.get(f'/api/{path}/', headers=headers)
        assert result.status_code == 200 and isinstance(result.json(), list)
```

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_rbac_reads.py -q`; expect 404 failures before registration.
- [ ] Implement validated output schemas, selectinload relation reads and bulk permission queries. Build permission map from direct role joins plus group role joins for all selected user IDs; query complete dictionary once for superusers. Extract serialize_user(session,user) to user_serialization and use same UserResponse for auth/read results.

```python
statement = select(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size)
if search:
    statement = statement.where(or_(User.username.icontains(search), User.email.icontains(search)))
```

- [ ] Register read routers with view permissions; output users' next/previous links using request URL and replaced page/page_size parameters. Page >1 outside result range raises HTTPException(404). Clamp requested page_size to 200 after validating positive integer.
- [ ] Run read tests and full pytest; require green without changing baseline auth assertions.

## Task 2: Validated mutations and atomic auditing

- [ ] Write HTTP tests for user create/patch/reset/delete, role create/patch/delete, group create/patch/delete, ID relation replacement, [] clearing and duplicate ID deduplication. Verify create 201, patch 200, delete 204, reset {success:true}, invalid ID 400 and uniqueness 409. Check actual database relations and hashes.

```python
created = await client.post('/api/users/', headers=headers, json={'username':'new-user', 'password':'safe-pass-123'})
assert created.status_code == 201
changed = await client.patch(f"/api/users/{created.json()['id']}/", headers=headers, json={'role_ids':[]})
assert changed.status_code == 200 and changed.json()['roles'] == []
```

- [ ] Run write tests; expect method/path missing failures.
- [ ] Implement input schemas (extra=forbid, ID>0, trimmed nonblank identity fields, password length 8–128 without trimming). Distinguish missing PATCH fields from []/false using model_dump(exclude_unset=True); reject null for non-nullable explicitly submitted fields. Validate each referenced ID with select-in-ID queries before mutations, then replace many-to-many relationships.
- [ ] Implement require_permissions for manage operations. Services flush only; router adds record_event and commits together. Audit metadata records field names and safe ID lists, never entire payload or hash. Delete via Core DELETE to rely on database cascades rather than unloaded ORM backrefs. User reset/disable/password edit issues DELETE auth_tokens WHERE user_id=:id within same transaction.

```python
await session.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
await record_event(session, actor=actor, action='reset_user_password', metadata={'changed_fields':['password']}, **request_context)
await session.commit()
```

- [ ] Run writes and all regression tests; enable SQLite foreign_keys pragma for new fixture to verify relation cascade. Verify all timestamps retain UTC and responses never expose secrets.

## Task 3: Authorization and administrator protections

- [ ] Add failing tests for non-superuser identity elevation, elevated target user/role/group edits, indirect role/group/member privilege escalation, builtin deletion/code mutation, last active admin disable/demotion/delete, self-delete, revoked-token reuse and unchanged status flags from full frontend forms.

```python
response = await client.patch('/api/users/1/', headers=headers, json={'is_active':False})
assert response.status_code == 400
assert (await client.get('/api/auth/me/', headers=headers)).status_code == 200
```

- [ ] Run each safety test and observe failure before implementing the corresponding policy.
- [ ] In rbac_policy, require target's existing permissions and desired relation permissions to be subsets of actor's own effective permissions unless actor.is_superuser. Only superusers actually change is_staff/is_superuser; non-superusers may submit unchanged false flags and cannot touch superuser targets. Group membership writes also check each affected member's current permission boundary.
- [ ] Serialize user mutations against ordered `select(User).where(User.is_superuser.is_(True)).order_by(User.id).with_for_update().execution_options(populate_existing=True)`; acquire before loading target row. Inspect current locked active flags and prohibit reducing final enabled-superuser count to zero. Apply this lock order consistently to create/patch/reset/delete to avoid user row/admin lock inversions.
- [ ] Protect builtin objects from delete/code mutation and is_builtin injection. Preserve existing registry-authoritative sync behavior for builtin role mutable fields.
- [ ] Force audit service failure in an isolated in-memory HTTP test and verify a new session sees neither mutation nor event. Verify validation/409 errors also rollback and do not poison subsequent requests.
- [ ] Run safety and full tests, documenting explicit MySQL concurrency verification separately from SQLite.

## Task 4: Real-environment verification, review and handoff

- [ ] Create explicitly gated MySQL tests using environment flag AIOPS_RUN_MYSQL_TESTS=1 and Settings(database_mode='test'). Verify active DB ends `_test`, differs from AIOps, and account can access it before creating tables. Never drop existing tables or create DB with inferred permission; report unavailable test DB rather than modifying development data.
- [ ] Use unique temporary fixture objects in test DB and delete only created IDs in dependency order. Two simultaneous sessions attempt to disable two temporary superusers in isolated test setup; confirm final-active-admin protection without touching development admin.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`, `python -m compileall -q app scripts alembic`, `python -m pip check`; inspect complete results.
- [ ] Check local development schema/current admin read-only. Browser business smoke, if authorized/available, creates and cleans only uniquely prefixed test users/roles/groups. Never reset admin password as a smoke step.
- [ ] Run frontend build with `node node_modules/vite/bin/vite.js build --configLoader runner` to work around known ordinary-loader ACL restriction. Verify FastAPI lifespan, OpenAPI and docs after registration.
- [ ] Use requesting-code-review for a bounded read-only security/contract review; independently reproduce findings and fix through failing tests.
- [ ] Update backend README with implemented endpoints and password/security rules. Mark actual completed plan steps, record unavailable MySQL/browser acceptance and Git commit restrictions. No blanket “all frontend interfaces implemented” claim.
- [ ] If every acceptance item passes, use finishing-a-development-branch; otherwise hand off honest phase completion without marking pending gates complete.
