# AI Ops Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new Django backend that preserves the old system's authentication, RBAC, module-setting, dashboard-statistics, AIOps audit, and application-shell behavior while using smaller service and selector modules.

**Architecture:** Keep the old project's model and HTTP contracts as the compatibility boundary. Put state changes in application services, read-only aggregation in selectors, and HTTP concerns in DRF views; the frontend remains unchanged. The first release supports every request automatically issued after `admin` logs in, while AIOps chat is configured disabled until its later vertical slice.

**Tech Stack:** Python 3.12, Django 5.x, Django REST Framework 3.15+, DRF Token Authentication, django-filter, django-cors-headers, Channels/Daphne, SQLite for local/test, MySQL via PyMySQL for production, Vue 3/Vite 6 for contract verification.

---

## Scope and file map

Create these focused units under `backend/`:

- `config/settings/base.py`: shared Django, DRF, database, cache, time-zone, static and logging settings.
- `config/settings/development.py`: safe local defaults only.
- `config/settings/production.py`: mandatory production-secret and host validation.
- `config/urls.py`, `config/asgi.py`, `config/wsgi.py`: HTTP and ASGI entry points.
- `common/pagination.py`: shared page-number pagination.
- `rbac/models.py`: compatible permission, role, group and module-setting schema.
- `rbac/registry.py`: immutable permission and built-in-role definitions copied from the old compatibility source.
- `rbac/services/permissions.py`: built-in synchronization and effective-permission calculation.
- `rbac/services/accounts.py`: environment-controlled `admin` creation.
- `rbac/services/modules.py`: module catalog and update transaction.
- `rbac/api/serializers.py`, `rbac/api/permissions.py`, `rbac/api/views.py`, `rbac/urls.py`: authentication and RBAC HTTP boundary.
- `eventwall/models.py`, `eventwall/services/recording.py`: compatible operation-event persistence.
- `ops/models.py`: old schema compatibility baseline; do not place workflows in the model module.
- `ops/dashboard/selectors.py`: dashboard aggregation.
- `ops/notifications/selectors.py`: pending deployment and transaction-ticket reads needed by the application shell.
- `ops/api/dashboard.py`, `ops/api/notifications.py`, `ops/urls.py`: first-stage ops endpoints.
- `aiops/models.py`: old schema compatibility baseline.
- `aiops/audit/costs.py`: cost and latency aggregation.
- `aiops/audit/traces.py`: Skill and Action trace parsing from message metadata.
- `aiops/audit/overview.py`: invocation distribution and daily overview.
- `aiops/bootstrap/selectors.py`: disabled-Agent bootstrap payload.
- `aiops/api/views.py`, `aiops/urls.py`: first-stage AIOps endpoints.
- `tests/contract/`: API-contract tests derived from frontend usage and old backend behavior.

Do not copy `aiops/services.py`, `ops/views.py`, or other old god modules into the new project. Model declarations and registry data may be transferred mechanically, then verified by schema tests.

All newly implemented API views, public service functions, selectors, reusable permission classes, and non-obvious helper methods must include concise Chinese docstrings. API docstrings state the route, HTTP method, authorization requirement and purpose; service/selector docstrings state their input, output and important side effects or security boundaries. Tests and generated migrations are exempt because their names and generated structure already document their intent.

### Task 1: Scaffold the Django runtime

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/manage.py`
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings/__init__.py`
- Create: `backend/config/settings/base.py`
- Create: `backend/config/settings/development.py`
- Create: `backend/config/settings/production.py`
- Create: `backend/config/urls.py`
- Create: `backend/config/asgi.py`
- Create: `backend/config/wsgi.py`
- Create: `backend/common/__init__.py`
- Create: `backend/common/pagination.py`
- Create: `backend/tests/__init__.py`
- Test: `backend/tests/test_settings.py`

- [x] **Step 1: Add a failing settings contract test**

```python
# backend/tests/test_settings.py
from django.conf import settings
from django.test import SimpleTestCase


class SettingsContractTests(SimpleTestCase):
    def test_api_defaults_match_frontend_contract(self):
        self.assertEqual(settings.LANGUAGE_CODE, 'zh-hans')
        self.assertEqual(settings.TIME_ZONE, 'Asia/Shanghai')
        self.assertEqual(settings.REST_FRAMEWORK['PAGE_SIZE'], 20)
        self.assertIn(
            'rest_framework.authentication.TokenAuthentication',
            settings.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'],
        )
```

- [x] **Step 2: Create and activate an isolated environment**

Run:

