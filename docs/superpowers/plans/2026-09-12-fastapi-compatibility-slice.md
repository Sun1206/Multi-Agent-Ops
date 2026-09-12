# FastAPI Compatibility Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Django/DRF runtime with a tested FastAPI/MySQL backend that preserves the complete current schema and restores the first frontend compatibility slice for admin authentication, RBAC, module settings, and operation auditing without changing the Vue contract.

**Architecture:** Build FastAPI beside the current Django code, using async SQLAlchemy services and selectors behind thin routers. Port all four existing model groups before cutover, but restore HTTP behavior in vertical slices; this plan implements the auth/RBAC/module/audit slice and leaves later page endpoints to separate plans. Keep Django executable until schema parity, the FastAPI acceptance suite, Alembic cycle, frontend build, and browser smoke test all pass; only then remove the Django runtime.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2 async, asyncmy, Alembic, MySQL 8, pwdlib Argon2id, pytest-asyncio, HTTPX, Vue/Vite

---

## File map

### Execution status (2026-09-12)

Latest update: local `localhost:3307/AIOps` connection, initial migration, 14-table prefix normalization, RBAC/module initialization, and explicit `admin` initialization have been completed and verified. The user explicitly authorized legacy cleanup: Django applications, settings, entrypoint, tests, model-generation script, SQLite artifact and legacy caches were moved outside the project into a recoverable backup. FastAPI startup/OpenAPI and 54 offline tests pass without Django. No downgrade or browser business acceptance was run, and later page endpoints remain pending. Earlier progress notes below are historical and superseded by this update.

- Implemented the auth/RBAC/module/audit compatibility slice and all persisted model groups. Default dependencies are now `backend/requirements.txt`; Django source remains inactive reference code, not a runtime dependency.
- Added UTC-aware MySQL timestamp handling, certificate/API-key audit redaction, and Alembic percent-encoded credential handling, with regression tests. Offline suite: 50 passed on local Python 3.13.5.
- Run scripts as modules (`python -m scripts.generate_domain_models`, `python -m scripts.generate_initial_migration`, `python -m scripts.bootstrap_data`). Initial revision is `0001_fastapi_initial.py`.
- User deferred real MySQL connection. MySQL migration-cycle acceptance, browser business acceptance, and Task 9 legacy deletion remain pending. Later page endpoints are outside this slice and remain unimplemented.
- Frontend build passed using Vite `--configLoader runner`; ordinary loader and Git commit encounter local filesystem ACL restrictions. No ACLs were changed.

Create focused runtime files under `backend/app`: `core/config.py` owns validated settings and database guards; `core/database.py` owns engine/session lifecycle; `core/security.py` owns password/token primitives; `models/` owns the complete persisted schema; `schemas/` owns HTTP types; `services/` owns writes and commits; `selectors/` owns reads; `api/dependencies.py` owns authentication/authorization dependencies; `api/routers/` owns the seven compatibility routes; `main.py` assembles the app. `backend/tests_fastapi` remains separate from the Django tests during the transition. `backend/requirements-fastapi.txt` is temporary until cutover, so Django remains runnable during acceptance.

## Task 1: Add FastAPI dependencies and safe settings

**Files:**
- Create: `backend/requirements-fastapi.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/tests_fastapi/unit/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

```python
# backend/tests_fastapi/unit/test_config.py
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides: object) -> Settings:
    values = {
        "mysql_host": "127.0.0.1",
        "mysql_port": 3306,
        "mysql_database": "ai_ops",
        "mysql_test_database": "ai_ops_test",
        "mysql_user": "ai_ops",
        "mysql_password": "p@ss:/word",
        "database_mode": "test",
    }
    values.update(overrides)
    return Settings(**values)


def test_test_database_must_be_isolated() -> None:
    with pytest.raises(ValidationError):
        make_settings(mysql_test_database="ai_ops")


