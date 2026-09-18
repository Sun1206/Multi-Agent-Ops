# 运行概览后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改现有前端和数据库结构的前提下，实现运行概览真实聚合接口，并从新智能助手请求开始记录模型 Token、费用与耗时。

**Architecture:** 新增独立的 audit API、schema 和 selector，查询现有模型调用、工具调用和助手消息元数据。新增模型调用记录服务负责安全提取 usage 与计算费用，聊天任务仅把请求结果交给该服务并与消息终态同事务保存。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy 2 async、MySQL/SQLite、pytest、httpx。

---

## 文件结构

- Create: `backend/aiops/api/audit.py` — 运行概览只读路由与权限。
- Create: `backend/aiops/schemas/audit.py` — 时间范围和响应模型。
- Create: `backend/aiops/selectors/audit.py` — 数据库聚合与消息元数据分布统计。
- Create: `backend/aiops/services/model_invocations.py` — usage 归一化、费用计算和调用记录构造。
- Modify: `backend/aidevops/restricted_http.py` — 返回安全的完整 Chat Completions JSON，保留现有文本接口兼容性。
- Modify: `backend/aiops/services/chat_jobs.py` — 采集调用耗时与终态记录。
- Modify: `backend/aidevops/routes.py` — 注册 audit router。
- Create: `backend/tests_fastapi/integration/test_aiops_runtime_overview.py` — 聚合接口、权限和时间过滤。
- Create: `backend/tests_fastapi/unit/test_model_invocations.py` — usage、金额和摘要单元测试。
- Modify: `backend/tests_fastapi/integration/test_chat_sending.py` — 成功、失败、取消与事务测试。
- Modify: `backend/tests_fastapi/contract/test_app_routes.py` — 新路由契约。

### Task 1: 时间范围契约

**Files:**
- Create: `backend/aiops/schemas/audit.py`
- Test: `backend/tests_fastapi/integration/test_aiops_runtime_overview.py`

- [ ] **Step 1: 写失败测试**

```python
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from aiops.schemas.audit import AuditRange

def test_audit_range_defaults_to_recent_seven_days():
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    resolved = AuditRange().resolve(now)
    assert resolved.start == now - timedelta(days=7)
    assert resolved.end == now

def test_audit_range_accepts_all_and_aware_custom_range():
    assert AuditRange(range='all').resolve().start is None
    value = AuditRange(start='2026-09-01T00:00:00+08:00', end='2026-09-02T00:00:00+08:00').resolve()
    assert value.start == datetime(2026, 8, 31, 16, tzinfo=timezone.utc)

@pytest.mark.parametrize('payload', [
    {'days': 7, 'range': 'all'},
    {'start': '2026-09-01T00:00:00Z'},
    {'start': '2026-09-02T00:00:00Z', 'end': '2026-09-01T00:00:00Z'},
    {'start': '2025-01-01T00:00:00Z', 'end': '2026-09-01T00:00:00Z'},
])
def test_audit_range_rejects_invalid_windows(payload):
    with pytest.raises(ValidationError):
        AuditRange(**payload)
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_aiops_runtime_overview.py -q`

Expected: FAIL，提示 `aiops.schemas.audit` 不存在。

- [ ] **Step 3: 实现严格时间范围模型**

```python
from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple
from pydantic import BaseModel, Field, model_validator

class ResolvedAuditRange(NamedTuple):
    start: datetime | None
    end: datetime | None

class AuditRange(BaseModel):
    days: int | None = Field(default=None, ge=1, le=365)
    start: datetime | None = None
    end: datetime | None = None
    range: Literal['all'] | None = None

    @model_validator(mode='after')
    def validate_range(self):
        if self.range and any(value is not None for value in (self.days, self.start, self.end)):
            raise ValueError('全部时间不能与其他时间参数同时使用。')
        if (self.start is None) != (self.end is None):
            raise ValueError('开始时间和结束时间必须同时提供。')
        if self.days is not None and self.start is not None:
            raise ValueError('最近天数不能与自定义时间同时使用。')
        if self.start is not None:
            if self.start.tzinfo is None or self.end.tzinfo is None:
                raise ValueError('时间必须包含时区。')
            if self.start >= self.end or self.end - self.start > timedelta(days=365):
                raise ValueError('时间范围无效或超过365天。')
        return self

    def resolve(self, now: datetime | None = None) -> ResolvedAuditRange:
        if self.range == 'all':
            return ResolvedAuditRange(None, None)
        end = self.end.astimezone(timezone.utc) if self.end else (now or datetime.now(timezone.utc))
        start = self.start.astimezone(timezone.utc) if self.start else end - timedelta(days=self.days or 7)
        return ResolvedAuditRange(start, end)
```

