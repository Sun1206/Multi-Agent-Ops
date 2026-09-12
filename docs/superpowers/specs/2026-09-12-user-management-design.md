# 用户管理 FastAPI 接口设计

日期：2026-09-12
项目：C:\Users\sunyupeng\PycharmProjects\AI-Ops
状态：实施范围与具体设计已批准；代码已实现，独立 MySQL 并发验收待测试库授权。

## 目标与边界

完成现有 Users.vue 的用户、角色、用户组、权限四个标签页，保留 Vue 页面、/api 前缀、尾部斜线和 Authorization: Token 认证协议。复用当前 MySQL 表结构，不新增数据库迁移，不修改现有 admin 密码，不引入 Django。

本期记录用户管理写操作的审计事件，但不实现 OperationAudit.vue 的查询或清理接口。首页 AIOps 统计、主机、任务、发布、SQL 执行及其他页面不属于本期。

## 方案选择

采用按页面闭环实施：契约、读取、写入、授权、审计和测试一起交付。按技术层全面重构容易留下不可验收的半成品；一次实现所有页面风险及范围过大。现有核心结构保持不动，仅提取账号序列化等确有重复的逻辑。

## HTTP 契约

- GET/POST /api/users/：用户列表及创建。GET /api/users/{id}/：用户详情。PATCH /api/users/{id}/：部分更新。DELETE /api/users/{id}/：删除。POST /api/users/{id}/reset_password/：重置密码。
- GET/POST /api/roles/ 和 GET/PATCH/DELETE /api/roles/{id}/：角色管理。
- GET/POST /api/groups/ 和 GET/PATCH/DELETE /api/groups/{id}/：用户组管理。
- GET /api/permissions/：只读权限字典。
- 继续复用现有 /api/auth/sync/、登录和模块接口。

用户列表返回 {count, next, previous, results}；默认每页 20，page 从 1 开始，page_size 最大 200，999 按 200 截断，与旧分页上限一致。空库第一页合法；不存在的后续页返回 404。按 id 稳定排序。search 匹配用户名和邮箱，不将用户输入拼成 SQL。

角色、用户组、权限列表返回数组，不包分页对象。角色和组 search 匹配 code/name/description；权限 search 匹配 code/name/category/description。读取不自动同步或创建数据。

创建成功 201；读取及更新 200；删除成功 204 空响应；密码重置成功 200 {success:true}。未认证 401、无权限 403、不存在 404、业务规则不满足 400、唯一约束冲突 409、请求格式错误 422。错误正文沿用可读 detail，不泄露 SQL 或输入凭据。

## 输入与输出

用户输入：username、email、first_name、last_name、password、is_active、is_staff、is_superuser、role_ids、group_ids。创建必须提供非空密码；PATCH 未提交字段保持原值。编辑时不提供 password 则保持原密码，明确提交空字符串则拒绝。关系数组缺省保持原值，[] 表示清空。关系 ID 验证全部存在并去重，非法 ID 使整个写入失败。

用户输出复用现有 UserResponse，包括 roles、user_groups、effective_permissions、display_name 和恒为 false 的 is_demo_account；不输出密码或哈希。用户组内成员返回 id/username/display_name 的精简信息。角色输出 id/code/name/description/is_builtin/permissions，以及创建和更新时间；权限嵌套对象与字典字段一致。组输出 id/code/name/description/is_builtin/roles/users 及时间。数量字段如 users_count/permissions_count/roles_count 从关系计算，不另建列。所有时间带 UTC 时区。

用户名长度 1–150，姓名字段和邮箱长度沿用现有模型；code/name 长度不超过 64，description 不超过 255。用户名、code、name 禁止纯空白并修剪首尾空白；密码不修剪，长度 8–128，用 Argon2id 哈希。现有 bootstrap 的显式开发密码初始化不受新管理接口的密码策略影响。

## 授权与保护规则

各资源读取需要 rbac.user.view、rbac.role.view、rbac.group.view、rbac.permission.view；写入分别需要 rbac.user.manage、rbac.role.manage、rbac.group.manage。超级管理员直接通过。