def test_test_database_must_end_with_test() -> None:
    with pytest.raises(ValidationError):
        make_settings(mysql_test_database="ai_ops_ci")


def test_database_url_percent_encodes_password() -> None:
    assert "p%40ss%3A%2Fword" in make_settings().database_url.render_as_string(hide_password=False)
```

- [ ] **Step 2: Run the test and confirm the expected import failure**

Run: `cd backend; python -m pytest tests_fastapi/unit/test_config.py -q`

Expected: FAIL because `app.core.config` does not exist.

- [ ] **Step 3: Add the dependency manifest and settings implementation**

`backend/requirements-fastapi.txt` must contain exact compatible ranges:

```text
fastapi>=0.116,<1.0
uvicorn[standard]>=0.35,<1.0
sqlalchemy[asyncio]>=2.0.43,<3.0
asyncmy>=0.2.10,<1.0
alembic>=1.16,<2.0
pydantic>=2.11,<3.0
pydantic-settings>=2.10,<3.0
pwdlib[argon2]>=0.2.1,<1.0
python-multipart>=0.0.20,<1.0
httpx>=0.28,<1.0
pytest>=8.4,<9.0
pytest-asyncio>=1.1,<2.0
```

`backend/.env.example` contains names only and safe local defaults—leave passwords empty:

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=ai_ops
MYSQL_TEST_DATABASE=ai_ops_test
MYSQL_USER=ai_ops
MYSQL_PASSWORD=
AIOPS_DATABASE_MODE=development
AIOPS_ADMIN_INITIAL_PASSWORD=
```

Implement `Settings` with `SettingsConfigDict(env_file=".env", extra="ignore")`, the seven fields above, and these exact public properties:

```python
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """读取运行配置，并阻止测试连接误指向开发数据库。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "ai_ops"
    mysql_test_database: str = "ai_ops_test"
    mysql_user: str
    mysql_password: SecretStr
    database_mode: Literal["development", "test"] = "development"
    aiops_admin_initial_password: SecretStr | None = None

    @model_validator(mode="after")
    def validate_test_database(self) -> "Settings":
        """验证自动化测试只能操作名称以 `_test` 结尾的独立数据库。"""
        if self.database_mode == "test":
            if not self.mysql_test_database.endswith("_test"):
                raise ValueError("MYSQL_TEST_DATABASE 必须以 _test 结尾")
            if self.mysql_test_database == self.mysql_database:
                raise ValueError("测试数据库不能与开发数据库相同")
        return self

    @property
    def active_database(self) -> str:
        """按运行模式返回当前允许访问的数据库名称。"""
        return self.mysql_test_database if self.database_mode == "test" else self.mysql_database

    @property
    def database_url(self) -> URL:
        """构造能正确编码特殊字符的 asyncmy 连接地址。"""
        return URL.create(
            "mysql+asyncmy", username=self.mysql_user,
            password=self.mysql_password.get_secret_value(), host=self.mysql_host,
            port=self.mysql_port, database=self.active_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    """返回进程级缓存配置，测试可通过 cache_clear 重新加载。"""
    return Settings()
```

- [ ] **Step 4: Install and verify**

Run: `cd backend; python -m pip install -r requirements-fastapi.txt; python -m pytest tests_fastapi/unit/test_config.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Commit**

Run: `git add backend/requirements-fastapi.txt backend/.env.example backend/app backend/tests_fastapi/unit/test_config.py; git commit -m "build: add FastAPI configuration foundation"`

## Task 2: Add guarded async MySQL lifecycle and test fixtures

**Files:**
- Create: `backend/app/core/database.py`
- Create: `backend/scripts/create_databases.py`
- Create: `backend/tests_fastapi/conftest.py`
- Create: `backend/tests_fastapi/integration/test_database.py`

- [ ] **Step 1: Write a failing connection test**

```python
# backend/tests_fastapi/integration/test_database.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_session_uses_guarded_test_database(test_session: AsyncSession) -> None:
    row = (await test_session.execute(text("SELECT DATABASE()"))).scalar_one()
    assert row == "ai_ops_test"
