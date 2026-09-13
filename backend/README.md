# AI Ops FastAPI 后端

## 当前迁移范围

默认依赖和启动入口已切换为 FastAPI，不需要安装 Django。当前实现登录、退出、当前用户、权限同步、模块设置，以及用户、角色、用户组管理、权限字典、操作审计查询/清理、智能体配置和智能助手会话基础接口，共 54 个 HTTP 操作。复用 RBAC、管理员初始化、审计服务和现有 SQLAlchemy 表结构。

这不代表所有前端页面的业务接口都已实现；其他页面接口仍需按页面逐步接入。旧 Django 应用、入口、测试和模型生成脚本已移出本项目，后端仅保留 FastAPI 代码。

本地 MySQL 连接和迁移已验证。时间字段统一以 UTC 存储和输出。

## 本地准备

后端使用项目内虚拟环境，不依赖全局 Python 包：

```powershell
cd C:\Users\sunyupeng\PycharmProjects\AI-Ops\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填写本机 MySQL 账号和密码。当前开发数据库为 `localhost:3307` 的 `AIOps`，自动化测试数据库配置为独立的 `ai_ops_test`，不要把 `.env` 提交到 Git。已有 `.env` 时不要重复复制覆盖。

## 数据库初始化

AIOps 业务表使用单个 `aiops_` 前缀，例如 `aiops_modelprovider`。已有数据库通过 `0002_normalize_aiops_names` 重命名，保留数据；新库执行完整迁移链后得到相同表名。已经执行的初始迁移不得重新生成或修改。

确保 `.env` 指定的 MySQL 服务运行后执行（当前数据库已经初始化，无需重复创建）：

```powershell
.\.venv\Scripts\python.exe -m scripts.create_databases
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.bootstrap_data
```

只有显式配置 `AIOPS_ADMIN_INITIAL_PASSWORD` 才会创建或升级 `admin`。初始化成功后应从 `.env` 删除该变量，数据库只保留 Argon2id 哈希。

## 启动

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档地址为 `http://127.0.0.1:8000/docs`。

