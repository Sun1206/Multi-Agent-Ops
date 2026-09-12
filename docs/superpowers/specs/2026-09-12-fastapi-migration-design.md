# AI Ops FastAPI Migration Design

## 1. Goal

Replace the new project's Django/DRF backend with FastAPI while keeping the Vue frontend unchanged. Preserve the established HTTP paths, request bodies, response shapes, RBAC behavior, module settings, audit semantics, and the requirement that admin is an enabled superuser that can perform every read and write operation.

The migration targets C:\Users\sunyupeng\PycharmProjects\AI-Ops. The old project at C:\Users\sunyupeng\PycharmProjects\AI Ops remains a read-only behavior reference and is not modified.

## 2. Chosen Stack

- Python 3.12
- FastAPI
- Pydantic 2 and pydantic-settings
- SQLAlchemy 2 asynchronous ORM
- asyncmy MySQL driver
- Alembic migrations
- MySQL 8 with InnoDB and utf8mb4
- pwdlib with Argon2id password hashing
- Opaque database-backed authentication tokens
- pytest, pytest-asyncio, and HTTPX AsyncClient
- Uvicorn for local HTTP serving

SQLModel is not used because the platform has many relationships, indexes, constraints, JSON fields, and domain-specific queries that benefit from direct SQLAlchemy control. Synchronous SQLAlchemy is not used because future AIOps, WebSocket, and external-system calls benefit from a consistently asynchronous request stack.

## 3. Project Structure

    backend/
    ├── app/
    │   ├── main.py
    │   ├── core/
    │   │   ├── config.py
    │   │   ├── database.py
    │   │   ├── exceptions.py
    │   │   ├── permissions.py
    │   │   └── security.py
    │   ├── models/
    │   ├── schemas/
    │   ├── api/routers/
    │   ├── services/
    │   └── selectors/
    ├── alembic/
    │   ├── env.py
    │   └── versions/0001_initial.py
    ├── tests/
    ├── alembic.ini
    └── requirements.txt

Routers only handle HTTP concerns. Services own writes and transaction boundaries. Selectors own read-only queries and aggregation. SQLAlchemy models describe persistence only and do not start threads, connect to external systems, or execute workflows.

## 4. Replacement Strategy

The migration is staged:

1. Add the FastAPI runtime, configuration, async database session, and pytest infrastructure alongside the current Django files.
2. Convert the four domain model groups to SQLAlchemy and generate one new Alembic initial migration.
3. Restore authentication, RBAC, module settings, and event auditing with the same frontend contracts.
4. Verify FastAPI tests, Alembic, frontend production build, and browser login flow.
5. Only after the FastAPI acceptance suite passes, remove Django settings, DRF code, Django migrations, manage.py, and db.sqlite3.
6. Continue with dashboard and application-shell endpoints using the FastAPI architecture.

There will be one runtime after the migration. Django and FastAPI will not remain as permanent parallel backends.

## 5. MySQL Configuration

Development and tests use the same local MySQL 8 instance but different databases:

    ai_ops       local development database
    ai_ops_test  automated test database

Connection settings are supplied through environment variables:

    MYSQL_HOST
    MYSQL_PORT
    MYSQL_DATABASE
    MYSQL_TEST_DATABASE
    MYSQL_USER
    MYSQL_PASSWORD

No real credentials or fallback production password are committed. The application builds an mysql+asyncmy URL internally so passwords containing reserved URL characters are encoded correctly.

All tables use InnoDB and utf8mb4. Application timestamps are stored in UTC. API serialization uses timezone-aware values and presents local business time using Asia/Shanghai where display conversion is required.

The test startup guard requires MYSQL_TEST_DATABASE to end with _test and rejects a test database name equal to MYSQL_DATABASE. Tests may clean or recreate only the guarded test database.

## 6. Models and Alembic

The existing Django models are a schema and business-language reference, not code imported by FastAPI. SQLAlchemy mappings preserve:

- table and column meanings;
- field lengths, nullability, defaults, and choices;
- foreign keys, many-to-many association tables, and deletion behavior;
- indexes, uniqueness rules, and ordering semantics needed by selectors;
- decimal precision for monetary audit data;
- JSON structures used by AIOps traces, audit metadata, and configuration.

The new MySQL database contains no Django migration history. Alembic 0001_initial creates every required application table plus authentication tables. It must pass upgrade from empty, downgrade to empty, and a second upgrade.

Generated migrations contain schema operations only. Data initialization is performed by explicit idempotent commands or services, not by import-time hooks.

## 7. Authentication

The frontend contract remains:

    Authorization: Token <opaque-token>

Login generates a cryptographically secure random token. The raw token is returned once; only a SHA-256 digest is stored in MySQL. Authentication hashes the presented token and performs an indexed lookup. Logout deletes the token record.