```

- [ ] **Step 2: Implement engine/session lifecycle**

`backend/app/core/database.py` exposes `Base(DeclarativeBase)`, `create_engine(settings)`, `create_session_factory(engine)`, and `get_session()`. `get_session()` must yield one `AsyncSession`, roll back on exceptions, and always close it. Each function receives a concise Chinese docstring. Engine options are `pool_pre_ping=True`, `pool_recycle=1800`, and `pool_size=10`.

`backend/scripts/create_databases.py` must connect without selecting a database, quote only validated identifiers matching `^[A-Za-z0-9_]+$`, and execute:

```sql
CREATE DATABASE IF NOT EXISTS `ai_ops` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `ai_ops_test` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

The script must call `Settings(database_mode="test")` before creating either database so the `_test` guard runs first. It must never drop a database.

In `backend/tests_fastapi/conftest.py`, set `AIOPS_DATABASE_MODE=test` before importing the app, expose session-scoped `settings` and `test_engine`, recreate mapped tables once per session, and provide a function-scoped `test_session` whose transaction is rolled back after every test.

- [ ] **Step 3: Prepare local MySQL explicitly**

Run: `Get-Service MySQL,MySQL80 -ErrorAction SilentlyContinue | Select-Object Name,Status,StartType`

Expected now: both detected services are stopped. Select the service whose executable/config points to the intended local MySQL 8 data directory; do not start both. Start that exact service from an elevated terminal, create a least-privilege local user outside source control, copy `.env.example` to `.env`, then run `cd backend; python scripts/create_databases.py`.

Expected: both database names are printed as available; no password is printed.

- [ ] **Step 4: Run and commit**

Run: `cd backend; python -m pytest tests_fastapi/integration/test_database.py -q`

Expected: `1 passed` and the selected database is `ai_ops_test`.

Run: `git add backend/app/core/database.py backend/scripts/create_databases.py backend/tests_fastapi; git commit -m "feat: add guarded async MySQL lifecycle"`

## Task 3: Map the complete current schema and add Alembic

**Files:**
- Create: `backend/app/models/{auth,rbac,module,eventwall,ops,aiops}.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_fastapi_compatibility.py`
- Create: `backend/tests_fastapi/contract/test_schema.py`
- Create: `backend/tests_fastapi/contract/test_full_model_parity.py`
- Create: `backend/tests_fastapi/integration/test_alembic_cycle.py`

- [ ] **Step 1: Write failing schema-contract tests**

```python
# backend/tests_fastapi/contract/test_schema.py
from sqlalchemy import inspect

from app.models import EventRecord, User


def test_auth_and_event_columns_keep_required_constraints() -> None:
    user = inspect(User)
    assert user.columns.username.unique is True
    assert user.columns.password_hash.nullable is False
    assert "token_digest" in {column.name for column in User.__table__.metadata.tables["auth_tokens"].columns}
    assert EventRecord.__table__.c.metadata.type.python_type is dict


def test_event_python_attribute_avoids_reserved_metadata_name() -> None:
    assert hasattr(EventRecord, "event_metadata")
    assert EventRecord.event_metadata.property.columns[0].name == "metadata"
```

- [ ] **Step 2: Add authentication and RBAC SQLAlchemy mappings**

Map these tables with integer primary keys, UTC timestamps, named foreign keys, InnoDB, and utf8mb4:

- `users`: username, display_name, password_hash, is_active, is_superuser, created_at, updated_at.
- `auth_tokens`: user_id, unique indexed 64-character `token_digest`, created_at.
- `permissions`, `roles`, `groups`, plus `role_permissions`, `user_roles`, `group_roles`, and `group_users` association tables with composite unique keys.
- `module_settings`: unique code, name, description, enabled, required, sort_order.
- `event_records`: actor_id nullable, event_type, method, path, source_address, resource_type, resource_id, correlation_id, and JSON database column `metadata` mapped to Python attribute `event_metadata` because `metadata` is reserved by SQLAlchemy.

