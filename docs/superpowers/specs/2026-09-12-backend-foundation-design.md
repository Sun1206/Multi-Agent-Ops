# AI Ops 新后端第一阶段设计

## 1. 背景

`AI-Ops` 新目录当前仅包含 Vue 3 前端。前端通过 `/api` 调用约 375 个后端接口，覆盖认证、RBAC、运行概览、资源、任务、工单、容器、可观测性、事件中心和 AIOps。

新后端采用 Django、Django REST Framework 和 Channels 重新搭建。旧项目 `AI Ops` 的后端是业务行为基线，但不复制其巨型模块结构。新实现必须保持前端可观察行为、数据库语义、权限判断和状态流转等价，同时将 API、应用服务、只读查询和外部适配器分层。

## 2. 第一阶段目标

第一阶段交付“可登录的最小运行闭环”：

1. `admin` 可以登录、刷新身份并退出。
2. 前端路由和侧边栏依据真实后端权限工作。
3. 运行概览页面可以展示真实的 AIOps 调用分布和成本聚合；没有数据时返回结构完整的零值。
4. 顶部平台提醒依赖的仪表盘统计接口正常响应。
5. 登录后由应用外壳自动发起的请求全部正常响应，不出现周期性 404 或错误提示。

第一阶段不实现用户管理页、任务执行、发布审批、容器管理、可观测性查询、事件中心页面或 AIOps 聊天能力。AIOps 配置在第一阶段初始化为 `is_enabled=False`，使悬浮组件完成 bootstrap 后不继续加载会话；这属于部署数据状态，不改变启用后的业务逻辑。

## 3. 兼容性原则

- API 路径、HTTP 方法、请求参数、筛选规则、状态码和响应字段与旧后端一致。
- 数据模型名称、关键字段、状态枚举、外键删除策略和默认排序与旧后端一致。
- 权限编码、直接角色、用户组角色、超级管理员语义和权限拒绝消息保持一致。
- 不增加 `{code, data, message}` 响应包装；前端继续直接消费 DRF 响应。
- 旧后端测试先迁移为行为基线，再实现新代码。
- 只改变代码边界，不在迁移过程中修改业务规则。

## 4. 账号策略

- 不再提供用户名为 `demo` 的特殊演示账号，也不保留“拥有全部权限但禁止写操作”的账号特例。
- `admin` 是 Django 超级管理员，拥有全部已注册权限并允许执行写操作。
- `admin` 仅在环境变量 `SXDEVOPS_ADMIN_INITIAL_PASSWORD` 明确配置时自动创建；代码和仓库中不保存默认密码。
- `is_superuser` 的权限语义与旧系统一致：跳过普通角色授权检查，但仍需要通过身份认证和功能开关检查。
- 前端现有逻辑会把超级管理员视为拥有全部权限，因此 `admin` 会看到尚未完成的菜单。这是分阶段开发期间的已知界面状态，不能通过削弱超级管理员语义或篡改必选模块规则规避。
- 应用外壳登录后自动请求的接口必须在第一阶段全部实现；尚未完成的页面不纳入第一阶段可用性承诺。

## 5. 后端目录结构

```text
backend/
├── manage.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── common/
│   ├── exceptions.py
│   ├── pagination.py
│   ├── permissions.py
│   └── testing.py
├── rbac/
│   ├── models.py
│   ├── registry.py
│   ├── services.py
│   ├── selectors.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── aiops/
│   ├── models.py
│   ├── audit/
│   │   ├── selectors.py
│   │   └── traces.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── ops/
│   ├── models.py
│   ├── dashboard/
│   │   └── selectors.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
└── eventwall/
    ├── models.py
    └── services.py
```

视图只处理 HTTP 协议和序列化；应用服务负责事务和状态变化；selector 负责只读查询与聚合；后续外部系统统一通过 adapter 接入。

## 6. 第一阶段数据模型