也可以运行 `powershell -ExecutionPolicy Bypass -File .\start.ps1`。该脚本只启动 FastAPI，不会自动启动 MySQL。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests_fastapi -q
```

离线服务测试使用内存 SQLite，不连接本机 MySQL；它不能替代 MySQL 的索引、外键和迁移集成验收。

## 用户管理接口

现有前端“系统管理 → 用户管理”的四个标签页使用以下接口；保持 `/api` 前缀、尾部斜线及 `Authorization: Token <token>` 认证。

- `/api/users/`：GET 分页查询，POST 创建；`/api/users/{id}/`：GET 详情、PATCH 更新、DELETE 删除。
- `/api/users/{id}/reset_password/`：POST 重置指定用户密码。
- `/api/roles/`、`/api/groups/`：GET 列表、POST 创建；对应 `/{id}/` 支持 GET、PATCH、DELETE。
- `/api/permissions/`：GET 权限字典。

用户查询支持 `search`、`page`、`page_size`；每页默认 20 条，最多 200 条。PATCH 未提交的字段保持原值，关系 ID 数组提交 `[]` 表示清空。新建或重置密码长度为 8–128 字符，不影响已有 admin 密码。

超级管理员拥有全部权限。普通管理员不能授予超出自身范围的权限、修改超级管理员或提升身份；内置角色/组不能删除或改代码，内置角色的可变字段仍由权限同步注册表维护。禁止删除当前账号，禁止停用、降级或删除最后一个启用的超级管理员。密码修改、重置和停用会撤销该用户所有令牌。写操作与审计事件在同一事务提交，日志不记录密码、哈希或令牌。

用户管理浏览器验证覆盖四个标签页读取；增删改查、关联修改和密码重置另通过 HTTP 验收，不代表所有弹窗交互已经逐项验收。首页统计和其他未接入业务页面的接口仍需继续实现。

## 操作审计接口

- `GET /api/events/operation_audit/`：要求 `rbac.audit.view`，返回 count/next/previous/results。支持 search、module、result、actor、start_at、end_at、page、page_size；默认 20 条、上限 200 条，按时间和 ID 倒序。时间范围包含边界，操作人按用户名精确匹配。
- `POST /api/events/prune_operation_audit/`：要求 `rbac.audit.manage`，只接受 JSON `{"before_at":"2025-01-01T00:00:00Z"}`，不接受查询参数。返回 deleted/before_at，严格删除截止时间之前的内部审计。该功能不可恢复，请通过页面的二次确认谨慎操作。

两个接口都排除 source_type=external、category=external_event 和 result=rejected 的记录，保持旧业务范围。日期必须是带时区的 ISO 8601 字符串，统一转换为 UTC；无时区、Unix 时间戳、颠倒范围或未来清理截止时间返回 422。查询响应不返回 detail、metadata、changes 等潜在敏感载荷。

清理与新增清理日志在同一事务提交，任一失败则回滚；保留未删除子事件，并按已有外键将 parent_event_id 置空。现有 MySQL 时间字段仅保留整秒，清理日志发生时间上取到下一整秒（最多晚不到 1 秒），避免相同小数秒截止时间重复清理掉刚生成的日志。页面顶部成功/失败等分类数量仍是当前页统计，不是全局统计。

操作审计验收包含隔离 SQLite HTTP 查询/清理、删除边界、权限和失败回滚，以及真实开发 MySQL 查询的只读检查。没有调用开发库清理接口、创建认证令牌或删除现有审计数据；真实 MySQL 清理事务及浏览器弹窗未验收。不需要新增数据库迁移，原启动命令不变。

## 智能体配置（第一批）

接口统一位于 `/api/aiops/admin/`，读取要求 `aiops.config.view`，变更要求 `aiops.config.manage`；超级管理员拥有全部权限。

- `config/`：GET 读取默认策略，PUT 局部更新；未提交字段保持原值，数组 `[]` 清空，默认提供商 `null` 清空。执行确认必须保持开启。
- `providers/`、`mcp-servers/`、`skills/`：GET 列表、POST 创建，对应 `/{id}/` 支持 GET、PATCH、DELETE。删除会在同一事务清理策略引用。
- `providers/presets/`、`skills/marketplace/`、`actions/`：GET 读取历史预设、Skill 目录和 Action 声明；`skills/{id}/clone/`：POST 克隆为团队 Skill。

GET 不初始化数据库。需要补充默认策略、13 个内置 Skill 和禁用的内置 MCP 声明时，手动执行以下幂等命令；不会覆盖已有内容或重置 admin：

```powershell
.\.venv\Scripts\python.exe -m scripts.bootstrap_agent_config
```

保存模型 API Key 或 MCP 鉴权前，先在本机生成专用密钥：

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将结果填入私有 `.env` 的 `AIOPS_CONFIG_ENCRYPTION_KEY` 并重启后端。密钥需安全备份，不要提交 Git，也不要随意替换；替换后旧凭据无法解密。缺失/无效密钥时，敏感写入返回 503，普通配置仍可读写。响应和审计不返回凭据；API Key 未提交表示保留，空串表示清除。MCP 的 `headers`/`env` 和识别出的敏感字段加密存储，页面 `***` 只能保留原路径凭据，`auth_config={}` 清空。

本批只管理配置与能力声明，不读取本地 Skill 文件、不启动 MCP 子进程、不调用外部模型。`runtime_ready` 仅表示提供商配置完整，不代表连接测试成功；真实模型测试、MCP 连接/发现和智能体执行尚未接入，相关接口未注册。历史预设仅用于填表，不保证外部服务当前可用。

## 智能助手迁移进度

已实现旧协议的 `/api/aiops/bootstrap/`、会话列表/创建/详情、完整消息数组查询，以及 DELETE 与 POST `delete_session/` 两个删除入口。要求 `aiops.chat.view`，所有会话按本人归属过滤（超级管理员也不例外）；创建201、删除204。旧 `page_context` 归一化、最新消息预览和消息轮询字段保持兼容。普通聊天基础接口不返回可执行工具或待执行动作。

这是基础阶段，不代表聊天已可用。`send_message/`、`send_message_async/`、后台处理与真实模型回复尚未注册/实现；前端发送目前仍会404。页面初始化与历史管理接口已实现，不修改任何前端文件；真实浏览器、本地MySQL写入和模型联调未验收。本批专项9项测试，全回归165 passed/3 skipped，编译与依赖检查通过。

## 独立 MySQL 测试

并发锁和 MySQL 事务测试需单独的 `ai_ops_test` 测试库。当前账号访问该库返回 MySQL 1044，相关测试会跳过；没有自动创建测试库或扩大账号权限，也没有在开发库运行并发管理员保护测试。

由数据库管理员准备独立测试库、授权并应用迁移后，可显式运行：

```powershell
$env:AIOPS_RUN_MYSQL_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests_fastapi/integration/test_mysql_rbac.py -q
Remove-Item Env:AIOPS_RUN_MYSQL_TESTS
```

测试会核实库名以 `_test` 结尾且不同于开发库，只清理自己创建的临时对象，不删除已有表或开发数据。当前开发 MySQL 已通过临时用户/角色/组的 HTTP 增删改查、密码重置和令牌撤销验收；临时对象已清理，审计记录保留。

FastAPI 是唯一运行入口，不需要安装 Django。SQLAlchemy 模型直接维护；字段或表结构变更应新增 Alembic 迁移，不修改已经应用的历史版本。历史设计文档仅用于记录迁移过程，不作为当前启动说明。