Use concrete SQLAlchemy annotations such as `Mapped[str]`, `Mapped[int]`, `Mapped[datetime]`, and `Mapped[dict[str, object]]` throughout, `lazy="raise"` on relationships, and cascading deletes only for association/token rows.

- [ ] **Step 3: Port all eventwall, ops, and AIOps persistence models**

Treat `backend/eventwall/models.py`, `backend/ops/models.py`, `backend/aiops/models.py`, and their `0001_initial.py` files as the parity source. Map every existing class, field, max length, decimal precision, JSON default, null/default rule, choice value, foreign key action, many-to-many table, index, uniqueness rule, and database table name into `app/models/eventwall.py`, `app/models/ops.py`, and `app/models/aiops.py`.

The parity test must define the exact expected class-name sets and fail if a mapping is absent:

```python
EXPECTED_EVENTWALL = {"EventRecord", "EventSource", "EventEnvironment"}
EXPECTED_AIOPS = {
    "AIOpsModelProvider", "AIOpsAgentConfig", "AIOpsMCPServer", "AIOpsSkill",
    "AIOpsKnowledgeEnvironment", "AIOpsChatSession", "AIOpsChatMessage",
    "AIOpsPendingAction", "AIOpsToolInvocation", "AIOpsModelInvocation",
    "AIOpsExternalTask", "AIOpsRunbook", "AIOpsRunbookVersion", "AIOpsReviewKnowledge",
}
EXPECTED_OPS = {
    "Host", "TaskResourceGroup", "TaskResource", "HostTask", "HostTaskTemplate",
    "HostTaskSchedule", "HostTaskScheduleExecution", "HostTaskExecution", "Deployment",
    "DeploymentApprovalFlow", "DeploymentApprovalNode", "DeploymentApprovalStep", "Alert",
    "AlertClaim", "AlertIntegration", "AlertRecipient", "AlertRecipientGroup",
    "AlertNotificationChannel", "AlertAggregationRule", "AlertInhibitionRule", "AlertMuteRule",
    "AlertEscalationPolicy", "AlertNotificationRule", "AlertNotificationLog", "AlertAction",
    "AlertInteractionToken", "LogEntry", "LogDataSource", "TracingDataSource",
    "MetricDataSource", "ObservabilityDataSourceLink", "GrafanaSetting", "DockerHost",
    "NginxEnvironment", "NginxCertificate", "NginxDomain", "NginxRoute", "TransactionTicket",
}


def test_every_current_domain_model_is_exported() -> None:
    from app import models
    exported = set(models.__all__)
    assert EXPECTED_EVENTWALL | EXPECTED_AIOPS | EXPECTED_OPS <= exported
```

Add table-driven assertions for every Django `Meta.indexes`/`unique_together`, every `DecimalField(max_digits, decimal_places)`, every JSON column, and every foreign key `on_delete`. Where Django generated an implicit association table, give the SQLAlchemy table the same explicit semantic name and test both foreign keys and the composite unique constraint. Export every model/table from `app.models` so Alembic sees one metadata graph.

- [ ] **Step 4: Add and exercise Alembic**

`alembic/env.py` loads `get_settings().database_url`, uses `async_engine_from_config`, imports `Base.metadata`, enables `compare_type=True`, and runs migrations inside `connection.run_sync`. Generate and then manually review `0001_fastapi_compatibility.py`; it must create the full exported metadata graph, contain schema operations only, and contain no seeded users, tokens, roles, or modules.

The integration test must run these subprocesses with `AIOPS_DATABASE_MODE=test` and assert all return code zero:

```text
python -m alembic downgrade base
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
python -m alembic check
```

- [ ] **Step 5: Verify and commit**

Run: `cd backend; python -m pytest tests_fastapi/contract/test_schema.py tests_fastapi/contract/test_full_model_parity.py tests_fastapi/integration/test_alembic_cycle.py -q`