- [ ] **Step 4: 运行测试确认通过并提交**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_aiops_runtime_overview.py -q`

```powershell
git add backend/aiops/schemas/audit.py backend/tests_fastapi/integration/test_aiops_runtime_overview.py
git commit -m "feat: add runtime overview time range contract"
```

### Task 2: 运行分布和成本聚合

**Files:**
- Create: `backend/aiops/selectors/audit.py`
- Modify: `backend/tests_fastapi/integration/test_aiops_runtime_overview.py`

- [ ] **Step 1: 写失败聚合测试**

插入两个币种的 `AIOpsModelInvocation`、成功和失败的 `AIOpsToolInvocation`，以及一条结构化助手消息：

```python
metadata_data={
    'skill_traces': [{'key': 'alert-analysis', 'label': '告警分析'}],
    'action_traces': [{'key': 'alert.root_cause', 'label': '告警根因分析'}],
}
```

断言：

```python
overview = await build_overview(memory_session, AuditRange(range='all').resolve())
assert overview['invocation_distribution']['mcp_tools'][0] == {
    'key': 'query_alerts', 'label': 'query_alerts', 'count': 2,
}
costs = await build_costs(memory_session, AuditRange(range='all').resolve())
assert costs['model']['total_calls'] == 3
assert costs['model']['total_tokens'] == 350
assert [row['currency'] for row in costs['model']['by_currency']] == ['CNY', 'USD']
assert costs['model']['estimated_cost_usd'] == 0
```

- [ ] **Step 2: 运行测试并确认聚合函数缺失**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_aiops_runtime_overview.py -q`

Expected: FAIL，提示 `build_overview` 或 `build_costs` 不存在。

- [ ] **Step 3: 实现 selector**

实现 `build_overview(session: AsyncSession, window: ResolvedAuditRange) -> dict` 和 `build_costs(session: AsyncSession, window: ResolvedAuditRange) -> dict`。SQL 聚合模型和工具记录；使用统一 `_time_conditions`；provider 名称表达式固定为 `func.coalesce(AIOpsModelProvider.name, '已删除提供商')`；同一提供商不同币种分组；Decimal 量化到六位小数后转 float；Skill/Action 只读取 `skill_traces`、`action_traces` 结构化列表；忽略非法项；按 `(-count, key)` 排序并限制 100 项；空数据返回完整零值结构。

- [ ] **Step 4: 运行聚合测试并提交**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_aiops_runtime_overview.py -q`

```powershell
git add backend/aiops/selectors/audit.py backend/tests_fastapi/integration/test_aiops_runtime_overview.py
git commit -m "feat: aggregate runtime overview data"
```

### Task 3: 概览 API 与权限

**Files:**
- Create: `backend/aiops/api/audit.py`
- Modify: `backend/aidevops/routes.py`
- Modify: `backend/tests_fastapi/integration/test_aiops_runtime_overview.py`
- Modify: `backend/tests_fastapi/contract/test_app_routes.py`

- [ ] **Step 1: 写失败接口测试**

```python
@pytest.mark.asyncio
async def test_runtime_overview_routes_require_audit_permission(rbac_client):
    client, headers, _ = rbac_client
    for path in ('overview/', 'costs/'):
        assert (await client.get('/api/aiops/admin/audit/' + path, headers=headers)).status_code == 200
        assert (await client.get('/api/aiops/admin/audit/' + path)).status_code == 401

@pytest.mark.asyncio
async def test_runtime_overview_query_validation(rbac_client):
    client, headers, _ = rbac_client
    response = await client.get('/api/aiops/admin/audit/overview/', headers=headers, params={'range': 'all', 'days': 7})
    assert response.status_code == 422
```

另建仅拥有 `ops.dashboard.view` 的账号断言 403，再授予 `aiops.audit.view` 断言 200。

- [ ] **Step 2: 运行测试并确认两个路径返回 404**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_aiops_runtime_overview.py tests_fastapi/contract/test_app_routes.py -q`

