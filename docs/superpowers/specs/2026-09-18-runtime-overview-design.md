# 运行概览后端设计

## 目标

保持现有 `Dashboard.vue` 页面、交互和 API 调用不变，补齐真实数据库聚合接口，并从功能上线后的新模型调用开始记录准确的运行数据。历史消息不反推 Token、耗时或费用，不生成估算数据。

## 范围

- 实现 `GET /api/aiops/admin/audit/overview/`。
- 实现 `GET /api/aiops/admin/audit/costs/`。
- 为智能助手的新模型调用写入 `aiops_modelinvocation`。
- 从现有 `aiops_toolinvocation` 和消息运行元数据聚合工具、Skill 与 Action 命中。
- 沿用 `aiops.audit.view` 权限。
- 不修改前端页面，不新增数据库表，不补历史统计。

## 统计时间范围

两个接口使用完全相同的时间过滤规则：

- `days`：最近 N 天，默认 7 天，允许 1 至 365 天。
- `start` 与 `end`：必须同时提供 ISO 8601 时间，`start` 必须早于 `end`，最大跨度 365 天。
- `range=all`：查询全部历史记录。
- 参数互斥；无效或冲突参数返回 422。
- 所有时间在服务端归一化为 UTC，并使用记录的 `created_at` 过滤。

## 接口设计

### 运行分布接口

`GET /api/aiops/admin/audit/overview/` 返回：

- `invocation_distribution.mcp_tools`：按工具名称聚合调用次数。
- `invocation_distribution.skills`：按 Skill 标识和显示名聚合命中次数。
- `invocation_distribution.actions`：按 Action code 和显示名聚合命中次数。
- 每项统一包含 `key`、`label`、`count`，按调用次数倒序、标识正序排列。
- 无数据时返回空数组，不返回演示数据。

工具调用以 `aiops_toolinvocation` 为权威来源。Skill 与 Action 使用助手消息中已经落库的安全运行元数据；不存在相应元数据时返回空数组，不从文本内容猜测。

### 成本接口

`GET /api/aiops/admin/audit/costs/` 返回：

- `model.total_calls`：时间范围内成功和失败模型调用总数。
- `model.total_tokens`：远端明确返回的 Token 总数。
- `model.estimated_cost_usd`：为兼容现有前端保留的费用汇总字段；仅在单币种结果中表示该币种金额，多币种时为 0。
- `model.cost_currency`：单币种时的币种，多币种时为空字符串。
- `model.avg_latency_ms`：所有已完成调用的平均耗时。
- `model.by_currency`：按 `USD`、`CNY` 分开的费用汇总。
- `model.by_provider`：按提供商和币种分组的调用次数、Token、费用和平均耗时。
- `tools`：工具调用总数、平均耗时及 `by_tool` 排名，供现有前端兜底使用。

聚合只读取运行记录，不触发模型请求，不修改业务数据。Decimal 金额在响应中转为普通数值，按数据库六位小数精度输出。

## 模型调用记录

智能助手发起 Chat Completions 时保留完整 JSON 响应到内存，提取并校验以下安全字段：

- 请求模型与响应中的实际模型。
- `usage.prompt_tokens`、`usage.completion_tokens`、`usage.total_tokens`。
- 调用成功或失败状态及耗时。
- 提供商 ID、会话 ID、助手消息 ID、用户名和用途。

不把提示词、回答正文、API Key 或远端原始错误写入运行记录。请求与响应摘要只保存长度、消息数量、是否返回 usage 等非敏感信息。

费用使用调用开始时的提供商价格快照计算：

`输入费用 = prompt_tokens × input_token_price_per_1m / 1,000,000`

`输出费用 = completion_tokens × output_token_price_per_1m / 1,000,000`

远端未返回 usage 或字段不合法时 Token 与费用记为 0，不估算。失败调用仍记录状态和耗时；仅保存远端已经安全解析出的 usage。

## 数据一致性与错误处理

- 模型调用记录与助手消息终态在同一个数据库事务中提交，防止页面显示成功但运行记录缺失。
- 如果调用在发送请求前失败且无法确定提供商，不创建伪造的模型调用记录。
- 如果远端请求已经开始，成功时写入 `success`；远端失败或任务取消时写入 `failed`，并在安全摘要中以 `failure` 或 `cancelled` 区分终止原因。
- 统计接口是只读接口，不写操作审计，避免每次刷新反向污染统计。
- 聚合查询失败使用现有统一异常处理，不回显 SQL、远端响应或凭据。

## 代码边界

- `aiops/api/audit.py`：路由、权限和查询参数契约。
- `aiops/schemas/audit.py`：时间范围和响应结构。
- `aiops/selectors/audit.py`：只读聚合查询及安全序列化。
- `aiops/services/model_invocations.py`：usage 归一化、价格计算和运行记录构造。
- `aiops/services/chat_jobs.py`：在现有模型请求生命周期中调用记录服务。
- `aidevops/routes.py`：注册审计路由。

## 测试

- 空数据库返回稳定空结构。
- `days`、自定义起止时间和全部时间过滤正确。
- 冲突、缺失、倒置或超范围时间参数返回 422。
- 未授权、缺少 `aiops.audit.view` 和已停用账号分别返回 401 或 403。
- 模型统计覆盖成功、失败、不同提供商、不同币种、零 usage 和平均耗时。
- 工具、Skill、Action 分布只统计真实结构化记录，不解析自然语言。
- 聊天成功、失败和取消均验证安全调用记录及事务一致性。
- 全量后端测试和前端生产构建必须通过。