Expected: every current domain model is exported, all schema-parity assertions pass, and Alembic reports no new upgrade operations.

Run: `git add backend/app/models backend/alembic backend/alembic.ini backend/tests_fastapi; git commit -m "feat: port complete backend schema to SQLAlchemy"`

## Task 4: Implement Argon2id auth, opaque tokens, and admin bootstrap

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/services/accounts.py`
- Create: `backend/app/selectors/accounts.py`
- Create: `backend/scripts/bootstrap_admin.py`
- Create: `backend/tests_fastapi/unit/test_security.py`
- Create: `backend/tests_fastapi/integration/test_admin_bootstrap.py`

- [ ] **Step 1: Write failing security tests**

```python
from app.core.security import digest_token, generate_token, hash_password, verify_password


def test_password_hash_is_argon2id() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", encoded)


def test_only_token_digest_is_storage_safe() -> None:
    raw = generate_token()
    digest = digest_token(raw)
    assert raw != digest
    assert len(digest) == 64
```

The integration test calls `ensure_admin(session, "first-secret")` twice, then once with `"second-secret"`; assert exactly one `admin`, active/superuser flags true, and the latest supplied password verifies. Also assert `ensure_admin(session, None)` creates nothing in an empty database.

- [ ] **Step 2: Implement security and account services**

Use `PasswordHash.recommended()` from pwdlib and `secrets.token_urlsafe(32)`. Implement `digest_token(raw)` as `hashlib.sha256(raw.encode("utf-8")).hexdigest()`. `issue_token` stores only the digest and flushes; `revoke_token` deletes the matching digest; `authenticate_credentials` returns no distinction between unknown user and bad password. All public functions have Chinese docstrings describing inputs, output, database side effects, and the rule that raw secrets must not be logged.

`bootstrap_admin.py` reads only `AIOPS_ADMIN_INITIAL_PASSWORD`; if absent, print a safe skipped message. It must not accept a password as a command-line argument because process lists expose arguments.

- [ ] **Step 3: Verify and commit**

Run: `cd backend; python -m pytest tests_fastapi/unit/test_security.py tests_fastapi/integration/test_admin_bootstrap.py -q`

Expected: all tests pass; a database query confirms token rows contain a 64-character digest and not the raw token.

Run: `git add backend/app/core/security.py backend/app/services/accounts.py backend/app/selectors/accounts.py backend/scripts/bootstrap_admin.py backend/tests_fastapi; git commit -m "feat: add secure admin and token authentication"`

## Task 5: Port deterministic RBAC and module settings

**Files:**
- Create: `backend/app/registry.py`
- Create: `backend/app/services/rbac.py`
- Create: `backend/app/services/modules.py`
- Create: `backend/app/selectors/permissions.py`
- Create: `backend/app/selectors/modules.py`
- Create: `backend/tests_fastapi/contract/test_rbac.py`
- Create: `backend/tests_fastapi/contract/test_modules.py`

- [ ] **Step 1: Write failing behavior tests**

RBAC tests must assert: direct-role permissions are returned; group-role permissions are returned; duplicates are removed and codes sorted; inactive users authenticate as 401; superuser dependency bypasses missing ordinary permissions; synchronization run twice leaves the same permission/role counts.

Module tests must use the exact eight entries currently returned by `backend/rbac/services/modules.py`, assert sort order, assert required modules cannot be disabled, and verify both accepted input forms normalize to the same list:

```python
[
    {"code": "containers", "enabled": False},
]