### 6.1 RBAC

保留旧系统模型：

- `PermissionDefinition`：`code`、`name`、`category`、`description`、`sort_order`、`is_builtin` 和时间字段。
- `Role`：角色信息以及到权限、用户的多对多关联。
- `UserGroup`：用户组信息以及到角色、用户的多对多关联。
- `SystemModuleSetting`：`code`、`enabled`、`updated_by` 和时间字段。

有效权限由用户直接角色与用户组角色的并集构成。超级管理员获得所有已启用功能对应的权限。

### 6.2 AIOps 审计骨架

为保持旧聚合语义，第一阶段建立：

- `AIOpsModelProvider`
- `AIOpsChatSession`
- `AIOpsChatMessage`
- `AIOpsPendingAction`
- `AIOpsToolInvocation`
- `AIOpsModelInvocation`
- `AIOpsMCPServer`
- `AIOpsSkill`

Skill 和 Action 命中信息继续保存在助手消息的 `metadata` 中，由审计 trace reader 解析，不创建新的 SkillTrace 或 ActionTrace 数据表。

### 6.3 运行统计骨架

为保持 `/api/dashboard/stats/` 和顶部提醒的统计规则，建立该查询所需的 `Host`、`Deployment`、`TransactionTicket`、`Alert` 和 `AlertClaim` 模型。模型使用旧系统字段和状态枚举；第一阶段只开放顶部提醒需要的只读列表，不开放完整 CRUD API。

### 6.4 操作审计

建立 `EventRecord` 及统一 `record_event()` 服务。权限同步和模块设置修改继续产生与旧系统等价的审计事件。

## 7. 第一阶段接口

### 7.1 认证

- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`
- `POST /api/auth/sync/`

登录成功返回 DRF Token 和完整用户序列化结果。用户结果包含直接角色、用户组、有效权限、显示名称和超级管理员标志。用户名或密码错误返回 HTTP 400；禁用用户返回 HTTP 403。

### 7.2 模块设置

- `GET /api/module-settings/`
- `PUT /api/module-settings/`
- `PATCH /api/module-settings/`

模块目录、标题、描述、`required` 和排序沿用旧系统。必选模块始终保持启用。更新需要 `rbac.module.manage` 权限并写入操作审计。

### 7.3 运行统计

- `GET /api/dashboard/stats/`

返回主机数量和平均利用率、发布状态数量、告警状态数量、最近发布和最近未认领告警。查询需要 `ops.dashboard.view`。

### 7.4 AIOps 首页聚合

- `GET /api/aiops/admin/audit/overview/`
- `GET /api/aiops/admin/audit/costs/`
- 兼容无尾斜杠的 `/api/aiops/admin/audit/costs`

`overview` 返回当日会话、消息、动作、模型调用等统计，并提供 `invocation_distribution`：MCP 工具调用、Skill 命中和 Action 命中。

`costs` 支持 `days`、`range=all`、`start` 和 `end`。`days` 无效时默认 7，并限制在 1 至 90 天。聚合结果保留窗口信息、模型总调用、Token、费用、币种、平均延迟、Provider 分布、用途分布和工具分布。

### 7.5 应用外壳自动请求

由于 `admin` 拥有全部权限，登录后的应用外壳会自动请求以下接口，第一阶段必须提供真实的只读实现：

- `GET /api/deployments/?approval_status=pending`
- `GET /api/transaction-tickets/?status=pending`
- `GET /api/events/analysis_wall/?limit=80`
- `GET /api/aiops/bootstrap/`

前三个接口从对应数据表查询；空库时返回旧接口格式的空结果。`bootstrap` 保留旧响应结构，第一阶段因 Agent 配置未启用而返回 `enabled: false`，从而不会自动加载聊天会话。

## 8. 请求与错误处理

```text
Vue -> TokenAuthentication -> RBACPermission -> View/Serializer
    -> Application Service 或 Selector -> ORM -> EventRecord