```powershell
Set-Location C:\Users\sunyupeng\PycharmProjects\AI-Ops
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

`backend/requirements.txt` must contain:

```text
django>=5.0,<6.0
djangorestframework>=3.15,<4.0
django-filter>=25.1,<26.0
django-cors-headers>=4.3,<5.0
channels>=4.0,<5.0
channels-redis>=4.2,<5.0
daphne>=4.1,<5.0
pymysql>=1.1,<2.0
cryptography>=42.0
```

Expected: packages install successfully inside `.venv`; no global interpreter is modified.

- [x] **Step 3: Implement minimal settings and entry points**

Use `DJANGO_SETTINGS_MODULE=config.settings.development` in `manage.py`, ASGI and WSGI. In `base.py`, configure the apps and DRF contract:

```python
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'corsheaders',
    'channels',
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PAGINATION_CLASS': 'common.pagination.DefaultPageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ],
}
```

`development.py` uses SQLite and a development-only fallback key. `production.py` reads `SECRET_KEY` and `ALLOWED_HOSTS` and raises `django.core.exceptions.ImproperlyConfigured` when either is absent; it must not default CORS to all origins.

- [x] **Step 4: Run the settings test and Django check**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.test_settings -v 2
.\.venv\Scripts\python.exe backend\manage.py check
```

Expected: the test passes and Django reports `System check identified no issues`.

- [ ] **Step 5: Commit the scaffold**

```powershell
git add backend/requirements.txt backend/manage.py backend/config backend/common backend/tests/__init__.py backend/tests/test_settings.py
git commit -m "chore: scaffold django backend"
```

### Task 2: Establish compatible domain models

**Files:**
- Create: `backend/rbac/models.py`
- Create: `backend/eventwall/models.py`
- Create: `backend/ops/models.py`
- Create: `backend/aiops/models.py`
- Create: `backend/rbac/apps.py`
- Create: `backend/eventwall/apps.py`
- Create: `backend/ops/apps.py`
- Create: `backend/aiops/apps.py`
- Create: `backend/tests/contract/__init__.py`
- Modify: `backend/config/settings/base.py`
- Test: `backend/tests/contract/test_model_schema.py`

- [x] **Step 1: Write schema compatibility tests before adding models**

```python
# backend/tests/contract/test_model_schema.py
from django.test import TestCase
from aiops.models import AIOpsAgentConfig, AIOpsModelInvocation, AIOpsToolInvocation
from ops.models import Alert, Deployment, Host, TransactionTicket
from rbac.models import PermissionDefinition, Role, SystemModuleSetting, UserGroup


class ModelSchemaContractTests(TestCase):
    def test_rbac_relationships_keep_old_related_names(self):
        self.assertEqual(Role._meta.get_field('users').remote_field.related_name, 'rbac_roles')
        self.assertEqual(UserGroup._meta.get_field('users').remote_field.related_name, 'rbac_groups')

    def test_audit_money_uses_decimal_storage(self):
        field = AIOpsModelInvocation._meta.get_field('estimated_cost_usd')
        self.assertEqual(field.max_digits, 12)
        self.assertEqual(field.decimal_places, 6)

    def test_first_stage_models_exist(self):
        self.assertTrue(all([
            PermissionDefinition, SystemModuleSetting, AIOpsAgentConfig,
            AIOpsToolInvocation, Host, Deployment, TransactionTicket, Alert,
        ]))
```

- [x] **Step 2: Run the schema test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_model_schema -v 2
```

Expected: FAIL with missing `rbac`, `ops`, `eventwall`, or `aiops` model modules.

- [x] **Step 3: Transfer model declarations as the compatibility baseline**

Using `apply_patch`, add the model declarations from these exact old sources:

```text
C:\Users\sunyupeng\PycharmProjects\AI Ops\backend\rbac\models.py
C:\Users\sunyupeng\PycharmProjects\AI Ops\backend\eventwall\models.py
C:\Users\sunyupeng\PycharmProjects\AI Ops\backend\ops\models.py
C:\Users\sunyupeng\PycharmProjects\AI Ops\backend\aiops\models.py
```

Preserve field names, choices, defaults, indexes, constraints, related names, deletion behavior and model ordering exactly. Do not transfer methods that start background threads or call external services; model-local display and encryption helpers remain with their models.

After the four app packages exist, append `'rbac'`, `'eventwall'`, `'ops'`, and `'aiops'` to `INSTALLED_APPS` in `config/settings/base.py`.

- [x] **Step 4: Generate a fresh initial migration for the new database**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py makemigrations rbac eventwall ops aiops
.\.venv\Scripts\python.exe backend\manage.py migrate
```

Expected: four initial migrations are created and applied to the local SQLite database.