{"modules": [{"code": "containers", "enabled": False}]}
```

- [ ] **Step 2: Copy registries as data, then implement services/selectors**

Copy `PERMISSION_DEFINITIONS` and `BUILTIN_ROLES` exactly from `backend/rbac/registry.py` into `backend/app/registry.py`; copy the eight module definitions exactly from `backend/rbac/services/modules.py`. Do not import Django files from the FastAPI runtime.

Expose these stable interfaces: `sync_rbac(session: AsyncSession) -> None`, `sync_modules(session: AsyncSession) -> None`, `effective_permission_codes(session: AsyncSession, user_id: int) -> list[str]`, `list_module_settings(session: AsyncSession) -> list[ModuleSetting]`, and `update_module_settings(session: AsyncSession, updates: list[ModuleToggle], actor: User) -> list[ModuleSetting]`.

Each sync uses MySQL upsert semantics, removes obsolete built-in role bindings but does not delete custom roles, flushes without committing, and is safe when rerun. `update_module_settings` validates all codes and required flags before changing any row, then commits once.

- [ ] **Step 3: Verify and commit**

Run: `cd backend; python -m pytest tests_fastapi/contract/test_rbac.py tests_fastapi/contract/test_modules.py -q`

Expected: all direct/group/superuser, idempotency, catalog, required-module, and payload-normalization tests pass.

Run: `git add backend/app/registry.py backend/app/services backend/app/selectors backend/tests_fastapi; git commit -m "feat: port RBAC and module settings"`

## Task 6: Add recursively sanitized event auditing

**Files:**
- Create: `backend/app/services/events.py`
- Create: `backend/tests_fastapi/unit/test_redaction.py`
- Create: `backend/tests_fastapi/integration/test_module_audit.py`

- [ ] **Step 1: Write failing redaction and atomicity tests**

```python
from app.services.events import sanitize_metadata


def test_recursive_sensitive_values_are_redacted() -> None:
    value = {
        "authorization": "Token raw",
        "nested": [{"password": "secret"}, {"safe": "visible"}],
        "ssh_private_key": "private",
        "kubeconfig": {"token": "nested-raw"},
    }
    assert sanitize_metadata(value) == {
        "authorization": "***",
        "nested": [{"password": "***"}, {"safe": "visible"}],
        "ssh_private_key": "***",
        "kubeconfig": "***",
    }