```

- 参数验证错误返回 HTTP 400 和 DRF 字段错误字典或 `detail`。
- 未认证返回 HTTP 401。
- 缺少权限返回 HTTP 403；普通缺权消息包含权限编码。
- 资源不存在返回 HTTP 404。
- 未捕获异常返回安全的 HTTP 500 提示，详细堆栈进入结构化日志。
- 列表接口沿用旧接口是否分页的行为，不强制将所有列表改成统一分页。
- 时间以带时区的 ISO 8601 输出；数据库开启时区支持。
- 模型费用继续使用 `DecimalField`，不使用浮点数累计。

## 9. 配置与安全

- `base.py` 放置公共配置；开发和生产配置分离。
- 生产环境必须显式提供 `SECRET_KEY`、`ALLOWED_HOSTS` 和数据库凭据。
- 生产环境不允许默认全开 CORS。
- 本地默认 SQLite，生产支持 MySQL；测试使用隔离测试数据库。
- Token、密码、数据库文件、日志、缓存和构建产物不提交到 Git。

## 10. 测试策略

先迁移并适配旧系统中与第一阶段相关的测试，再开始实现：

1. 用户直接角色和用户组角色权限合并。
2. 普通用户访问授权接口成功、访问未授权接口返回 403。
3. 序列化输入不能修改 `is_superuser`、`is_staff` 或 `is_active`。
4. `admin` 超级管理员可以执行读写操作。
5. 不存在任何基于用户名 `demo` 的特殊授权或写操作拦截。
6. 登录成功、登录失败、禁用用户、Token 恢复和退出。
7. 必选模块不可关闭，模块更新产生事件记录。
8. 仪表盘空数据和有数据统计。
9. AIOps 成本统计、币种分组、时间范围和无尾斜杠兼容。
10. MCP、Skill 和 Action 调用分布解析。
11. 超级管理员登录后所有应用外壳自动请求均返回 200，且未启用的 AIOps 不继续请求会话。

测试层包括 service/selector 单元测试、DRF API 测试和一条浏览器冒烟路径：登录 -> 运行概览 -> 刷新 -> 退出。

## 11. 实施顺序

1. 初始化 Git、`.gitignore`、Django 工程和分层配置。
2. 建立测试框架并迁移第一阶段行为测试，确认其先失败。
3. 建立 RBAC、AIOps 审计、运行统计和 EventRecord 模型及迁移。
4. 实现内置权限注册、角色和用户组权限计算。
5. 实现认证、当前用户和权限同步接口。
6. 实现模块设置查询与修改。
7. 实现运行统计 selector 和接口。
8. 实现 AIOps 审计 trace reader、概览、成本 selector 和禁用状态 bootstrap。
9. 实现顶部提醒需要的发布、事务工单和事件只读查询。
10. 通过管理命令创建 `admin` 超级管理员；密码只从环境变量读取。
11. 运行后端测试、迁移检查、前端构建和浏览器冒烟测试。

## 12. 完成标准

- 现有前端不修改 API 调用即可连接新后端。
- `admin` 拥有全部权限并允许写操作。
- 登录、身份恢复、退出、RBAC、模块设置和运行概览行为与旧系统一致。
- 首页零数据和有数据两种状态均正常。
- 登录后的自动请求全部成功；尚未完成的页面允许保留菜单入口，但不属于第一阶段验收范围。
- 第一阶段自动化测试全部通过。
- Django 系统检查和迁移检查通过。
- 前端生产构建通过。
- 浏览器冒烟路径无控制台错误和失败请求。

## 13. 后续阶段

第一阶段完成后，按资源底座、任务工作台、工单系统、容器管理、告警与事件、可观测性、AIOps 的顺序逐页交付。每个页面均重复“提取旧行为合同 -> 编写失败测试 -> 分层实现 -> API 联调 -> 浏览器验收”的流程。