- [x] **Step 5: Re-run schema and migration checks**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_model_schema -v 2
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
```

Expected: tests pass and migration check prints `No changes detected`.

- [ ] **Step 6: Commit the model baseline**

```powershell
git add backend/rbac backend/eventwall backend/ops backend/aiops backend/tests/contract/test_model_schema.py
git commit -m "feat: add compatible domain model baseline"
```

### Task 3: Implement RBAC synchronization and permission evaluation

**Files:**
- Create: `backend/rbac/registry.py`
- Create: `backend/rbac/services/__init__.py`
- Create: `backend/rbac/services/permissions.py`
- Create: `backend/rbac/api/__init__.py`
- Create: `backend/rbac/api/permissions.py`
- Test: `backend/tests/contract/test_rbac_permissions.py`

- [x] **Step 1: Add failing effective-permission tests**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac.models import PermissionDefinition, Role, UserGroup
from rbac.services.permissions import get_user_effective_permissions, user_has_permissions


User = get_user_model()


class EffectivePermissionTests(TestCase):
    def setUp(self):
        self.permission = PermissionDefinition.objects.create(
            code='ops.dashboard.view', name='查看运行概览', category='ops'
        )
        self.user = User.objects.create_user('operator', password='Admin@123456')

    def test_group_role_grants_permission(self):
        role = Role.objects.create(code='viewer', name='查看者')
        role.permissions.add(self.permission)
        group = UserGroup.objects.create(code='operators', name='运维组')
        group.roles.add(role)
        group.users.add(self.user)
        self.assertEqual(get_user_effective_permissions(self.user), {'ops.dashboard.view'})

    def test_admin_has_every_registered_permission_and_can_write(self):
        admin = User.objects.create_superuser('admin', 'admin@example.com', 'Admin@123456')
        self.assertTrue(user_has_permissions(admin, ['ops.dashboard.view']))

    def test_demo_named_user_has_no_special_permission_branch(self):
        demo = User.objects.create_user('demo', password='Admin@123456')
        self.assertEqual(get_user_effective_permissions(demo), set())
        self.assertFalse(user_has_permissions(demo, ['ops.dashboard.view']))
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_rbac_permissions -v 2
```

Expected: FAIL because the permission service does not exist.

- [x] **Step 3: Implement the permission service without username exceptions**

```python
# backend/rbac/services/permissions.py
from django.db import transaction
from rbac.models import PermissionDefinition, Role
from rbac.registry import BUILTIN_ROLES, PERMISSION_DEFINITIONS


@transaction.atomic
def ensure_builtin_rbac():
    permission_by_code = {}
    for index, (code, name, category, description) in enumerate(PERMISSION_DEFINITIONS, start=1):
        permission, _ = PermissionDefinition.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'category': category,
                'description': description,
                'sort_order': index,
                'is_builtin': True,
            },
        )
        permission_by_code[code] = permission
    for item in BUILTIN_ROLES:
        role, _ = Role.objects.update_or_create(
            code=item['code'],
            defaults={
                'name': item['name'],
                'description': item['description'],
                'is_builtin': True,
            },
        )
        codes = permission_by_code if '*' in item['permissions'] else item['permissions']
        role.permissions.set(permission_by_code[code] for code in codes if code in permission_by_code)


def get_user_effective_permissions(user):
    if not getattr(user, 'is_authenticated', False):
        return set()
    if user.is_superuser:
        return set(PermissionDefinition.objects.values_list('code', flat=True))
    direct = PermissionDefinition.objects.filter(roles__users=user).values_list('code', flat=True)
    grouped = PermissionDefinition.objects.filter(
        roles__user_groups__users=user
    ).values_list('code', flat=True)
    return set(direct).union(grouped)


def user_has_permissions(user, codes):
    codes = [code for code in codes or [] if code]
    if not codes:
        return True
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    granted = get_user_effective_permissions(user)
    return all(code in granted for code in codes)
```

Copy the complete `PERMISSION_DEFINITIONS` and `BUILTIN_ROLES` data from the old `rbac/registry.py`. Keep every registry entry so superuser and future-page permission behavior cannot drift.

- [x] **Step 4: Implement reusable DRF permission classes**

Create `RBACPermission`, `RBACPermissionMixin`, and `build_rbac_permission()` with the old missing-permission messages, but remove every `demo` username branch. Unsafe methods are allowed or denied solely through authentication and required permission codes.

- [x] **Step 5: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_rbac_permissions -v 2
```

Expected: all permission tests pass.

- [ ] **Step 6: Commit RBAC core**

```powershell
git add backend/rbac/registry.py backend/rbac/services backend/rbac/api/permissions.py backend/tests/contract/test_rbac_permissions.py
git commit -m "feat: implement rbac permission core"
```

### Task 4: Implement admin bootstrap and authentication APIs

**Files:**
- Create: `backend/rbac/services/accounts.py`
- Create: `backend/rbac/api/serializers.py`
- Create: `backend/rbac/api/views.py`
- Create: `backend/rbac/urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/tests/contract/test_auth_api.py`

- [x] **Step 1: Add failing API-contract tests**

```python
import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token


User = get_user_model()


class AuthApiContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='Admin@123456'
        )

    def test_login_me_and_logout_contract(self):
        login = self.client.post('/api/auth/login/', {
            'username': 'admin', 'password': 'Admin@123456'
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['user']['username'], 'admin')
        self.assertTrue(login.data['user']['is_superuser'])
        self.assertFalse(login.data['user']['is_demo_account'])
        self.assertIn('effective_permissions', login.data['user'])
        token = login.data['token']
        me = self.client.get('/api/auth/me/', HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(me.status_code, 200)
        logout = self.client.post('/api/auth/logout/', HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(logout.data, {'success': True})
        self.assertFalse(Token.objects.filter(user=self.admin).exists())

    def test_wrong_password_is_http_400(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'admin', 'password': 'wrong'
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], '用户名或密码错误。')

    @patch.dict(os.environ, {}, clear=True)
    def test_admin_is_not_created_without_environment_password(self):
        from rbac.services.accounts import ensure_default_superuser
        User.objects.all().delete()
        ensure_default_superuser()
        self.assertFalse(User.objects.filter(username='admin').exists())
```

- [x] **Step 2: Run the auth tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_auth_api -v 2
```

Expected: FAIL because auth serializers, URLs and views do not exist.

- [x] **Step 3: Implement environment-controlled admin creation**

```python
# backend/rbac/services/accounts.py
import os
from django.contrib.auth import get_user_model
from django.db import transaction


ADMIN_PASSWORD_ENV = 'SXDEVOPS_ADMIN_INITIAL_PASSWORD'


@transaction.atomic
def ensure_default_superuser():
    User = get_user_model()
    password = os.getenv(ADMIN_PASSWORD_ENV, '').strip()
    if not password:
        return None

    admin = User.objects.select_for_update().filter(username='admin').first()
    if admin:
        if admin.is_staff and admin.is_superuser:
            return None
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        if not admin.email:
            admin.email = 'admin@example.com'
        admin.set_password(password)
        admin.save(update_fields=[
            'email', 'is_active', 'is_staff', 'is_superuser', 'password',
        ])
        return admin

    return User.objects.create_superuser(
        username='admin', email='admin@example.com', password=password
    )
```

- [x] **Step 4: Implement serializers and auth views**

`UserSerializer` must expose the old fields, derive `display_name`, serialize `roles` and `user_groups`, and ignore write attempts to `is_active`, `is_staff`, and `is_superuser`. Retain the legacy response key `is_demo_account` strictly as a compatibility field that always serializes to `False`; it must never be computed from the username and must never participate in authorization. Implement login, logout, current-user and sync-permissions views with the exact old status codes and response text. Mount `rbac.urls` at `/api/`.

- [x] **Step 5: Run auth and RBAC regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_auth_api tests.contract.test_rbac_permissions -v 2
```

Expected: all tests pass.

- [ ] **Step 6: Commit authentication**

```powershell
git add backend/rbac backend/config/urls.py backend/tests/contract/test_auth_api.py
git commit -m "feat: add admin authentication api"
```

### Task 5: Implement module settings with operation auditing

**Files:**
- Create: `backend/eventwall/services/__init__.py`
- Create: `backend/eventwall/services/recording.py`
- Create: `backend/rbac/services/modules.py`
- Modify: `backend/rbac/api/views.py`
- Modify: `backend/rbac/urls.py`
- Test: `backend/tests/contract/test_module_settings.py`

- [x] **Step 1: Add failing module-setting tests**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from eventwall.models import EventRecord


User = get_user_model()


class ModuleSettingsContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='Admin@123456')
        self.client.force_login(self.admin)

    def test_catalog_shape_and_required_modules(self):
        response = self.client.get('/api/module-settings/')
        self.assertEqual(response.status_code, 200)
        dashboard = next(item for item in response.data if item['code'] == 'dashboard')
        self.assertTrue(dashboard['required'])
        self.assertTrue(dashboard['enabled'])

    def test_update_cannot_disable_required_module_and_records_event(self):
        response = self.client.put('/api/module-settings/', {
            'modules': [{'code': 'dashboard', 'enabled': False},
                        {'code': 'containers', 'enabled': False}]
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        settings = {item['code']: item for item in response.data['data']}
        self.assertTrue(settings['dashboard']['enabled'])
        self.assertFalse(settings['containers']['enabled'])
        self.assertTrue(EventRecord.objects.filter(action='update_module_settings').exists())
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_module_settings -v 2
```

Expected: FAIL because module services and endpoint do not exist.

- [x] **Step 3: Implement the exact module catalog and service**

Use the eight old entries and required flags:

```python
SYSTEM_MODULE_CATALOG = [
    {'code': 'dashboard', 'title': '仪表盘', 'required': True, 'sort_order': 10},
    {'code': 'aiops', 'title': 'AIOps', 'required': True, 'sort_order': 20},
    {'code': 'observability', 'title': '可观测性', 'required': True, 'sort_order': 30},
    {'code': 'events', 'title': '事件中心', 'required': True, 'sort_order': 40},
    {'code': 'tasks', 'title': '任务中心', 'required': True, 'sort_order': 50},
    {'code': 'workorders', 'title': '工单系统', 'required': False, 'sort_order': 60},
    {'code': 'containers', 'title': '容器管理', 'required': False, 'sort_order': 70},
    {'code': 'system', 'title': '系统管理', 'required': True, 'sort_order': 80},
]
```

Also preserve each old description, `updated_by`, `updated_at`, the accepted raw-list or `{modules: module_list}` payload, and the response `{'success': True, 'data': get_system_module_settings()}`.

- [x] **Step 4: Implement `record_event()` and call it after a successful update**

The recording service must accept `request`, `module`, `category`, `action`, `title`, `summary`, resource identifiers, severity, correlation ID and metadata. It stores safe request context but never authorization headers, passwords or tokens.

- [x] **Step 5: Run module and auth tests**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_module_settings tests.contract.test_auth_api -v 2
```

Expected: all tests pass.

- [ ] **Step 6: Commit module settings**

```powershell
git add backend/eventwall backend/rbac backend/tests/contract/test_module_settings.py
git commit -m "feat: add audited module settings"
```

### Task 6: Implement dashboard and shell-notification reads

**Files:**
- Create: `backend/ops/dashboard/__init__.py`
- Create: `backend/ops/dashboard/selectors.py`
- Create: `backend/ops/notifications/__init__.py`
- Create: `backend/ops/notifications/selectors.py`
- Create: `backend/ops/api/__init__.py`
- Create: `backend/ops/api/serializers.py`
- Create: `backend/ops/api/dashboard.py`
- Create: `backend/ops/api/notifications.py`
- Create: `backend/ops/urls.py`
- Create: `backend/eventwall/serializers.py`
- Create: `backend/eventwall/api.py`
- Create: `backend/eventwall/urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/tests/contract/test_shell_api.py`

- [ ] **Step 1: Add failing empty-state and populated-state tests**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from ops.models import Alert, Host


User = get_user_model()


class ShellApiContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='Admin@123456')
        self.client.force_login(self.admin)

    def test_every_automatic_shell_read_returns_200(self):
        cases = [
            ('/api/dashboard/stats/', None),
            ('/api/deployments/', {'approval_status': 'pending'}),
            ('/api/transaction-tickets/', {'status': 'pending'}),
            ('/api/events/analysis_wall/', {'limit': 80}),
        ]
        for url, params in cases:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, params or {}).status_code, 200)

    def test_dashboard_counts_hosts_and_unclaimed_alerts(self):
        Host.objects.create(hostname='node-1', ip_address='10.0.0.1', status='online')
        Alert.objects.create(
            title='CPU 高', level='critical', status='active',
            source='contract-test', message='CPU 使用率过高'
        )
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.data['hosts']['total'], 1)
        self.assertEqual(response.data['hosts']['online'], 1)
        self.assertEqual(response.data['alerts']['unacknowledged'], 1)
```

- [ ] **Step 2: Run the shell tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_shell_api -v 2
```

Expected: FAIL with unresolved URLs.

- [ ] **Step 3: Implement dashboard aggregation in a selector**

Move the old `dashboard_stats` ORM operations into `build_dashboard_stats()`. Return the exact keys:

```python
{
    'hosts': {'total': 0, 'online': 0, 'offline': 0, 'warning': 0,
              'avg_cpu': 0.0, 'avg_memory': 0.0, 'avg_disk': 0.0},
    'deployments': {'total': 0, 'success': 0, 'failed': 0, 'running': 0},
    'alerts': {'total': 0, 'unacknowledged': 0, 'critical': 0,
               'warning': 0, 'info': 0},
    'recent_deploys': [],
    'recent_alerts': [],
}
```

Use focused serializers for recent deployment and alert rows. The alert serializer exposes `id`, `title`, `message`, `source`, `level`, and `created_at`. The deployment notification serializer exposes `id`, `app_name`, `version`, `system_name`, `business_line`, `environment`, `environment_display`, `approval_status`, `current_approval_step`, and `deployed_at`. The transaction-ticket serializer exposes `id`, `title`, `system_name`, `business_line`, `environment`, `environment_display`, `type_display`, `status`, `updated_at`, and `created_at`. The event-wall suspect serializer exposes `id`, `title`, `summary`, `detail`, `resource_name`, `result`, and `occurred_at`. These are the exact fields consumed by `AppLayout.vue` and the future detail links.

- [ ] **Step 4: Implement the three notification reads**

`GET /api/deployments/` and `GET /api/transaction-tickets/` use standard DRF pagination and honor the old `approval_status` and `status` filters. `GET /api/events/analysis_wall/` returns the old object shape including `suspects`; it returns `suspects: []` when no events exist. All three must query the database rather than return hard-coded fixtures.

- [ ] **Step 5: Run shell tests and query-count checks**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_shell_api -v 2
```

Expected: all tests pass; empty-state endpoints return 200.

- [ ] **Step 6: Commit shell APIs**

```powershell
git add backend/ops backend/eventwall backend/config/urls.py backend/tests/contract/test_shell_api.py
git commit -m "feat: add dashboard and shell notification api"
```

### Task 7: Implement AIOps cost aggregation

**Files:**
- Create: `backend/aiops/audit/__init__.py`
- Create: `backend/aiops/audit/costs.py`
- Create: `backend/aiops/api/__init__.py`
- Create: `backend/aiops/api/views.py`
- Create: `backend/aiops/urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/tests/contract/test_aiops_costs.py`

- [ ] **Step 1: Add failing cost and window tests**

```python
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from aiops.models import AIOpsModelInvocation, AIOpsModelProvider


User = get_user_model()


class AIOpsCostContractTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', password='Admin@123456'))
        self.provider = AIOpsModelProvider.objects.create(
            name='OpenAI Compatible', provider_type='openai_compatible',
            input_token_price_per_1m=Decimal('1.000000'),
            output_token_price_per_1m=Decimal('2.000000'),
        )

    def test_cost_overview_groups_provider_tokens_and_cost(self):
        AIOpsModelInvocation.objects.create(
            provider=self.provider, requested_model='model-a', resolved_model='model-a',
            prompt_tokens=100, completion_tokens=20, total_tokens=120,
            estimated_cost_usd=Decimal('0.000140'), latency_ms=40,
        )
        response = self.client.get('/api/aiops/admin/audit/costs/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['model']['total_calls'], 1)
        self.assertEqual(response.data['model']['total_tokens'], 120)
        self.assertEqual(response.data['model']['by_provider'][0]['calls'], 1)

    def test_invalid_days_defaults_and_large_days_clamps(self):
        invalid = self.client.get('/api/aiops/admin/audit/costs/', {'days': 'bad'})
        clamped = self.client.get('/api/aiops/admin/audit/costs/', {'days': 999})
        self.assertEqual(invalid.data['window_days'], 7)
        self.assertEqual(clamped.data['window_days'], 90)

    def test_missing_trailing_slash_is_compatible(self):
        self.assertEqual(self.client.get('/api/aiops/admin/audit/costs').status_code, 200)
```

- [ ] **Step 2: Run the cost tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_aiops_costs -v 2
```

Expected: FAIL with unresolved audit-cost URL.

- [ ] **Step 3: Extract the old cost logic into `aiops/audit/costs.py`**

Using `apply_patch`, move `_parse_audit_range_datetime`, `_normalize_model_cost_currency`, and `build_model_cost_overview` from `C:\Users\sunyupeng\PycharmProjects\AI Ops\backend\aiops\services.py` into `backend/aiops/audit/costs.py`. Rename only the two private helpers by removing their leading underscore and update their internal call sites. Preserve recent/all/custom windows; model totals; `by_currency`, `by_provider`, `by_purpose`; tool totals and `by_tool`; decimal values; and integer average latency. The new module may import only Django ORM, time utilities and AIOps models—not views or chat runtime code.

- [ ] **Step 4: Add the permission-protected API and compatibility URL**

Use `IsAuthenticated` plus `build_rbac_permission('aiops.audit.view')`. Pass `days`, `range`, `start`, and `end` directly to the selector and register both slash and no-slash paths.

- [ ] **Step 5: Run cost tests**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_aiops_costs -v 2
```

Expected: all cost tests pass.

- [ ] **Step 6: Commit cost aggregation**

```powershell
git add backend/aiops backend/config/urls.py backend/tests/contract/test_aiops_costs.py
git commit -m "feat: add aiops cost aggregation"
```

### Task 8: Implement AIOps overview, trace distribution, and disabled bootstrap

**Files:**
- Create: `backend/aiops/audit/traces.py`
- Create: `backend/aiops/audit/overview.py`
- Create: `backend/aiops/bootstrap/__init__.py`
- Create: `backend/aiops/bootstrap/selectors.py`
- Modify: `backend/aiops/api/views.py`
- Modify: `backend/aiops/urls.py`
- Test: `backend/tests/contract/test_aiops_overview.py`

- [ ] **Step 1: Add failing overview and bootstrap tests**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from aiops.models import AIOpsAgentConfig, AIOpsChatMessage, AIOpsChatSession


User = get_user_model()


class AIOpsOverviewContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='Admin@123456')
        self.client.force_login(self.admin)

    def test_bootstrap_is_disabled_in_first_stage(self):
        response = self.client.get('/api/aiops/bootstrap/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['enabled'])
        self.assertIn('permissions', response.data)
        self.assertIn('active_mcp_servers', response.data)

    def test_message_metadata_contributes_skill_and_action_hits(self):
        session = AIOpsChatSession.objects.create(user=self.admin, title='诊断')
        AIOpsChatMessage.objects.create(
            session=session,
            role='assistant',
            content='完成',
            metadata={
                'skill_trace': {'items': [{'slug': 'root-cause', 'name': '根因分析',
                                           'status': 'used', 'used_tools': ['query_logs']}]},
                'action_trace': {'code': 'diagnose', 'display_name': '诊断', 'status': 'matched'},
            },
        )
        response = self.client.get('/api/aiops/admin/audit/overview/', {'range': 'all'})
        distribution = response.data['invocation_distribution']
        self.assertEqual(distribution['skill_hits'], 1)
        self.assertEqual(distribution['action_hits'], 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_aiops_overview -v 2
```

Expected: FAIL because overview and bootstrap behavior is absent.

- [ ] **Step 3: Implement the trace reader and overview selector**

Move only trace-reading and aggregation behavior from the old AIOps code. Preserve hidden trace IDs, assistant-message filtering, mirror-source exclusion, username/time filtering, label resolution and count ordering. Expose `build_invocation_distribution(request)` and `build_audit_overview(request)`. The latter returns the old daily totals, `session_status`, `action_status`, and `invocation_distribution`. Transfer the exact aggregation logic from `_audit_invocation_distribution` in old `aiops/views.py` and `build_audit_overview` in old `aiops/services.py`, then update imports so neither new module imports an API view.

- [ ] **Step 4: Implement first-stage bootstrap state**

Create or update the default `AIOpsAgentConfig` with `is_enabled=False`. Return the full old bootstrap response shape, including welcome text, suggested questions, action registry summary, permission flags, Provider summary, runtime flags, active MCP servers and active Skills. Do not implement chat execution in this task.

- [ ] **Step 5: Run overview and cost tests**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_aiops_overview tests.contract.test_aiops_costs -v 2
```

Expected: all tests pass and bootstrap does not cause a sessions request in the browser smoke test.

- [ ] **Step 6: Commit overview and bootstrap**

```powershell
git add backend/aiops backend/tests/contract/test_aiops_overview.py
git commit -m "feat: add aiops overview and bootstrap"
```

### Task 9: Add deterministic initialization commands

**Files:**
- Create: `backend/rbac/management/__init__.py`
- Create: `backend/rbac/management/commands/__init__.py`
- Create: `backend/rbac/management/commands/bootstrap_admin.py`
- Create: `backend/aiops/management/__init__.py`
- Create: `backend/aiops/management/commands/__init__.py`
- Create: `backend/aiops/management/commands/seed_foundation_audit.py`
- Test: `backend/tests/contract/test_bootstrap_commands.py`

- [ ] **Step 1: Add failing command tests**

```python
import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from aiops.models import AIOpsAgentConfig, AIOpsModelInvocation


User = get_user_model()


class BootstrapCommandTests(TestCase):
    @patch.dict(os.environ, {'SXDEVOPS_ADMIN_INITIAL_PASSWORD': 'Admin@123456'})
    def test_bootstrap_admin_is_idempotent(self):
        call_command('bootstrap_admin')
        call_command('bootstrap_admin')
        self.assertEqual(User.objects.filter(username='admin', is_superuser=True).count(), 1)

    def test_foundation_seed_is_idempotent_and_keeps_aiops_disabled(self):
        call_command('seed_foundation_audit')
        first = AIOpsModelInvocation.objects.count()
        call_command('seed_foundation_audit')
        self.assertEqual(AIOpsModelInvocation.objects.count(), first)
        self.assertFalse(AIOpsAgentConfig.objects.get(name='default').is_enabled)
```

- [ ] **Step 2: Run command tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_bootstrap_commands -v 2
```

Expected: FAIL with unknown commands.

- [ ] **Step 3: Implement idempotent commands**

`bootstrap_admin` must call `ensure_builtin_rbac()`, `ensure_system_module_settings()`, and `ensure_default_superuser()`. It exits with a clear message and no user creation when the password environment variable is absent.

`seed_foundation_audit` uses deterministic JSON identifiers and `update_or_create()` so reruns do not duplicate records. Use keys such as `{'seed_key': 'foundation-provider-openai-1'}`, `{'seed_key': 'foundation-model-invocation-1'}`, `{'seed_key': 'foundation-tool-invocation-1'}`, and `{'seed_key': 'foundation-assistant-message-1'}` in the models' JSON summary or metadata field, and use that complete JSON value as the lookup. Seed exactly two Providers, at least two model invocations, at least two tool invocations, and one assistant message containing both Skill and Action traces. Keep `AIOpsAgentConfig.is_enabled=False`.

- [ ] **Step 4: Run command tests twice**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test tests.contract.test_bootstrap_commands -v 2
```

Expected: all tests pass and idempotency assertions hold.

- [ ] **Step 5: Commit initialization commands**

```powershell
git add backend/rbac/management backend/aiops/management backend/tests/contract/test_bootstrap_commands.py
git commit -m "feat: add foundation bootstrap commands"
```

### Task 10: Verify the complete first-stage contract

**Files:**
- Create: `backend/tests/contract/test_first_stage_api.py`
- Create: `backend/.env.example`
- Create: `README.md`
- Inspect: `frontend/vite.config.js`; its existing `/api` and `/ws` proxies already target port 8000, so no edit is expected.

- [ ] **Step 1: Add a first-stage API flow test**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class FirstStageApiFlowTests(TestCase):
    def test_admin_login_and_every_automatic_read(self):
        User.objects.create_superuser('admin', password='Admin@123456')
        login = self.client.post('/api/auth/login/', {
            'username': 'admin', 'password': 'Admin@123456'
        })
        token = login.data['token']
        headers = {'HTTP_AUTHORIZATION': f'Token {token}'}
        urls = [
            '/api/auth/me/',
            '/api/module-settings/',
            '/api/dashboard/stats/',
            '/api/deployments/?approval_status=pending',
            '/api/transaction-tickets/?status=pending',
            '/api/events/analysis_wall/?limit=80',
            '/api/aiops/bootstrap/',
            '/api/aiops/admin/audit/overview/?days=7',
            '/api/aiops/admin/audit/costs/?days=7',
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, **headers).status_code, 200)
```

- [ ] **Step 2: Run all backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test -v 2
```

Expected: all tests pass with zero errors and zero failures.

- [ ] **Step 3: Run framework and migration verification**

Run:

```powershell
$env:SECRET_KEY='production-check-only-not-for-deployment'
$env:ALLOWED_HOSTS='localhost,127.0.0.1'
.\.venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.production
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
```

Expected: no application errors and `No changes detected`; expected HTTPS deployment warnings are reviewed and documented rather than suppressed in code.

- [ ] **Step 4: Build the unchanged frontend**

Run:

```powershell
Set-Location C:\Users\sunyupeng\PycharmProjects\AI-Ops\frontend
npm run build
```

Expected: Vite exits with code 0 and emits `frontend/dist`.

- [ ] **Step 5: Start local services for browser verification**

Run in separate terminals:

```powershell
Set-Location C:\Users\sunyupeng\PycharmProjects\AI-Ops
$env:SXDEVOPS_ADMIN_INITIAL_PASSWORD='a local password supplied by the user'
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py bootstrap_admin
.\.venv\Scripts\python.exe backend\manage.py seed_foundation_audit
.\.venv\Scripts\python.exe -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

```powershell
Set-Location C:\Users\sunyupeng\PycharmProjects\AI-Ops\frontend
npm run dev
```

Expected: backend listens on 8000 and frontend on 3000.

- [ ] **Step 6: Perform the browser smoke path**

Open `http://127.0.0.1:3000/login`, log in as `admin`, verify the running overview, change the audit time range, refresh the page, open the notification popover, and log out. Expected: no failed automatic API requests, no console errors, dashboard charts render, and the disabled AIOps bootstrap does not request `/api/aiops/sessions/`.

- [ ] **Step 7: Scan for secrets and accidental demo-account behavior**

Run:

```powershell
rg -n "Admin@123456|SXDEVOPS_ADMIN_INITIAL_PASSWORD\s*=|DEMO_ACCOUNT|username\s*==\s*['\"]demo['\"]" backend --glob '!backend/tests/**' --glob '!backend/.env.example'
git status --short
```

Expected: the source scan has no matches; only intentional, reviewed files are shown by Git.

- [ ] **Step 8: Commit documentation and final contract test**

```powershell
git add backend/tests/contract/test_first_stage_api.py backend/.env.example README.md
git commit -m "docs: document backend foundation workflow"
```

## Final verification checklist

- [ ] All old first-stage behavior tests and new frontend-contract tests pass.
- [ ] `admin` is a real writable superuser and no `demo` username branch remains.
- [ ] Every request automatically issued after login returns HTTP 200.
- [ ] AIOps bootstrap is structurally compatible and disabled until the chat phase.
- [ ] Dashboard and audit endpoints query persisted data rather than fixtures.
- [ ] Django reports no model drift.
- [ ] Frontend production build succeeds.
- [ ] Browser smoke test shows no failed requests or console errors.
- [ ] Secrets, local databases, logs, virtual environments, dependencies and build output remain untracked.