只有超级管理员能够实际变更 is_staff/is_superuser；非超级管理员可创建普通账号、管理普通账号启停，但不能修改或重置超级管理员，也不能删除超级管理员。非超级管理员提交与当前值相同的身份标记允许通过，以兼容前端完整表单；提交升级身份标记则返回 403。

非超级管理员不能通过角色、组或成员关系授予超出自身有效权限的权限。需要同时检查当前对象权限及目标关系权限，覆盖直属角色和组角色的传递授权；管理高权限角色/组同样被拒绝。服务端每次请求读取当前授权，不依赖前端缓存。

至少保留一个启用的超级管理员。删除、禁用、降级超级管理员前，按稳定顺序锁定全部超级管理员账号并基于锁定后的当前值检查，以防并发请求同时移除最后可用管理员。任何账号不得删除自己；允许在存在另一启用超级管理员时调整自己的启用或超级管理员状态。

内置角色/组不允许删除或改 code，不接受客户端修改 is_builtin。角色其他字段及权限允许超级管理员编辑；内置角色后续执行权限同步或登录触发同步时，以注册表定义为准，会恢复定义字段及权限，本期不改变这一现有行为。

修改密码或禁用账号时撤销该账号的全部令牌。删除用户使用已有外键级联清理 RBAC 关系和令牌，不清理历史审计事件。角色和组删除使用关系表级联解除绑定。修改角色、组及关系后，后续请求立即按数据库重新计算权限，不自动重置用户密码。

## 代码结构与事务

schemas/rbac.py 定义输入输出；selectors/users.py、selectors/rbac.py 负责批量关系加载、过滤、分页及详情；services/users.py、services/role_management.py、services/group_management.py 负责写入；services/rbac_policy.py 集中授权边界与管理员保护；api/routers/users.py、roles.py、groups.py、permissions.py 声明 HTTP 契约和权限。

现有 services/rbac.py 保持内置目录同步职责。共享账号响应构造从 auth 路由提取到专用序列化模块，登录和用户列表共同使用，避免服务导入路由。列表查询批量加载关联及权限，避免每个用户额外查询一次权限。

路由使用请求依赖提供的同一个会话，业务变更、令牌撤销、脱敏审计和提交组成一个事务；服务仅 flush，不自行 commit。依赖认证查询已经开启事务，因此不在路由盲目嵌套 session.begin()。任何异常回滚所有业务和审计写入。Pydantic 使用明确字段，拒绝客户端越权写入只读字段。

审计记录操作者、动作、资源 ID、请求路径/IP/关联 ID、修改字段及关系 ID，不记录原始密码、哈希、令牌或整个未经筛选的请求正文。复用 record_event 脱敏服务。

所有新增公共接口和方法带中文用途注释。现有已应用的 Alembic 0001/0002 不改动。

## 验收

先写失败测试，再实现。保留现有 54 项回归；新增前端契约、分页/搜索、CRUD、关系替换和去重、无效 ID 回滚、唯一冲突、权限缺失与传递提权、最后管理员保护、内置对象保护、密码和令牌撤销、审计失败回滚及脱敏测试。

离线使用内存 SQLite；SQLite 不作为 MySQL 行锁或级联行为的充分证据。真实 MySQL 集成测试仅访问独立 ai_ops_test，且测试开关显式启用；确认测试账号具有该库权限后，在测试库验证外键、唯一约束、事务及两会话并发最后管理员保护，不在 AIOps 开发库清空表或进行管理员保护破坏性试验。无测试库权限时报告该项未验收，不伪称通过。

浏览器验证用户页四标签、新建普通账号、分配角色和组、编辑、密码重置及删除；测试账号使用唯一前缀，禁止修改现有 admin 密码或删除既有用户。若需写入开发库验收，实施时明确说明并限定测试对象。前端构建和后端启动验证通过后，报告实际完成接口及仍未覆盖的其他页面。

## 当前确认事项

本设计新增密码最少 8 位、非超级管理员传递授权上限和最后管理员保护；属于有意增强，而不是宣称原 Django 逻辑完全相同。待用户确认这些规则后编写实施计划。项目尚无 Git 初始提交且此前索引写入受本地 ACL 限制；本设计保存为文件，不宣称已提交。