```

The integration test updates a module and asserts one event is committed with actor, PUT/PATCH method, path, safe client IP, resource code, correlation ID, and redacted metadata. Force event insertion to fail and assert the module update also rolls back so audit and business mutation stay atomic.

- [ ] **Step 2: Implement the sanitizer and audit writer**

Sensitive-key matching is case-insensitive after removing `-` and `_`, and covers authorization, cookie, password, secret, token, accesskey, privatekey, certificate, sshcredential, and kubeconfig. Recursively traverse dict/list/tuple; preserve safe scalar values; replace the entire value beneath a sensitive key with `"***"`. `record_event` only adds the row and flushes—its caller owns commit/rollback. Add Chinese docstrings explaining this transaction boundary.

- [ ] **Step 3: Verify and commit**

Run: `cd backend; python -m pytest tests_fastapi/unit/test_redaction.py tests_fastapi/integration/test_module_audit.py -q`

Expected: all recursive-redaction and transaction-rollback assertions pass.

Run: `git add backend/app/services/events.py backend/tests_fastapi; git commit -m "feat: add sanitized atomic event auditing"`

## Task 7: Restore the seven frontend HTTP contracts

**Files:**
- Create: `backend/app/schemas/{auth,module,common}.py`
- Create: `backend/app/api/dependencies.py`
- Create: `backend/app/api/routers/{auth,module_settings}.py`
- Create: `backend/app/core/exceptions.py`
- Create: `backend/app/main.py`
- Create: `backend/tests_fastapi/contract/test_auth_api.py`
- Create: `backend/tests_fastapi/contract/test_module_api.py`

- [ ] **Step 1: Write failing HTTP contract tests**

Use `httpx.AsyncClient(transport=ASGITransport(app=create_app()))`. Assert:

- `POST /api/auth/login/` accepts the existing JSON field names and returns `{token, user}`.
- bad username/password returns 400 with only `{"detail": "用户名或密码错误"}`.
- `GET /api/auth/me/` with `Authorization: Token <raw>` returns username, display_name, role/group summaries, sorted effective_permissions, and `is_demo_account: false`.
- missing, wrong-scheme, and invalid tokens return 401.
- `POST /api/auth/logout/` returns `{"success": true}` and invalidates that token.
- `POST /api/auth/sync/` is admin-only and idempotent.
- GET/PUT/PATCH module routes retain trailing slashes, accept both payload shapes, deny ordinary users without `rbac.module.manage`, and allow admin writes.
- every error response contains only a string-valued `detail` field and never exposes a traceback or secret.

- [ ] **Step 2: Implement dependencies and schemas**

`get_current_user` parses exactly the `Token` scheme, hashes the credential, selects an active user, and stores no raw token in request state. `require_permissions(*codes)` returns a dependency that allows superusers or requires every code. Response schemas use `ConfigDict(from_attributes=True)` and include the compatibility field `is_demo_account: Literal[False] = False`.

- [ ] **Step 3: Implement thin routers and app factory**

Routers call selectors/services only. Each endpoint has a Chinese docstring naming method/path, authentication, permission, and purpose. `create_app()` mounts both routers, CORS for the configured local Vue origins, a correlation-ID middleware, and exception handlers for 400/401/403/404/409 plus a sanitized 500. The 500 handler logs the correlation ID but never request authorization/cookie headers.

- [ ] **Step 4: Verify and commit**

Run: `cd backend; python -m pytest tests_fastapi/contract/test_auth_api.py tests_fastapi/contract/test_module_api.py -q`

Expected: all seven route contracts pass with unchanged paths and shapes.

Run: `git add backend/app backend/tests_fastapi/contract; git commit -m "feat: restore FastAPI auth and module contracts"`

## Task 8: Bootstrap, migrate, and perform acceptance before cutover

**Files:**
- Create: `backend/scripts/bootstrap_data.py`
- Create: `backend/README.md`
- Modify: `frontend/` only if a smoke test proves its API base URL is wrong; otherwise no frontend source change.

- [ ] **Step 1: Add deterministic bootstrap orchestration**

`bootstrap_data.py` opens one session, runs `sync_rbac`, `sync_modules`, and `ensure_admin`, then commits once. On any exception it rolls back and exits non-zero. It must print counts and admin status, never passwords/tokens. Add Chinese docstrings to the entry point and helper.

- [ ] **Step 2: Document exact local commands**

`backend/README.md` documents `.env` setup, database creation, `python -m alembic upgrade head`, `python scripts/bootstrap_data.py`, `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`, test command, and the requirement that `AIOPS_ADMIN_INITIAL_PASSWORD` is removed from `.env` after successful bootstrap.

- [ ] **Step 3: Run backend, migration, frontend, and secret checks**

Run:

```powershell
cd backend
$env:AIOPS_DATABASE_MODE='test'
python -m alembic downgrade base
python -m alembic upgrade head
python -m pytest tests_fastapi -q
Remove-Item Env:AIOPS_DATABASE_MODE
python -m alembic upgrade head
python scripts/bootstrap_data.py
cd ..\frontend
npm run build
cd ..
rg -n "demo.*special|username\s*==\s*['\"]demo|from django|import django|rest_framework" backend\app backend\tests_fastapi
rg -n "Authorization: Token [A-Za-z0-9_-]{16,}|MYSQL_PASSWORD=.+|AIOPS_ADMIN_INITIAL_PASSWORD=.+" backend --glob "!.env"
```

Expected: Alembic cycle succeeds, all FastAPI tests pass, Vite build exits zero, and both source scans return no matches.

- [ ] **Step 4: Browser smoke test**

Start FastAPI and the Vue dev server. In the browser, sign in as `admin`; confirm `/api/auth/login/`, `/api/auth/me/`, and `/api/module-settings/` return 2xx; toggle a non-required module and confirm one audit row; log out and confirm `/api/auth/me/` returns 401. Browser console must contain no error for these restored endpoints.

- [ ] **Step 5: Commit acceptance assets**

Run: `git add backend/scripts/bootstrap_data.py backend/README.md; git commit -m "docs: add FastAPI local bootstrap and acceptance workflow"`

## Task 9: Remove Django only after acceptance succeeds

**Files:**
- Delete: `backend/manage.py`
- Delete: `backend/config/`
- Delete: `backend/rbac/`
- Delete: `backend/eventwall/`
- Delete: `backend/ops/`
- Delete: `backend/aiops/`
- Delete: `backend/common/`
- Delete: `backend/tests/`
- Delete: `backend/db.sqlite3` if present
- Replace: `backend/requirements.txt`
- Delete: `backend/requirements-fastapi.txt`
- Create: `backend/tests_fastapi/contract/test_no_django_runtime.py`

- [ ] **Step 1: Write the cutover guard before deleting anything**

```python
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]