- [ ] **Step 3: 实现并注册 router**

```python
from typing import Annotated
from fastapi import APIRouter, Depends
from aidevops.dependencies import SessionDependency, require_permissions
from aiops.schemas.audit import AuditRange
from aiops.selectors.audit import build_costs, build_overview
from rbac.models import User

router = APIRouter(prefix='/api/aiops/admin/audit', tags=['AIOps运行概览'])
AuditViewer = Annotated[User, Depends(require_permissions('aiops.audit.view'))]

@router.get('/overview/', description='按时间范围读取工具、Skill 与 Action 的真实调用分布。')
async def get_overview(session: SessionDependency, actor: AuditViewer, filters: Annotated[AuditRange, Depends()]):
    return await build_overview(session, filters.resolve())

@router.get('/costs/', description='按时间范围汇总模型 Token、费用、耗时和工具调用。')
async def get_costs(session: SessionDependency, actor: AuditViewer, filters: Annotated[AuditRange, Depends()]):
    return await build_costs(session, filters.resolve())
```

在 `aidevops/routes.py` 将 audit router 放在配置路由后、聊天路由前；更新路由契约基线。

- [ ] **Step 4: 运行接口测试并提交**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_aiops_runtime_overview.py tests_fastapi/contract/test_app_routes.py -q`

```powershell
git add backend/aiops/api/audit.py backend/aidevops/routes.py backend/tests_fastapi/integration/test_aiops_runtime_overview.py backend/tests_fastapi/contract/test_app_routes.py
git commit -m "feat: expose runtime overview audit endpoints"
```

### Task 4: usage 与费用记录服务

**Files:**
- Create: `backend/aiops/services/model_invocations.py`
- Create: `backend/tests_fastapi/unit/test_model_invocations.py`
- Modify: `backend/aidevops/restricted_http.py`
- Modify: `backend/tests_fastapi/contract/test_http_client_safety.py`

- [ ] **Step 1: 写失败单元测试**

```python
from decimal import Decimal
from aiops.services.model_invocations import invocation_values

def test_invocation_values_uses_real_usage_and_provider_currency():
    values = invocation_values(provider={'id': 3, 'name': 'DeepSeek', 'default_model': 'deepseek-chat',
        'price_currency': 'CNY', 'input_token_price_per_1m': Decimal('2'),
        'output_token_price_per_1m': Decimal('8')}, session_id=7, message_id=9,
        username='admin', latency_ms=125, result={'model': 'deepseek-chat-v3',
        'usage': {'prompt_tokens': 1000, 'completion_tokens': 500, 'total_tokens': 1500}},
        status='success', termination='completed', request_summary={'message_count': 2})
    assert values['total_tokens'] == 1500
    assert values['estimated_cost_usd'] == Decimal('0.006000')
    assert values['estimated_cost_currency'] == 'CNY'

def test_invocation_values_does_not_estimate_invalid_usage():
    values = invocation_values(provider={'id': 1, 'name': 'x', 'default_model': 'm',
        'price_currency': 'USD', 'input_token_price_per_1m': Decimal('1'),
        'output_token_price_per_1m': Decimal('1')}, session_id=1, message_id=2,
        username='u', latency_ms=1, result={'usage': {'prompt_tokens': -1,
        'completion_tokens': 'secret'}}, status='failed', termination='failure', request_summary={})
    assert values['total_tokens'] == 0
    assert values['estimated_cost_usd'] == Decimal('0.000000')
```

- [ ] **Step 2: 运行测试并确认模块缺失**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/unit/test_model_invocations.py -q`

- [ ] **Step 3: 实现纯函数和 ORM 构造器**

实现签名 `invocation_values(*, provider: dict, session_id: int, message_id: int, username: str, latency_ms: int, result: object, status: str, termination: str, request_summary: dict) -> dict`，并使用下面的 ORM 构造器：

```python
def model_invocation(**kwargs) -> AIOpsModelInvocation:
    return AIOpsModelInvocation(**invocation_values(**kwargs))
```

Token 只接受 `0 <= int <= 2_000_000_000`；total 不可信时使用已验证 prompt 与 completion 之和。模型 ID 使用 `safe_model_id`，非法时回退请求模型。金额用 Decimal 和 `ROUND_HALF_UP` 六位量化。摘要只允许 termination、has_usage、message_count 和长度字段。