For first-stage compatibility, tokens do not expire automatically. Passwords are stored only as Argon2id hashes using pwdlib. Logs, exceptions, event metadata, and database audit records never contain raw passwords or raw tokens.

The admin account is created or upgraded only when AIOPS_ADMIN_INITIAL_PASSWORD is explicitly set. Initialization guarantees:

- username is exactly admin;
- the account is active and is a superuser;
- the account can perform every read and write action;
- rerunning initialization does not create duplicates;
- another superuser does not prevent creation of admin.

The username demo has no special handling. The compatibility response field is_demo_account remains present and always returns false.

## 8. RBAC

The complete permission registry and built-in role definitions remain unchanged. Permission synchronization uses deterministic codes and is idempotent.

Effective permissions combine direct user roles and roles inherited through user groups. Superusers bypass ordinary permission checks. Ordinary users must possess every permission declared by an endpoint dependency. Frontend menu visibility is not a security boundary.

## 9. Module Settings and Event Audit

The eight existing module definitions, descriptions, required flags, and sort order remain unchanged. Required modules cannot be disabled. Both request shapes remain accepted:

    [{"code": "containers", "enabled": false}]

    {"modules": [{"code": "containers", "enabled": false}]}

Successful updates create an event audit record containing the actor, method, path, safe source address, resource identity, correlation ID, and sanitized metadata.

Sensitive-key detection is recursive and covers authorization, cookies, passwords, secrets, tokens, access keys, private keys, certificates, SSH credentials, and kubeconfig data. Authentication headers and cookies are never copied into event metadata.

## 10. First Restored HTTP Contracts

The first FastAPI slice restores:

    POST /api/auth/login/
    POST /api/auth/logout/
    GET  /api/auth/me/
    POST /api/auth/sync/
    GET  /api/module-settings/
    PUT  /api/module-settings/
    PATCH /api/module-settings/

Responses keep the existing frontend shapes, including detail errors, login {token, user}, logout {success: true}, sorted effective_permissions, display_name, role/group summaries, and is_demo_account: false.

After this slice is stable, implementation proceeds to dashboard, deployment approval, transaction ticket, event wall, and AIOps bootstrap/audit endpoints.

## 11. Error Handling

The public error envelope is:

    {"detail": "具体错误信息"}

Status codes:

- 400 for invalid business input and incorrect username/password;
- 401 for missing or invalid authentication;
- 403 for authenticated users without required permissions;
- 404 for missing resources;
- 409 for uniqueness and business-state conflicts;
- 422 for Pydantic field-validation failures;
- 500 for unhandled server errors.

Unhandled errors are logged with a correlation ID. Public responses never include tracebacks, connection URLs, passwords, or tokens.

## 12. Documentation Convention

Every newly implemented router endpoint, public service function, selector, permission dependency, and non-obvious helper includes a concise Chinese docstring.

Router docstrings state the route, HTTP method, authorization requirement, and purpose. Service and selector docstrings state inputs, outputs, transaction behavior, side effects, and security boundaries. Generated Alembic files and tests are exempt from redundant docstrings.

## 13. Testing and Acceptance

The FastAPI suite uses pytest, pytest-asyncio, and HTTPX AsyncClient. It covers:

- configuration validation and test-database safety guards;
- model relationships, indexes, constraints, JSON fields, and decimal precision;
- Alembic upgrade, downgrade, and repeat-upgrade behavior;
- admin initialization and upgrade idempotency;
- login, current user, logout, invalid-token, and invalid-password behavior;
- token digest storage with no raw token persisted;
- direct-role and group-role permissions;
- superuser write access and absence of demo username branches;
- module catalog, required-module enforcement, both payload shapes, and permission denial;
- audit creation and recursive sensitive-value redaction;
- compatibility of response fields consumed by the Vue frontend.

Completion requires:

1. The FastAPI test suite passes against ai_ops_test.
2. Alembic creates ai_ops from an empty database without manual SQL.
3. No Django or DRF runtime import remains under backend.
4. The Vue production build passes unchanged.
5. A browser can sign in as admin, load current-user and module-setting requests, and log out without restored-endpoint console errors.
6. Source and logs pass secret, obsolete demo-account, and Chinese mojibake scans.

## 14. Out of Scope

- Preserving the current SQLite file or Django migration history.
- Migrating production or customer data.
- JWT, refresh tokens, SSO, OAuth, or automatic token expiration.
- Running Django and FastAPI permanently side by side.
- Implementing every frontend page before the first compatibility slice is verified.
- Changing Vue routes, UI layout, or API wrapper paths.

## 15. Operational Impact

The old project is not modified. The new project's local SQLite data is intentionally replaced; it contains only admin, built-in roles, permissions, and module settings, with no domain business records. Those deterministic records are recreated in MySQL by explicit initialization.

The migration changes backend technology but not the frontend contract. Risk is controlled through contract tests, staged removal of Django, isolated MySQL test data, explicit initialization, and browser-level verification.