def test_django_runtime_files_are_absent() -> None:
    assert not (BACKEND / "manage.py").exists()
    for package in ("config", "rbac", "eventwall", "ops", "aiops", "common"):
        assert not (BACKEND / package).exists()


def test_runtime_dependencies_are_fastapi_only() -> None:
    requirements = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "fastapi" in requirements
    assert "django" not in requirements
    assert "djangorestframework" not in requirements
```

- [ ] **Step 2: Verify exact deletion targets, then remove them**

Resolve every target with `Resolve-Path -LiteralPath` and confirm each is below `C:\Users\sunyupeng\PycharmProjects\AI-Ops\backend`. Remove only the exact paths listed above. This deletion is authorized only because Task 8 acceptance passed; if any check failed, stop here and keep Django intact.

Copy the full contents of `requirements-fastapi.txt` to `requirements.txt`, then delete `requirements-fastapi.txt`. Do not remove frontend code or the old reference project at `C:\Users\sunyupeng\PycharmProjects\AI Ops`.

- [ ] **Step 3: Run final clean-room verification**

Run:

```powershell
cd backend
python -m pip install -r requirements.txt
$env:AIOPS_DATABASE_MODE='test'
python -m alembic downgrade base
python -m alembic upgrade head
python -m pytest tests_fastapi -q
Remove-Item Env:AIOPS_DATABASE_MODE
rg -n "from django|import django|rest_framework" app tests_fastapi
cd ..\frontend
npm run build
```

Expected: all tests pass, Alembic upgrades an empty test database, Django scan has no matches, and frontend production build succeeds.

- [ ] **Step 4: Commit cutover**

Run: `git add -A backend; git commit -m "refactor: cut over backend runtime to FastAPI"`

## Final acceptance checklist

- [ ] Local development uses `ai_ops`; automated tests use only guarded `ai_ops_test`.
- [ ] Alembic passes empty upgrade, downgrade, repeat upgrade, and drift check.
- [ ] Every current RBAC, eventwall, ops, and AIOps model has a tested SQLAlchemy mapping before Django deletion.
- [ ] Raw passwords/tokens never appear in persisted rows, logs, audit metadata, or committed configuration.
- [ ] `admin` is active, superuser, idempotently initialized, and can perform writes.
- [ ] The username `demo` has no branch; API still returns `is_demo_account: false`.
- [ ] Direct-role and group-role permissions work; superuser bypass is server-side.
- [ ] Both module update payloads work; required modules cannot be disabled; audit is atomic and recursively redacted.
- [ ] All seven HTTP paths, trailing slashes, request fields, status codes, and response fields match the existing Vue usage.
- [ ] Every new endpoint, public service, selector, permission dependency, and non-obvious helper has a concise Chinese docstring.
- [ ] Django is removed only after the acceptance suite and browser smoke test pass.
- [ ] The old reference project `C:\Users\sunyupeng\PycharmProjects\AI Ops` remains unchanged.
