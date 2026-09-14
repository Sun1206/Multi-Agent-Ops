# AI Ops FastAPI 后端

## 当前迁移范围

默认依赖和启动入口已切换为 FastAPI，不需要安装 Django。当前实现登录、退出、当前用户、权限同步、模块设置，以及用户、角色、用户组管理、权限字典、操作审计查询/清理、智能体配置、模型连接测试/目录探测和智能助手普通对话接口，共 58 个 HTTP 操作。复用 RBAC、管理员初始化、审计服务和现有 SQLAlchemy 表结构。

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

配置CRUD及目录声明本身不读取本地 Skill 文件、不启动 MCP 子进程、不调用外部模型。`runtime_ready` 仅表示提供商配置完整，不代表连接测试成功；模型诊断通过下述显式触发接口进行。MCP连接/发现和工具执行尚未接入，相关接口未注册。历史预设仅用于填表，不保证外部服务当前可用。

## 模型提供商连接测试及模型目录

两个接口都要求 `aiops.config.manage`，仅操作已保存且启用的 `openai_compatible` 提供商，继续使用Token认证和尾部斜线。先配置 Base URL、API Key、默认模型和私有 `.env` 加密密钥；网络准入变量沿用智能助手说明，HTTP/私网模型需精确origin授权。不会自动补 `/v1`、修改默认/备用模型或执行真实工具。

- `POST /api/aiops/admin/providers/{id}/test_connection/`：无需请求体。向 `/chat/completions` 提交固定短提示词，temperature=0、max_tokens=32；非空文本才算成功。成功200返回status/message/resolved_model，远端诊断失败400返回status=failed及安全message。诊断状态与审计一起提交，不公开供应商正文或原始异常。
- `GET /api/aiops/admin/providers/{id}/models/?probe=true`：返回models/count/recommendation/probe_candidates/probe_error/catalog_error/fallback_used。probe默认true兼容旧前端；false只请求 `/models`，不生成回答。目录失败可回退到配置中的默认/备用模型，明确fallback_used，回退目录不表示验证成功。

探测最多两个候选；每个候选至多一次文本和一次无副作用工具声明测试，整个接口最多一次目录及四次生成请求。工具声明需函数名/参数有效，且文本和工具返回的模型标识一致；不执行工具。文本验证通过但工具未验证时，推荐明确supports_tool_calling=false。响应上限1MiB，目录最多200项，模型ID最多128字符，整条链包括DNS共用提供商超时与90秒上限。不重试、不走环境代理、不跟随重定向，TLS及DNS地址固定规则与普通聊天一致。

无对象404、无权限403、无认证401、非法probe422；缺失/错误服务端加密密钥503，密文损坏、禁用/不完整配置或准入拒绝400且不改测试状态。探测期间提供商变更/删除返回409，不保存旧结果。为识别MySQL整秒精度下“修改后还原”，提供商配置更新至少推进一秒的updated_at标记；短时间连续修改时该标记可能略晚于墙钟。诊断保存不推进配置标记，实际诊断时间以审计为准；未变配置的并发诊断按完成顺序保存结果。该保护未新增表字段或修改历史迁移。

GET目录/探测也记录安全操作审计，但不保存测试状态或推荐模型。审计/提交失败回滚，不向页面假报成功；供应商已经发生的请求和费用无法回滚。用户点击测试或拉取模型默认会触发真实供应商请求，可能计费；本轮自动化验收仅模拟网络，未调用真实供应商、未写开发MySQL、未重置admin，真实浏览器和MySQL时间精度/锁行为仍待验收。启动命令不变。

本轮提供商专项30 passed，最终全回归240 passed/3 skipped；编译/依赖检查通过，OpenAPI58个HTTP操作，88个前端文件未变。目录远端失败且无回退时也记录安全失败审计。

## 智能助手迁移进度

已实现旧协议的 `/api/aiops/bootstrap/`、会话列表/创建/详情、完整消息数组查询，以及 DELETE 与 POST `delete_session/` 两个删除入口。要求 `aiops.chat.view`，所有会话按本人归属过滤（超级管理员也不例外）；创建201、删除204。旧 `page_context` 归一化、最新消息预览和消息轮询字段保持兼容。普通聊天基础接口不返回可执行工具或待执行动作。

现已接入 `POST sessions/{id}/send_message_async/`：201 返回用户消息及 pending 助手消息，后台独立数据库会话处理，页面沿用完整历史消息接口轮询 running/completed/failed。`send_message/` 同步入口复用同一业务核心。用户正文去除首尾空白后为1–4000字符；第一次发送以正文前48字符生成标题。没有可用模型时保留问题并保存 failed/error 消息，不会一直排队。

使用前在智能体配置中启用默认模型提供商、填写兼容 OpenAI Chat Completions 的 base_url（包含服务需要的 `/v1` 等路径）、模型名和 API Key，并设置前述私有加密密钥。后端请求 `{base_url}/chat/completions`，不自动补 `/v1`、切换备用模型或重试。当前只支持普通文本，不支持工具执行、MCP、平台资源查询或任务生成，不能据此认为旧智能助手全部业务已经迁移。

默认仅允许 HTTPS 公网443。HTTP、本地/私网模型和特殊端口必须由服务端在私有 `.env` 的 `AIOPS_MODEL_ALLOWED_INTERNAL_ORIGINS` 中精确授权，值为 JSON origin 数组，例如 `["http://localhost:11434"]`；环境变量优先，修改后重启。不要添加不可信服务；授权 HTTP 意味着凭据在该连接上没有 TLS 保护。链路本地/元数据地址始终拒绝；DNS全部答案检查后固定已验证IP并保留TLS主机名验证。禁用重定向、环境代理和自动重试，单次总预算最多90秒、响应最多1MiB且仅接受未压缩响应。

同会话提交及后台处理依次执行，独立会话可并发；最多32个已接纳任务，超限在消息写入前429。删除会话取消可取消的本地请求并禁止写回，不能保证远端已经开始的推理不计费。权限、账号或模型配置变化会拒绝过期回复；业务和安全审计一起提交。停止及重启只把本批带版本标记的未完成消息转为 failed，不自动重新调用模型。

部署必须保持单个应用进程：不要使用 `--workers 2`、多副本或同时启动多个后端访问同一数据库。当前任务和顺序控制在内存中，不是持久化/分布式队列。原本地单进程启动命令不变，不需要数据库迁移。前端未修改；本批只使用隔离SQLite和模拟网络验收，真实浏览器、本地MySQL对话写入和真实模型联调仍未验收。

本轮普通对话专项45 passed，全回归210 passed/3 skipped；编译与依赖检查通过，OpenAPI56个HTTP操作，88个前端文件SHA256保持一致。3项独立MySQL测试未启用。

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
