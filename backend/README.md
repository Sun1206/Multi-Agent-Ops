# AI Ops FastAPI 后端

## 当前迁移范围

默认依赖和启动入口已切换为 FastAPI，不需要安装 Django。当前实现登录、退出、当前用户、权限同步、模块设置，以及用户、角色、用户组管理和权限字典，共 24 个 HTTP 操作。复用 RBAC、管理员初始化、审计服务和现有 SQLAlchemy 表结构。

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

本期不包含操作审计列表、首页统计和其他业务页面的接口。浏览器验证覆盖四个标签页读取；增删改查、关联修改和密码重置另通过 HTTP 验收，不代表所有弹窗交互已经逐项验收。

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