- [ ] **Step 4: 扩展 HTTP 客户端并保持兼容接口**

```python
async def request_completion(target, api_key, payload, timeout_seconds, *, transport=None) -> dict:
    return await request_json(target, api_key, 'POST', '/chat/completions', {**payload, 'stream': False}, timeout_seconds, transport=transport)

async def request_text(target, api_key, payload, timeout_seconds, *, transport=None) -> str:
    result = await request_completion(target, api_key, payload, timeout_seconds, transport=transport)
    return text_content(result).replace(api_key, '***')
```

补充安全契约：`request_text` 行为不变、stream 固定 false、超大响应仍拒绝。

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/unit/test_model_invocations.py tests_fastapi/contract/test_http_client_safety.py -q`

```powershell
git add backend/aiops/services/model_invocations.py backend/aidevops/restricted_http.py backend/tests_fastapi/unit/test_model_invocations.py backend/tests_fastapi/contract/test_http_client_safety.py
git commit -m "feat: capture safe model invocation usage"
```

### Task 5: 聊天调用落库

**Files:**
- Modify: `backend/aiops/services/chat_jobs.py`
- Modify: `backend/tests_fastapi/integration/test_chat_sending.py`

- [ ] **Step 1: 改为完整响应 mock 并写失败断言**

```python
async def reply(*_args, **_kwargs):
    return {'model': 'resolved-model', 'choices': [{'message': {'content': 'test answer'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
monkeypatch.setattr(model_client, 'request_completion', reply)
```

等待任务后查询 `AIOpsModelInvocation`，断言 provider/session/message、success、15 Token、非负耗时，且不含 prompt、answer 或 API Key。远端异常和取消分别断言 termination 为 failure、cancelled；模型未配置时断言不创建记录。

- [ ] **Step 2: 运行测试并确认没有调用记录**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_chat_sending.py -q`

- [ ] **Step 3: 接入记录服务**

把 `name`、`price_currency`、`input_token_price_per_1m`、`output_token_price_per_1m` 加入 `PROVIDER_FIELDS`。`ChatJobs.run` 使用 `perf_counter()`、`request_completion` 和 `text_content`；成功、远端失败、取消各构造一次不可变记录值。调用 `await update_result(factory, session_id, assistant_id, user_id, terminal_status, content, expected, invocation_values=values)`，并在消息终态同一事务添加 `AIOpsModelInvocation`。配置变化只令消息失败，不抹掉真实远端 usage 与费用；发送前失败不生成记录。

- [ ] **Step 4: 验证提交失败不发布回答、不重复统计**

扩展 `test_completed_transaction_failure_does_not_publish_answer`：首次终态提交失败后最终最多一条调用记录，且回答未发布。第二次安全终态也失败时允许没有记录，但禁止重复。

- [ ] **Step 5: 运行测试并提交**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/integration/test_chat_sending.py tests_fastapi/integration/test_aiops_runtime_overview.py -q`

```powershell
git add backend/aiops/services/chat_jobs.py backend/tests_fastapi/integration/test_chat_sending.py
git commit -m "feat: persist assistant model invocation metrics"
```

### Task 6: 完整验证

**Files:** Verify only.

- [ ] **Step 1: 编译检查**

Run: `cd backend && .\.venv\Scripts\python.exe -m compileall -q aiops aidevops tests_fastapi`

Expected: exit code 0，无输出。

- [ ] **Step 2: 运行相关测试**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests_fastapi/unit/test_model_invocations.py tests_fastapi/integration/test_aiops_runtime_overview.py tests_fastapi/integration/test_chat_sending.py tests_fastapi/contract/test_app_routes.py tests_fastapi/contract/test_http_client_safety.py -q`

Expected: 全部通过。

- [ ] **Step 3: 运行后端全量测试**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest -q`

Expected: 全部通过；允许既有显式 skip，不允许新增失败。

- [ ] **Step 4: 运行前端生产构建**

Run: `cd frontend && npx vite build --configLoader runner`

Expected: exit code 0。

- [ ] **Step 5: 检查差异和敏感信息**

Run: `git diff --check`

Run: `rg -n "test-key|provider-secret|api_key_encrypted.*=" backend/aiops/api/audit.py backend/aiops/selectors/audit.py backend/aiops/services/model_invocations.py backend/aiops/services/chat_jobs.py`

Expected: 没有空白错误，也没有硬编码凭据或密文。
