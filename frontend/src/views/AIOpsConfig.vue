<template>
  <div class="fade-in aiops-config-page">
    <section class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon"><el-icon><ChatDotSquare /></el-icon></span>
          <h2>智能体配置</h2>
          <p class="page-inline-desc">统一管理智能助手的策略、Action、Skill、MCP 与模型提供商。</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" :loading="loading.page" @click="loadAll">刷新</el-button>
      </div>
    </section>

    <section class="tabs-card">
      <el-tabs v-model="activeTab" class="event-like-tabs">
        <el-tab-pane name="strategy">
          <template #label>
            <span class="tab-label"><el-icon><Setting /></el-icon>智能体策略</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="actions">
          <template #label>
            <span class="tab-label"><el-icon><Promotion /></el-icon>Action</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="skills">
          <template #label>
            <span class="tab-label"><el-icon><Tools /></el-icon>Skill</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="mcp">
          <template #label>
            <span class="tab-label"><el-icon><Connection /></el-icon>MCP</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="orchestration">
          <template #label>
            <span class="tab-label"><el-icon><Message /></el-icon>拓展功能-待实现</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="providers">
          <template #label>
            <span class="tab-label"><el-icon><Cpu /></el-icon>模型提供商</span>
          </template>
        </el-tab-pane>
      </el-tabs>
    </section>

    <section class="panel">
      <template v-if="activeTab === 'strategy'">
        <div class="section-toolbar strategy-actions">
          <div class="toolbar-head">
            <span class="toolbar-title">智能体策略</span>
            <span class="toolbar-desc">统一配置默认模型、欢迎语与运行安全开关</span>
          </div>
          <el-button size="small" type="primary" :loading="saving.config" @click="saveConfig">保存策略</el-button>
        </div>
        <div class="config-grid">
          <div class="config-section config-section--main surface-card">
            <div class="section-title">基础策略</div>
            <el-form :model="configForm" label-width="118px">
              <el-form-item label="默认提供商">
                <el-select v-model="configForm.default_provider_id" clearable style="width:100%">
                  <el-option
                    v-for="provider in providers"
                    :key="provider.id"
                    :label="providerOptionLabel(provider)"
                    :value="provider.id"
                    :disabled="!provider.runtime_ready"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="欢迎语">
                <el-input v-model="configForm.welcome_message" />
              </el-form-item>
              <el-form-item label="建议问题">
                <el-select v-model="configForm.suggested_questions" multiple filterable allow-create default-first-option style="width:100%" />
              </el-form-item>
              <el-form-item label="启用 MCP">
                <el-select v-model="configForm.enabled_mcp_server_ids" multiple collapse-tags collapse-tags-tooltip style="width:100%">
                  <el-option v-for="item in mcpServers" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="启用 Skill">
                <el-select v-model="configForm.enabled_skill_ids" multiple collapse-tags collapse-tags-tooltip style="width:100%">
                  <el-option v-for="item in skills" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="系统提示语">
                <el-input v-model="configForm.system_prompt" type="textarea" :rows="8" />
              </el-form-item>
            </el-form>
          </div>
          <div class="config-section config-section--runtime surface-card">
            <div class="section-title">运行生效项</div>
            <div class="runtime-note">这些配置会被聊天入口或后端任务生成逻辑直接读取。</div>
            <div class="switch-list">
              <div class="switch-item">
                <div class="switch-copy">
                  <span>启用智能助手</span>
                  <small>关闭后聊天入口不可用，已有会话仍保留。</small>
                </div>
                <el-switch v-model="configForm.is_enabled" />
              </div>
              <div class="switch-item">
                <div class="switch-copy">
                  <span>允许生成待执行任务</span>
                  <small>关闭后只返回分析结果，不创建待确认任务。</small>
                </div>
                <el-switch v-model="configForm.allow_action_execution" />
              </div>
            </div>
            <el-form :model="configForm" label-width="126px" class="runtime-form">
              <el-form-item label="模型上下文消息数">
                <el-input-number v-model="configForm.max_history_messages" :min="4" :max="40" />
                <div class="runtime-field-tip">仅限制每次发送给模型的最近用户/助手消息数，不影响会话历史展示。</div>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'orchestration'">
        <div class="skill-summary-row">
          <div class="skill-summary-item">
            <span>协同任务</span>
            <strong>{{ a2aOverview.total }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>待处理任务</span>
            <strong>{{ a2aOverview.queued }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>Runbook 手册</span>
            <strong>{{ runbookOverview.total }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>复盘知识</span>
            <strong>{{ reviewOverview.total }}</strong>
          </div>
        </div>
        <div v-if="canViewMcpServer" class="mcp-server-panel">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">AI Ops 对外 MCP Server</span>
              <span class="toolbar-desc">外部 Agent 通过 Token 鉴权调用平台只读工具，所有调用进入审计</span>
            </div>
          </div>
          <el-table :data="platformMcpManifest.tools || []" stripe size="small" class="console-table">
            <el-table-column prop="title" label="工具" min-width="180" show-overflow-tooltip />
            <el-table-column prop="name" label="MCP 名称" min-width="230" show-overflow-tooltip />
            <el-table-column prop="permission" label="权限" min-width="160" />
            <el-table-column label="状态" width="96">
              <template #default="{ row }">
                <el-tag size="small" :type="row.available === false ? 'warning' : 'success'">{{ row.available === false ? '受限' : '可用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="安全" width="96">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="row.annotations?.readOnlyHint ? 'success' : 'danger'">
                  {{ row.annotations?.readOnlyHint ? '只读' : '写入' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="audit-section">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">外部协同任务</span>
              <span class="toolbar-desc">接收其他系统或 Agent 提交的任务草案，平台确认后再执行</span>
            </div>
            <el-button v-if="canInvokeA2A" size="small" type="primary" @click="openA2ADialog">创建任务草案</el-button>
          </div>
          <el-table :data="a2aTasks" stripe size="small" class="console-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="json-preview">{{ formatJsonCompact({ input_payload: row.input_payload, plan_steps: row.plan_steps, orchestration_state: row.orchestration_state, agent_results: row.agent_results, react_trace: row.react_trace, result_payload: row.result_payload }) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="任务标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="source_agent" label="来源" width="130" />
            <el-table-column prop="action_code" label="Action" min-width="160" />
            <el-table-column prop="agent_mode" label="模式" width="110" />
            <el-table-column prop="status_display" label="状态" width="110" />
            <el-table-column prop="created_at" label="创建时间" min-width="170" />
            <el-table-column v-if="canInvokeA2A" label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <div class="table-actions">
                  <el-button link type="primary" :disabled="row.status !== 'queued'" @click="handleRunA2ATask(row)">运行</el-button>
                  <el-button link type="warning" :disabled="['completed', 'canceled'].includes(row.status)" @click="handleInterruptA2ATask(row)">中断</el-button>
                  <el-button link :disabled="['completed', 'canceled'].includes(row.status)" @click="handleCancelA2ATask(row)">取消</el-button>
                  <el-button v-if="canManageReviewKnowledge" link type="success" @click="handleAutoIngestReviewKnowledge(row, 'task')">沉淀</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-row">
            <el-pagination
              v-model:current-page="a2aPagination.page"
              :page-size="a2aPagination.pageSize"
              :total="a2aPagination.total"
              layout="total, prev, pager, next"
              @current-change="loadA2ATasks"
            />
          </div>
        </div>
        <div class="audit-section">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">Runbook 手册</span>
              <span class="toolbar-desc">把排障步骤、证据和复盘结论保存成可复用手册</span>
            </div>
            <el-button v-if="canManageRunbook" size="small" type="primary" @click="openRunbookDialog">生成手册草案</el-button>
          </div>
          <el-table :data="runbooks" stripe size="small" class="console-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="json-preview">{{ formatJsonCompact({ content: row.content || '暂无内容', evidence: row.evidence, source_refs: row.source_refs }) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="environment" label="环境" width="130" />
            <el-table-column prop="service" label="服务" width="150" />
            <el-table-column prop="version" label="版本" width="76" />
            <el-table-column prop="status_display" label="状态" width="100" />
            <el-table-column prop="updated_at" label="更新时间" min-width="170" />
            <el-table-column label="操作" width="270" fixed="right">
              <template #default="{ row }">
                <div class="table-actions">
                  <el-button link @click="handleViewRunbookVersions(row)">版本</el-button>
                  <el-button v-if="canManageRunbook" link type="primary" :disabled="row.status === 'published'" @click="handlePublishRunbook(row)">发布</el-button>
                  <el-button v-if="canManageRunbook" link type="warning" :disabled="row.status === 'archived'" @click="handleArchiveRunbook(row)">归档</el-button>
                  <el-button v-if="canManageReviewKnowledge" link type="success" @click="handleAutoIngestReviewKnowledge(row, 'runbook')">沉淀</el-button>
                  <el-button v-if="canManageRunbook" link type="danger" @click="handleDeleteRunbook(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-row">
            <el-pagination
              v-model:current-page="runbookPagination.page"
              :page-size="runbookPagination.pageSize"
              :total="runbookPagination.total"
              layout="total, prev, pager, next"
              @current-change="loadRunbooks"
            />
          </div>
        </div>
        <div class="audit-section">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">复盘知识</span>
              <span class="toolbar-desc">自动关联会话、协同任务、Runbook 和证据，形成可检索知识</span>
            </div>
          </div>
          <el-table :data="reviewKnowledge" stripe size="small" class="console-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="json-preview">{{ formatJsonCompact({ summary: row.summary, evidence: row.evidence, source_refs: row.source_refs }) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="environment" label="环境" width="130" />
            <el-table-column prop="service" label="服务" width="150" />
            <el-table-column prop="source_type_display" label="来源" width="110" />
            <el-table-column prop="updated_at" label="更新时间" min-width="170" />
            <el-table-column v-if="canManageReviewKnowledge" label="操作" width="92" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="handleDeleteReviewKnowledge(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-row">
            <el-pagination
              v-model:current-page="reviewPagination.page"
              :page-size="reviewPagination.pageSize"
              :total="reviewPagination.total"
              layout="total, prev, pager, next"
              @current-change="loadReviewKnowledge"
            />
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'providers'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">模型供应商</span>
            <span class="toolbar-desc">
              管理外部 LLM 接入配置与默认模型。
              <strong class="provider-strategy-reminder">模型供应商保存并测试通过后，请到智能体策略中选择默认供应商，智能助手才会使用该模型。</strong>
            </span>
          </div>
          <el-button size="small" type="primary" @click="openProviderDialog()">新增提供商</el-button>
        </div>
        <el-table :data="providers" stripe class="console-table">
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column label="类型" width="150">
            <template #default="{ row }">{{ formatProviderType(row.provider_type) }}</template>
          </el-table-column>
          <el-table-column prop="base_url" label="Base URL" min-width="220" show-overflow-tooltip />
          <el-table-column prop="default_model" label="默认模型" width="160" />
          <el-table-column label="计费" width="96">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ formatProviderCurrency(row.price_currency) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可用性" width="96">
            <template #default="{ row }">
              <el-tooltip :content="providerRuntimeHint(row)" placement="top" :disabled="row.runtime_ready">
                <el-tag size="small" :type="providerRuntimeTagType(row)">{{ providerRuntimeLabel(row) }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button link type="primary" @click="openProviderDialog(row)">编辑</el-button>
                <el-button link type="success" @click="handleTestProvider(row)">测试</el-button>
                <el-button link type="danger" @click="handleDeleteProvider(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'mcp'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">外部 MCP 接入</span>
            <span class="toolbar-desc">管理平台内置与外部 MCP 的接入、鉴权和运行边界</span>
          </div>
          <el-button size="small" type="primary" @click="openMcpDialog()">新增 MCP</el-button>
        </div>
        <el-table :data="mcpServers" stripe class="console-table">
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :class="['type-tag', `type-tag--${row.server_type || 'http'}`]">
                {{ formatMcpType(row.server_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="endpoint_or_command" label="地址或命令" min-width="240" show-overflow-tooltip />
          <el-table-column label="启用工具" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ formatEnabledTools(row.tool_whitelist) }}</template>
          </el-table-column>
          <el-table-column label="运行保护" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="mcpRuntimeMode(row).type">{{ mcpRuntimeMode(row).label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="248" fixed="right">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button link type="primary" @click="openMcpDialog(row)">编辑</el-button>
                <el-button link type="success" @click="handleTestMcp(row)">测试</el-button>
                <el-button link @click="handleListMcpTools(row)">工具</el-button>
                <el-button link type="danger" :disabled="row.is_builtin" @click="handleDeleteMcp(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'skills'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">Skill 能力包</span>
            <span class="toolbar-desc">Skill = 能力包，用于声明专业方法和工具依赖，最终可用工具仍会经过 MCP 可用性、用户 RBAC 和 Action 安全策略过滤</span>
          </div>
          <div class="toolbar-actions">
            <el-button size="small" @click="openSkillMarketDialog">Skill 市场</el-button>
            <el-button size="small" type="primary" @click="openSkillDialog()">新增 Skill</el-button>
          </div>
        </div>
        <div class="skill-summary-row">
          <div class="skill-summary-item">
            <span>能力包</span>
            <strong>{{ skillOverview.total }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>内置</span>
            <strong>{{ skillOverview.builtin }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>自定义</span>
            <strong>{{ skillOverview.custom }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>启用</span>
            <strong>{{ skillOverview.enabled }}</strong>
          </div>
        </div>
        <div class="skill-library">
          <div v-for="group in skillGroups" :key="group.category" class="skill-group">
            <div class="skill-group-head">
              <div class="toolbar-head">
                <span class="skill-group-title">{{ group.category }}</span>
                <span class="toolbar-desc">{{ group.items.length }} 个 Skill</span>
              </div>
            </div>
            <div class="skill-package-list">
              <div v-for="skill in group.items" :key="skill.id || skill.slug" class="skill-package-row">
                <div class="skill-package-main">
                  <div class="skill-package-title-row">
                    <span class="skill-package-name">{{ skill.name }}</span>
                    <el-tag size="small" effect="plain" :class="['type-tag', `type-tag--${getSkillTypeClass(skill)}`]">
                      {{ formatSkillType(skill) }}
                    </el-tag>
                    <el-tag size="small" :type="skillRiskTagType(skill.risk_level)" effect="plain">
                      能力风险：{{ formatSkillRiskLabel(skill.risk_level) }}
                    </el-tag>
                    <el-tag size="small" :type="skill.is_enabled ? 'success' : 'info'" effect="plain">
                      {{ skill.is_enabled ? '启用' : '停用' }}
                    </el-tag>
                  </div>
                  <div class="skill-package-desc">{{ skill.description || '暂无描述' }}</div>
                  <div class="skill-package-tags">
                    <el-tag v-for="action in skill.applicable_actions || []" :key="`${skill.slug}-${action}`" size="small" effect="plain">
                      适用：{{ formatActionName(action) }}
                    </el-tag>
                    <span v-if="!(skill.applicable_actions || []).length" class="muted-text">未绑定 Action</span>
                  </div>
                </div>
                <div class="skill-package-side">
                  <button type="button" class="skill-package-stat stat-detail-button" @click="openSkillStatDetail(skill, 'tools')">
                    <span>工具依赖</span>
                    <strong>{{ skillRecommendedToolCount(skill) }}</strong>
                  </button>
                  <button type="button" class="skill-package-stat stat-detail-button" @click="openSkillStatDetail(skill, 'scenes')">
                    <span>场景</span>
                    <strong>{{ (skill.examples || []).length }}</strong>
                  </button>
                  <div class="table-actions">
                    <el-button link type="primary" @click="openSkillDialog(skill)">编辑</el-button>
                    <el-button link type="danger" :disabled="skill.is_builtin" @click="handleDeleteSkill(skill)">删除</el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'actions'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">Action Registry</span>
            <span class="toolbar-desc">Action = 任务入口，用于把用户问题路由到任务类型，并决定上下文、预检、风险、输出结构和默认加载的 Skill</span>
          </div>
          <span class="audit-hint">已内置 {{ actionOverview.total }} 个 P0 action</span>
        </div>
        <div class="action-summary-row">
          <div class="action-summary-item">
            <span>动作总数</span>
            <strong>{{ actionOverview.total }}</strong>
          </div>
          <div class="action-summary-item">
            <span>可用动作</span>
            <strong>{{ actionOverview.available }}</strong>
          </div>
          <div class="action-summary-item">
            <span>待预检</span>
            <strong>{{ actionOverview.preflight }}</strong>
          </div>
          <div class="action-summary-item">
            <span>分组</span>
            <strong>{{ actionGroups.length }}</strong>
          </div>
        </div>
        <div class="action-library">
          <div v-for="group in actionGroups" :key="group.category" class="action-group">
            <div class="action-group-head">
              <div class="toolbar-head">
                <span class="action-group-title">{{ group.category }}</span>
                <span class="toolbar-desc">{{ group.items.length }} 个 Action</span>
              </div>
            </div>
            <div class="action-package-list">
              <div v-for="action in group.items" :key="action.code" class="action-package-row">
                <div class="action-package-main">
                  <div class="action-package-title-row">
                    <span class="action-package-name">{{ action.display_name || action.code }}</span>
                    <span class="action-package-code">{{ action.code }}</span>
                    <el-tag size="small" effect="plain" :type="actionModeTagType(action.agent_mode)">
                      {{ formatActionMode(action.agent_mode) }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="actionRiskTagType(action.risk_level)">
                      {{ actionRiskLabel(action.risk_level) }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="action.preflight_required ? 'warning' : 'success'">
                      {{ action.preflight_required ? '需预检' : '免预检' }}
                    </el-tag>
                    <el-tooltip :content="action.available_reason || 'action 可用'" placement="top" :disabled="action.available !== false">
                      <el-tag size="small" effect="plain" :type="actionAvailabilityTagType(action.available)">
                        {{ actionAvailabilityLabel(action.available) }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                  <div class="action-package-desc">{{ action.description || '暂无描述' }}</div>
                  <div class="action-package-tags">
                    <el-tag v-for="context in action.required_context || []" :key="`${action.code}-ctx-${context}`" size="small" effect="plain">
                      上下文：{{ context }}
                    </el-tag>
                    <span v-if="!(action.required_context || []).length" class="muted-text">未要求前置上下文</span>
                  </div>
                </div>
                <div class="action-package-side">
                  <button type="button" class="action-package-stat stat-detail-button" @click="openActionStatDetail(action, 'examples')">
                    <span>示例</span>
                    <strong>{{ (action.suggested_questions || []).length }}</strong>
                  </button>
                  <button type="button" class="action-package-stat stat-detail-button" @click="openActionStatDetail(action, 'skills')">
                    <span>Skill</span>
                    <strong>{{ actionSkillCount(action) }}</strong>
                  </button>
                  <button type="button" class="action-package-stat stat-detail-button" @click="openActionStatDetail(action, 'outputs')">
                    <span>输出</span>
                    <strong>{{ (action.output_blocks || []).length }}</strong>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

    </section>

    <el-dialog v-model="providerDialogVisible" :title="providerForm.id ? '编辑提供商' : '新增提供商'" width="min(880px, 94vw)" destroy-on-close append-to-body>
      <el-form :model="providerForm" label-width="102px">
        <el-form-item label="名称"><el-input v-model="providerForm.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="providerForm.provider_type" style="width:100%">
            <el-option label="OpenAI Compatible" value="openai_compatible" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="千问" value="qwen" />
            <el-option label="智谱" value="zhipu" />
            <el-option label="Kimi" value="kimi" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应商预设">
          <el-select v-model="providerForm.provider_preset" filterable clearable placeholder="选择 DeepSeek / 豆包 / 千问 / Kimi 等预设" style="width:100%" @change="applyProviderPreset">
            <el-option v-for="item in providerPresets" :key="item.key" :label="item.name" :value="item.key">
              <span>{{ item.name }}</span>
              <span class="provider-preset-option">动态获取模型</span>
            </el-option>
          </el-select>
        </el-form-item>
        <div v-if="selectedProviderPresetDetail" class="provider-preset-card">
          <strong>{{ selectedProviderPresetDetail.name }}</strong>
          <span>{{ selectedProviderPresetDetail.notes }}</span>
          <a v-if="selectedProviderPresetDetail.docs_url" :href="selectedProviderPresetDetail.docs_url" target="_blank" rel="noreferrer">查看官方文档</a>
        </div>
        <el-form-item label="Base URL"><el-input v-model="providerForm.base_url" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="providerForm.api_key" type="password" show-password :placeholder="providerApiKeyPlaceholder" /></el-form-item>
        <div class="model-discovery-strip">
          <el-button size="small" :loading="saving.models" :disabled="!providerForm.id" @click="handleListProviderModels">
            拉取模型列表
          </el-button>
          <span v-if="!providerForm.id" class="model-discovery-hint">新增提供商请先保存后再拉取模型。</span>
          <span v-else-if="providerModelRecommendation" class="model-discovery-hint">
            推荐 {{ providerModelRecommendation.model }}
            <el-tag size="small" :type="providerModelRecommendation.supports_tool_calling ? 'success' : 'warning'">
              {{ providerModelRecommendation.supports_tool_calling ? 'Tool Calling 可用' : '已验证文本' }}
            </el-tag>
            <el-button link type="primary" @click="applyRecommendedModel">一键填入</el-button>
          </span>
          <span v-else-if="providerModels.length" class="model-discovery-hint">已拉取 {{ providerModels.length }} 个模型，可在下方选择。</span>
        </div>
        <div class="dialog-grid">
          <el-form-item label="默认模型">
            <el-select v-model="providerForm.default_model" filterable allow-create default-first-option style="width:100%">
              <el-option v-for="item in providerModels" :key="item.id" :label="formatProviderModelLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="备用模型">
            <el-select v-model="providerForm.backup_model" filterable allow-create default-first-option clearable style="width:100%">
              <el-option v-for="item in providerModels" :key="item.id" :label="formatProviderModelLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
        </div>
        <div class="provider-inline-grid provider-runtime-grid">
          <el-form-item label="温度"><el-input-number v-model="providerForm.temperature" class="provider-compact-number" :min="0" :max="2" :step="0.1" :controls="false" /></el-form-item>
          <el-form-item label="最大 Tokens"><el-input-number v-model="providerForm.max_tokens" class="provider-compact-number provider-compact-number--wide" :min="100" :max="16000" :step="100" :controls="false" /></el-form-item>
          <el-form-item label="超时">
            <div class="provider-unit-input">
              <el-input-number v-model="providerForm.timeout_seconds" class="provider-compact-number" :min="5" :max="120" :controls="false" />
              <span>s</span>
            </div>
          </el-form-item>
        </div>
        <div class="provider-inline-grid provider-inline-grid--three provider-billing-grid">
          <el-form-item label="计费币种">
            <el-segmented v-model="providerForm.price_currency" :options="providerCurrencyOptions" />
          </el-form-item>
          <el-form-item label="输入单价">
            <div class="price-input-row">
              <el-input-number v-model="providerForm.input_token_price_per_1m" class="provider-price-input" :min="0" :precision="2" :step="0.01" :controls="false" />
              <span>{{ providerPriceUnitLabel }}</span>
            </div>
          </el-form-item>
          <el-form-item label="输出单价">
            <div class="price-input-row">
              <el-input-number v-model="providerForm.output_token_price_per_1m" class="provider-price-input" :min="0" :precision="2" :step="0.01" :controls="false" />
              <span>{{ providerPriceUnitLabel }}</span>
            </div>
          </el-form-item>
        </div>
        <div class="dialog-grid">
          <el-form-item label="启用"><el-switch v-model="providerForm.is_enabled" /></el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="providerDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.provider" @click="saveProvider">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="mcpDialogVisible" :title="mcpForm.id ? '编辑 MCP' : '新增 MCP'" width="680px" destroy-on-close append-to-body>
      <el-form :model="mcpForm" label-width="102px">
        <el-form-item label="名称"><el-input v-model="mcpForm.name" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="mcpForm.server_type" style="width:100%"><el-option label="HTTP" value="http" /><el-option label="STDIO" value="stdio" /><el-option label="平台内置" value="platform_builtin" /></el-select></el-form-item>
        <el-form-item label="地址或命令"><el-input v-model="mcpForm.endpoint_or_command" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="mcpForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="鉴权配置"><el-input v-model="mcpForm.auth_config_text" type="textarea" :rows="5" placeholder='例如：{"headers":{"Authorization":"Bearer xxx"},"env":{"TOKEN":"xxx"}}' /></el-form-item>
        <div v-if="mcpForm.server_type !== 'platform_builtin'" class="mcp-guard-card">
          <strong>外部 MCP 运行保护</strong>
          <span>默认只读过滤 create/update/delete/run 等写入工具；STDIO 只继承安全系统环境变量，业务凭据请显式放入 auth_config.env。</span>
        </div>
        <div v-if="mcpForm.server_type !== 'platform_builtin'" class="dialog-grid">
          <el-form-item label="写操作">
            <el-switch v-model="mcpAllowWrite" active-text="允许写工具" inactive-text="只读过滤" />
          </el-form-item>
          <el-form-item label="超时秒数">
            <el-input-number v-model="mcpTimeoutSeconds" :min="5" :max="300" />
          </el-form-item>
        </div>
        <el-form-item label="启用工具"><el-select v-model="mcpForm.tool_whitelist" multiple filterable allow-create default-first-option style="width:100%" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="mcpForm.is_enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mcpDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.mcp" @click="saveMcp">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="skillDialogVisible" :title="skillForm.id ? '编辑 Skill' : '新增 Skill'" width="880px" destroy-on-close append-to-body>
      <div v-if="skillForm.id" class="skill-detail-card">
        <div class="skill-detail-title">Skill 详情</div>
        <div class="skill-detail-meta">
          <span>名称：{{ skillForm.name || '--' }}</span>
          <span>标识：{{ skillForm.slug || '--' }}</span>
          <span>类型：{{ formatSkillType(skillForm) }}</span>
          <span>分类：{{ skillForm.category || '未分类' }}</span>
        </div>
        <div class="skill-detail-desc">{{ skillForm.description || '暂无描述' }}</div>
      </div>
      <el-form :model="skillForm" label-width="102px">
        <div class="dialog-grid">
          <el-form-item label="名称"><el-input v-model="skillForm.name" /></el-form-item>
          <el-form-item label="标识"><el-input v-model="skillForm.slug" :disabled="skillForm.is_builtin" /></el-form-item>
        </div>
        <div class="dialog-grid">
          <el-form-item label="来源">
            <el-select v-model="skillForm.source_type" :disabled="skillForm.is_builtin" style="width:100%">
              <el-option label="平台内置" value="inline" />
              <el-option label="本地文件" value="local" />
            </el-select>
          </el-form-item>
          <el-form-item label="分类">
            <el-select v-model="skillForm.category" filterable allow-create default-first-option style="width:100%">
              <el-option v-for="item in skillCategoryOptions" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="描述"><el-input v-model="skillForm.description" /></el-form-item>
        <el-form-item label="适用 Action">
          <el-select v-model="skillForm.applicable_actions" multiple filterable collapse-tags collapse-tags-tooltip style="width:100%">
            <el-option
              v-for="action in actionRegistry"
              :key="action.code"
              :label="`${action.display_name || action.code}（${action.code}）`"
              :value="action.code"
            />
          </el-select>
        </el-form-item>
        <div class="dialog-grid">
          <el-form-item label="风险提示">
            <el-select v-model="skillForm.risk_level" style="width:100%">
              <el-option label="只读" value="read_only" />
              <el-option label="草稿" value="draft" />
              <el-option label="写入" value="write" />
              <el-option label="执行" value="execute" />
            </el-select>
          </el-form-item>
          <el-form-item label="建议轮次">
            <el-input-number v-model="skillForm.max_iterations" :min="0" :max="20" style="width:100%" />
          </el-form-item>
        </div>
        <el-form-item label="适用场景">
          <el-select v-model="skillForm.examples" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip style="width:100%" />
        </el-form-item>
        <el-form-item label="核心工具依赖">
          <el-select v-model="skillForm.builtin_tools" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip style="width:100%">
            <el-option v-for="tool in skillToolOptions" :key="`builtin-${tool}`" :label="tool" :value="tool" />
          </el-select>
        </el-form-item>
        <el-form-item label="补充工具依赖">
          <el-select v-model="skillForm.recommended_tools" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip style="width:100%">
            <el-option v-for="tool in skillToolOptions" :key="`recommend-${tool}`" :label="tool" :value="tool" />
          </el-select>
        </el-form-item>
        <el-form-item label="适用角色"><el-select v-model="skillForm.allowed_role_codes" multiple filterable allow-create default-first-option style="width:100%" /></el-form-item>
        <el-form-item label="输出指导">
          <el-input v-model="skillForm.output_contract_text" type="textarea" :rows="4" placeholder='例如：{"sections":["结论","依据"],"blocks":["risk_notice"]}' />
        </el-form-item>
        <el-form-item label="方法内容"><el-input v-model="skillForm.content" type="textarea" :rows="10" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="skillForm.is_enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="skillDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.skill" @click="saveSkill">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="skillMarketDialogVisible" title="Skill 市场" width="900px" destroy-on-close append-to-body>
      <div class="skill-summary-row">
        <div class="skill-summary-item">
          <span>市场能力包</span>
          <strong>{{ skillMarketSummary.total || 0 }}</strong>
        </div>
        <div class="skill-summary-item">
          <span>平台内置</span>
          <strong>{{ skillMarketSummary.builtin || 0 }}</strong>
        </div>
        <div class="skill-summary-item">
          <span>团队自定义</span>
          <strong>{{ skillMarketSummary.team || 0 }}</strong>
        </div>
        <div class="skill-summary-item">
          <span>已启用</span>
          <strong>{{ skillMarketSummary.enabled || 0 }}</strong>
        </div>
      </div>
      <el-table :data="skillMarketplace.items || []" stripe max-height="460" class="console-table">
        <el-table-column prop="name" label="名称" min-width="170" />
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="source_display" label="来源" width="110" />
        <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
        <el-table-column label="Action" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatActionList(row.applicable_actions) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleCloneSkill(row)">克隆</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="skillMarketDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="a2aDialogVisible" title="创建协同任务草案" width="720px" destroy-on-close append-to-body>
      <el-form :model="a2aForm" label-width="104px">
        <el-form-item label="来源系统"><el-input v-model="a2aForm.source_agent" /></el-form-item>
        <el-form-item label="任务标题"><el-input v-model="a2aForm.title" placeholder="留空则使用 Action 名称" /></el-form-item>
        <el-form-item label="Action">
          <el-select v-model="a2aForm.action_code" filterable style="width:100%">
            <el-option v-for="action in actionRegistry" :key="action.code" :label="`${action.display_name || action.code}（${action.code}）`" :value="action.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="输入参数">
          <el-input v-model="a2aForm.input_payload_text" type="textarea" :rows="8" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="a2aDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveA2ATask">创建任务草案</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runbookDialogVisible" title="生成 Runbook 手册草案" width="760px" destroy-on-close append-to-body>
      <el-form :model="runbookForm" label-width="104px">
        <el-form-item label="标题"><el-input v-model="runbookForm.title" /></el-form-item>
        <el-form-item label="来源会话"><el-input v-model="runbookForm.source_session" placeholder="填写会话 ID 可从事故会话一键生成" /></el-form-item>
        <div class="dialog-grid">
          <el-form-item label="环境"><el-input v-model="runbookForm.environment" /></el-form-item>
          <el-form-item label="服务"><el-input v-model="runbookForm.service" /></el-form-item>
        </div>
        <el-form-item label="标签"><el-select v-model="runbookForm.tags" multiple filterable allow-create default-first-option style="width:100%" /></el-form-item>
        <el-form-item label="引用来源"><el-input v-model="runbookForm.source_refs_text" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="runbookForm.content" type="textarea" :rows="10" placeholder="留空则按环境、服务和标题生成基础草案" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runbookDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRunbookDraft">生成手册草案</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runbookVersionDialogVisible" :title="currentRunbookVersionTitle || 'Runbook 版本历史'" width="840px" destroy-on-close append-to-body>
      <el-table :data="runbookVersions" stripe max-height="420">
        <el-table-column prop="version" label="版本" width="76" />
        <el-table-column prop="status_display" label="状态" width="96" />
        <el-table-column prop="change_note" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column prop="created_by" label="创建人" width="110" />
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="json-preview">{{ formatJsonCompact({ content: row.content, evidence: row.evidence, source_refs: row.source_refs }) }}</div>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="runbookVersionDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="mcpToolsDialogVisible" title="MCP 工具列表" width="760px" destroy-on-close>
      <div class="section-title" style="margin-bottom:12px;">{{ currentMcpToolsTitle || '工具列表' }}</div>
      <div v-if="mcpToolDiagnostics.length" class="mcp-diagnostic-list">
        <div v-for="item in mcpToolDiagnostics" :key="`${item.name}-${item.status}`" class="mcp-diagnostic-item">
          <el-tag size="small" :type="mcpDiagnosticType(item.status)">{{ mcpDiagnosticLabel(item.status) }}</el-tag>
          <span>{{ item.name }}：{{ item.message || `发现 ${item.tool_count || 0} 个工具` }}</span>
        </div>
      </div>
      <el-table :data="mcpToolsList" stripe max-height="420">
        <el-table-column prop="name" label="工具名" min-width="180" />
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="参数" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatMcpToolSchema(row) }}</template>
        </el-table-column>
        <el-table-column label="安全提示" width="120">
          <template #default="{ row }">
            <el-tag v-if="row._meta?.description_warnings?.length" size="small" type="warning">需复核</el-tag>
            <span v-else class="muted-text">--</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!mcpToolsList.length" class="session-empty">暂无工具</div>
      <template #footer>
        <el-button @click="mcpToolsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="statDetailDialogVisible" :title="statDetail.title || '统计详情'" width="640px" destroy-on-close append-to-body>
      <div v-if="statDetail.subtitle" class="stat-detail-subtitle">{{ statDetail.subtitle }}</div>
      <div v-if="statDetail.items.length" class="stat-detail-list">
        <div v-for="(item, index) in statDetail.items" :key="`${item.label}-${index}`" class="stat-detail-item">
          <div class="stat-detail-main">
            <span class="stat-detail-label">{{ item.label }}</span>
            <span v-if="item.desc" class="stat-detail-desc">{{ item.desc }}</span>
          </div>
          <el-tag v-if="item.tag" size="small" effect="plain">{{ item.tag }}</el-tag>
        </div>
      </div>
      <div v-else class="stat-detail-empty">{{ statDetail.emptyText || '暂无详情' }}</div>
      <template #footer>
        <el-button @click="statDetailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ChatDotSquare, Connection, Cpu, Message, Promotion, Setting, Tools } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useRouteTabState } from '@/composables/useRouteTabState'
import {
  archiveAIOpsRunbook,
  autoIngestAIOpsReviewKnowledge,
  cancelAIOpsA2ATask,
  createAIOpsMcpServer,
  createAIOpsProvider,
  createAIOpsSkill,
  createAIOpsA2ATask,
  createAIOpsRunbookDraft,
  createAIOpsRunbookFromSession,
  cloneAIOpsSkill,
  deleteAIOpsMcpServer,
  deleteAIOpsProvider,
  deleteAIOpsSkill,
  deleteAIOpsReviewKnowledge,
  deleteAIOpsRunbook,
  getAIOpsA2ATasks,
  getAIOpsActions,
  getAIOpsConfig,
  getAIOpsPlatformMcpManifest,
  getAIOpsProviderPresets,
  getAIOpsReviewKnowledge,
  getAIOpsRunbooks,
  getAIOpsRunbookVersions,
  getAIOpsSkillMarketplace,
  getAIOpsMcpServers,
  getAIOpsProviders,
  getAIOpsSkills,
  listAIOpsProviderModels,
  listAIOpsMcpTools,
  publishAIOpsRunbook,
  runAIOpsA2ATask,
  interruptAIOpsA2ATask,
  testAIOpsProvider,
  testAIOpsMcpServer,
  updateAIOpsConfig,
  updateAIOpsMcpServer,
  updateAIOpsProvider,
  updateAIOpsSkill,
} from '@/api/modules/aiops'

const configTabs = ['strategy', 'actions', 'skills', 'mcp', 'orchestration', 'providers']
const { activeTab } = useRouteTabState({
  tabs: configTabs,
  defaultTab: 'strategy',
})
const authStore = useAuthStore()
const loading = reactive({ page: false })
const saving = reactive({ config: false, provider: false, models: false, mcp: false, skill: false })

const providers = ref([])
const providerPresets = ref([])
const mcpServers = ref([])
const skills = ref([])
const actionRegistry = ref([])
const actionRegistrySummary = ref({})
const a2aTasks = ref([])
const runbooks = ref([])
const reviewKnowledge = ref([])
const platformMcpManifest = ref({ tools: [], rate_limit: {} })
const skillMarketplace = ref({ summary: {}, items: [] })

const a2aPagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})
const runbookPagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})
const reviewPagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})

const configForm = reactive({
  default_provider_id: null,
  system_prompt: '',
  welcome_message: '',
  suggested_questions: [],
  enabled_mcp_server_ids: [],
  enabled_skill_ids: [],
  is_enabled: true,
  allow_action_execution: true,
  require_confirmation: true,
  show_evidence: true,
  allow_analysis: true,
  max_history_messages: 12,
})

const providerDialogVisible = ref(false)
const mcpDialogVisible = ref(false)
const skillDialogVisible = ref(false)
const skillMarketDialogVisible = ref(false)
const mcpToolsDialogVisible = ref(false)
const a2aDialogVisible = ref(false)
const runbookDialogVisible = ref(false)
const runbookVersionDialogVisible = ref(false)
const statDetailDialogVisible = ref(false)
const runbookVersions = ref([])
const currentRunbookVersionTitle = ref('')
const statDetail = reactive({
  title: '',
  subtitle: '',
  items: [],
  emptyText: '',
})

const providerForm = reactive({})
const providerModels = ref([])
const providerModelRecommendation = ref(null)
const selectedProviderPreset = computed({
  get: () => providerForm.provider_preset || '',
  set: (value) => {
    providerForm.provider_preset = value || ''
  },
})
const mcpForm = reactive({})
const skillForm = reactive({})
const a2aForm = reactive({})
const runbookForm = reactive({})
const mcpToolsList = ref([])
const mcpToolDiagnostics = ref([])
const currentMcpToolsTitle = ref('')

const canInvokeA2A = computed(() => authStore.hasPermission('aiops.a2a.invoke'))
const canManageRunbook = computed(() => authStore.hasPermission('aiops.runbook.manage'))
const canViewMcpServer = computed(() => authStore.hasPermission('aiops.mcp.view'))
const canManageReviewKnowledge = computed(() => authStore.hasPermission('aiops.review.manage'))
const selectedProviderPresetDetail = computed(() => providerPresets.value.find(item => item.key === selectedProviderPreset.value) || null)
const providerApiKeyPlaceholder = computed(() => {
  const preset = selectedProviderPresetDetail.value
  if (preset?.api_key_placeholder) return providerForm.id ? `留空则保留原值；${preset.api_key_placeholder}` : preset.api_key_placeholder
  return providerForm.id ? '留空则保留原值' : 'API Key'
})
const providerCurrencyOptions = [
  { label: '人民币', value: 'CNY' },
  { label: '美元', value: 'USD' },
]
const providerPriceUnitLabel = computed(() => {
  const currency = String(providerForm.price_currency || '').toUpperCase()
  return currency === 'USD' ? '$/M Token' : `${currencySymbol(currency)}/百万 Token`
})
const mcpAuthConfig = computed(() => {
  try {
    const raw = mcpForm.auth_config_text?.trim()
    return raw ? JSON.parse(raw) : {}
  } catch (error) {
    return mcpForm.auth_config && typeof mcpForm.auth_config === 'object' ? mcpForm.auth_config : {}
  }
})
const mcpAllowWrite = computed({
  get: () => Boolean(mcpAuthConfig.value.allow_write),
  set: (value) => updateMcpAuthConfig({ allow_write: Boolean(value) }),
})
const mcpTimeoutSeconds = computed({
  get: () => Number(mcpAuthConfig.value.timeout_seconds || 20),
  set: (value) => updateMcpAuthConfig({ timeout_seconds: Number(value || 20) }),
})
const skillOverview = computed(() => ({
  total: skills.value.length,
  builtin: skills.value.filter(item => item.is_builtin).length,
  custom: skills.value.filter(item => !item.is_builtin).length,
  enabled: skills.value.filter(item => item.is_enabled).length,
}))
const skillGroups = computed(() => {
  const groups = new Map()
  skills.value.forEach((skill) => {
    const category = skill.category || '未分类'
    if (!groups.has(category)) groups.set(category, { category, items: [] })
    groups.get(category).items.push(skill)
  })
  return Array.from(groups.values())
    .map(group => ({
      ...group,
      items: group.items.slice().sort((a, b) => Number(b.is_builtin) - Number(a.is_builtin) || String(a.name).localeCompare(String(b.name), 'zh-CN')),
    }))
    .sort((a, b) => a.category.localeCompare(b.category, 'zh-CN'))
})
const actionOverview = computed(() => ({
  total: Number(actionRegistrySummary.value.total ?? actionRegistry.value.length) || 0,
  available: Number(
    actionRegistrySummary.value.available
      ?? actionRegistry.value.filter(item => item.available !== false).length,
  ) || 0,
  preflight: Number(actionRegistrySummary.value.preflight_required ?? 0) || 0,
  execute: Number(actionRegistrySummary.value.execute ?? 0) || 0,
}))
const actionGroups = computed(() => {
  const groups = new Map()
  actionRegistry.value.forEach((action) => {
    const category = action.category || '通用'
    if (!groups.has(category)) groups.set(category, { category, items: [] })
    groups.get(category).items.push(action)
  })
  return Array.from(groups.values())
    .map(group => ({
      ...group,
      items: group.items
        .slice()
        .sort((a, b) => String(a.display_name || a.code).localeCompare(String(b.display_name || b.code), 'zh-CN')),
    }))
    .sort((a, b) => a.category.localeCompare(b.category, 'zh-CN'))
})
const skillMarketSummary = computed(() => skillMarketplace.value?.summary || {})
const a2aOverview = computed(() => ({
  total: a2aPagination.total || a2aTasks.value.length,
  queued: a2aTasks.value.filter(item => item.status === 'queued').length,
  running: a2aTasks.value.filter(item => item.status === 'running').length,
  done: a2aTasks.value.filter(item => ['completed', 'canceled', 'failed'].includes(item.status)).length,
}))
const runbookOverview = computed(() => ({
  total: runbookPagination.total || runbooks.value.length,
  draft: runbooks.value.filter(item => item.status === 'draft').length,
  published: runbooks.value.filter(item => item.status === 'published').length,
  archived: runbooks.value.filter(item => item.status === 'archived').length,
}))
const reviewOverview = computed(() => ({
  total: reviewPagination.total || reviewKnowledge.value.length,
  session: reviewKnowledge.value.filter(item => item.source_type === 'session').length,
  task: reviewKnowledge.value.filter(item => item.source_type === 'task').length,
  runbook: reviewKnowledge.value.filter(item => item.source_type === 'runbook').length,
}))
const platformMcpOverview = computed(() => ({
  total: platformMcpManifest.value?.tools?.length || 0,
  available: (platformMcpManifest.value?.tools || []).filter(item => item.available !== false).length,
  rateLimit: platformMcpManifest.value?.rate_limit?.per_minute || 0,
}))
const skillCategoryOptions = computed(() => {
  const categories = new Set(['告警排障', '变更关联', '日志查询', 'K8s 诊断', '自愈安全', '任务中心', '发布回滚', '回答规范'])
  skills.value.forEach(item => {
    if (item.category) categories.add(item.category)
  })
  return Array.from(categories)
})
const skillToolOptions = computed(() => {
  const tools = new Set()
  mcpServers.value.forEach(server => (server.tool_whitelist || []).forEach(tool => tools.add(tool)))
  actionRegistry.value.forEach(action => (action.allowed_tools || []).forEach(tool => tools.add(tool)))
  return Array.from(tools).sort()
})

function formatMcpType(serverType) {
  if (serverType === 'platform_builtin') return '平台内置'
  if (serverType === 'stdio') return 'STDIO'
  return 'HTTP'
}

function updateMcpAuthConfig(patch) {
  const nextConfig = { ...mcpAuthConfig.value, ...patch }
  mcpForm.auth_config = nextConfig
  mcpForm.auth_config_text = JSON.stringify(nextConfig, null, 2)
}

function mcpRuntimeMode(row = {}) {
  if (row.server_type === 'platform_builtin') return { label: '平台内置', type: 'success' }
  return row.auth_config?.allow_write ? { label: '可写', type: 'warning' } : { label: '只读', type: 'info' }
}

function mcpDiagnosticType(status) {
  if (status === 'connected') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

function mcpDiagnosticLabel(status) {
  if (status === 'connected') return '已连接'
  if (status === 'failed') return '失败'
  return '未知'
}

function formatMcpToolSchema(row = {}) {
  const properties = row.inputSchema?.properties || {}
  const names = Object.keys(properties)
  if (!names.length) return '无参数'
  return names.slice(0, 6).join('、') + (names.length > 6 ? '…' : '')
}

function formatSkillSource(row = {}) {
  if (row.is_builtin) return '平台内置'
  if (row.source_type === 'local') return '本地文件'
  return '自定义'
}

function formatSkillType(row = {}) {
  return formatSkillSource(row)
}

function getSkillTypeClass(row = {}) {
  if (row.is_builtin) return 'platform_builtin'
  return row.source_type === 'local' ? 'local' : 'custom'
}

function formatSkillRiskLabel(risk) {
  if (risk === 'read_only') return '只读'
  if (risk === 'draft') return '草稿'
  if (risk === 'write') return '写入'
  if (risk === 'execute') return '执行'
  return risk || '只读'
}

function skillRiskTagType(risk) {
  if (risk === 'read_only') return 'info'
  if (risk === 'draft') return 'warning'
  if (risk === 'write') return 'warning'
  if (risk === 'execute') return 'danger'
  return 'info'
}

function skillRecommendedTools(skill = {}) {
  return Array.from(new Set([...(skill.builtin_tools || []), ...(skill.recommended_tools || [])])).filter(Boolean)
}

function skillRecommendedToolCount(skill = {}) {
  return skillRecommendedTools(skill).length
}

function actionSkillCount(action = {}) {
  return new Set(action.skills || []).size
}

function formatActionName(code) {
  const action = actionRegistry.value.find(item => item.code === code)
  return action?.display_name || code
}

function formatEnabledTools(tools) {
  if (!Array.isArray(tools) || !tools.length) return '--'
  return tools.join('、')
}

function formatActionList(items) {
  if (!Array.isArray(items) || !items.length) return '--'
  return items.join('、')
}

function openStatDetail({ title, subtitle, items, emptyText }) {
  statDetail.title = title
  statDetail.subtitle = subtitle || ''
  statDetail.items = Array.isArray(items) ? items : []
  statDetail.emptyText = emptyText || '暂无详情'
  statDetailDialogVisible.value = true
}

function openSkillStatDetail(skill = {}, type) {
  const skillName = skill.name || skill.slug || '--'
  if (type === 'tools') {
    const builtinTools = new Set((skill.builtin_tools || []).filter(Boolean))
    const recommendedTools = new Set((skill.recommended_tools || []).filter(Boolean))
    const items = skillRecommendedTools(skill).map(tool => ({
      label: tool,
      tag: builtinTools.has(tool) ? '核心工具' : '补充工具',
      desc: builtinTools.has(tool) && recommendedTools.has(tool) ? '同时声明在补充依赖中' : '',
    }))
    openStatDetail({
      title: '工具依赖详情',
      subtitle: `Skill：${skillName}`,
      items,
      emptyText: '当前 Skill 未声明工具依赖',
    })
    return
  }
  const items = (skill.examples || []).filter(Boolean).map((example, index) => ({
    label: example,
    tag: `场景 ${index + 1}`,
  }))
  openStatDetail({
    title: '适用场景详情',
    subtitle: `Skill：${skillName}`,
    items,
    emptyText: '当前 Skill 未配置适用场景',
  })
}

function openActionStatDetail(action = {}, type) {
  const actionName = action.display_name || action.code || '--'
  if (type === 'examples') {
    const items = (action.suggested_questions || []).filter(Boolean).map((example, index) => ({
      label: example,
      tag: `示例 ${index + 1}`,
    }))
    openStatDetail({
      title: '示例入口详情',
      subtitle: `Action：${actionName}`,
      items,
      emptyText: '当前 Action 未配置示例入口',
    })
    return
  }
  if (type === 'skills') {
    const skillsBySlug = new Map(skills.value.map(item => [item.slug, item]))
    const items = Array.from(new Set(action.skills || [])).filter(Boolean).map((slug) => {
      const skill = skillsBySlug.get(slug)
      return {
        label: skill?.name || slug,
        desc: skill?.description || `标识：${slug}`,
        tag: skill?.is_builtin ? '内置' : '自定义',
      }
    })
    openStatDetail({
      title: '默认 Skill 详情',
      subtitle: `Action：${actionName}`,
      items,
      emptyText: '当前 Action 未绑定默认 Skill',
    })
    return
  }
  const items = (action.output_blocks || []).filter(Boolean).map(block => ({
    label: block,
    tag: '输出块',
  }))
  openStatDetail({
    title: '结构化输出详情',
    subtitle: `Action：${actionName}`,
    items,
    emptyText: '当前 Action 未配置结构化输出块',
  })
}

function formatActionMode(mode) {
  if (mode === 'direct') return 'Direct'
  if (mode === 'react') return 'ReAct'
  if (mode === 'plan_react') return 'Plan+ReAct'
  return mode || '--'
}

function actionModeTagType(mode) {
  if (mode === 'direct') return 'info'
  if (mode === 'plan_react') return 'warning'
  return 'success'
}

function actionRiskLabel(risk) {
  if (risk === 'read_only') return '只读'
  if (risk === 'draft') return '草稿'
  if (risk === 'write') return '写入'
  if (risk === 'execute') return '执行'
  return risk || '--'
}

function actionRiskTagType(risk) {
  if (risk === 'read_only') return 'info'
  if (risk === 'draft') return 'warning'
  if (risk === 'execute') return 'danger'
  return 'warning'
}

function actionAvailabilityLabel(available) {
  return available === false ? '受限' : '可用'
}

function actionAvailabilityTagType(available) {
  return available === false ? 'warning' : 'success'
}

function formatProviderModelLabel(item = {}) {
  const owner = item.owned_by ? ` · ${item.owned_by}` : ''
  return `${item.id}${owner}`
}

function currencySymbol(currency) {
  return String(currency || '').toUpperCase() === 'CNY' ? '¥' : '$'
}

function formatProviderCurrency(currency) {
  return String(currency || '').toUpperCase() === 'CNY' ? '人民币' : '美元'
}

function formatProviderType(providerType) {
  return {
    openai_compatible: 'OpenAI Compatible',
    deepseek: 'DeepSeek',
    qwen: '千问',
    zhipu: '智谱',
    kimi: 'Kimi',
  }[providerType] || providerType || '-'
}

function providerOptionLabel(provider = {}) {
  if (provider.runtime_ready) return provider.name
  return `${provider.name}（${provider.is_enabled ? '待配置' : '停用'}）`
}

function providerRuntimeTagType(row = {}) {
  if (row.runtime_ready) return 'success'
  return row.is_enabled ? 'warning' : 'info'
}

function providerRuntimeLabel(row = {}) {
  if (row.runtime_ready) return '可用'
  return row.is_enabled ? '待配置' : '停用'
}

function providerRuntimeHint(row = {}) {
  if (row.runtime_ready) return '可作为智能助手运行模型'
  return row.setup_hint || (row.is_enabled ? '请补全模型配置后使用' : '当前已停用，启用后可作为运行模型')
}

function detectProviderPreset(provider = {}) {
  if (provider.provider_preset) return provider.provider_preset
  const normalizedBaseUrl = String(provider.base_url || '').replace(/\/+$/, '').toLowerCase()
  const defaultModel = String(provider.default_model || '').toLowerCase()
  const backupModel = String(provider.backup_model || '').toLowerCase()
  const matchedPreset = providerPresets.value.find((preset) => {
    if (preset.key === 'custom_openai_compatible') return false
    const presetBaseUrl = String(preset.base_url || '').replace(/\/+$/, '').toLowerCase()
    const presetDefaultModel = String(preset.default_model || '').toLowerCase()
    const presetBackupModel = String(preset.backup_model || '').toLowerCase()
    return Boolean(
      (presetBaseUrl && normalizedBaseUrl === presetBaseUrl)
      || (presetDefaultModel && defaultModel === presetDefaultModel)
      || (presetBackupModel && backupModel === presetBackupModel),
    )
  })
  if (matchedPreset) return matchedPreset.key
  const baseUrl = (provider.base_url || '').toLowerCase()
  if (baseUrl.includes('deepseek')) return 'deepseek'
  if (baseUrl.includes('bigmodel') || /^glm-/i.test(provider.default_model || '')) return 'zhipu_glm'
  if (baseUrl.includes('minimax') || /^minimax/i.test(provider.default_model || '')) return 'minimax'
  if (baseUrl.includes('xiaomimimo') || baseUrl.includes('mimo.mi.com')) return 'xiaomi_mimo'
  if (baseUrl.includes('volces.com') || baseUrl.includes('volcengine') || baseUrl.includes('doubao')) return 'volcengine_doubao'
  if (baseUrl.includes('dashscope') || baseUrl.includes('aliyuncs.com') || /^qwen/i.test(provider.default_model || '')) return 'aliyun_qwen'
  if (baseUrl.includes('moonshot') || /^kimi/i.test(provider.default_model || '')) return 'moonshot_kimi'
  if (String(provider.provider_type || '').toLowerCase() === 'openai_compatible') return 'custom_openai_compatible'
  return ''
}

function normalizeProviderList(data) {
  const items = Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : [])
  return items.map(item => ({
    ...item,
    provider_preset: detectProviderPreset(item),
  }))
}
function applyProviderPreset(key) {
  const preset = providerPresets.value.find(item => item.key === key)
  if (!preset) {
    providerForm.provider_preset = ''
    return
  }
  Object.assign(providerForm, {
    name: providerForm.name || preset.name,
    provider_type: preset.provider_type || 'openai_compatible',
    base_url: preset.base_url || providerForm.base_url,
    default_model: Object.prototype.hasOwnProperty.call(preset, 'default_model') ? preset.default_model : providerForm.default_model,
    backup_model: Object.prototype.hasOwnProperty.call(preset, 'backup_model') ? preset.backup_model : providerForm.backup_model,
    temperature: preset.temperature ?? providerForm.temperature,
    max_tokens: preset.max_tokens || providerForm.max_tokens,
    timeout_seconds: preset.timeout_seconds || providerForm.timeout_seconds,
    price_currency: preset.price_currency || providerForm.price_currency || 'CNY',
    provider_preset: preset.key,
  })
  providerModels.value = []
  providerModelRecommendation.value = null
}

function resetProviderForm() {
  Object.assign(providerForm, {
    id: null,
    name: '',
    provider_type: 'openai_compatible',
    base_url: '',
    api_key: '',
    default_model: '',
    backup_model: '',
    temperature: 0.2,
    max_tokens: 10000,
    timeout_seconds: 30,
    price_currency: 'CNY',
    input_token_price_per_1m: 0,
    output_token_price_per_1m: 0,
    provider_preset: '',
    is_enabled: true,
  })
  selectedProviderPreset.value = ''
}

function resetMcpForm() {
  Object.assign(mcpForm, {
    id: null,
    name: '',
    server_type: 'http',
    endpoint_or_command: '',
    description: '',
    auth_config: {},
    auth_config_text: '{}',
    tool_whitelist: [],
    is_enabled: true,
  })
  mcpToolDiagnostics.value = []
}

function resetSkillForm() {
  Object.assign(skillForm, {
    id: null,
    name: '',
    slug: '',
    source_type: 'inline',
    description: '',
    category: '',
    applicable_actions: [],
    examples: [],
    builtin_tools: [],
    recommended_tools: [],
    max_iterations: 0,
    risk_level: 'read_only',
    output_contract: {},
    output_contract_text: '{}',
    content: '',
    allowed_role_codes: [],
    is_builtin: false,
    is_enabled: true,
  })
}

function resetA2AForm() {
  Object.assign(a2aForm, {
    source_agent: 'web-console',
    title: '',
    action_code: 'slo.analysis',
    input_payload_text: '{\n  "environment": "电商测试环境",\n  "service": "order-service"\n}',
  })
}

function resetRunbookForm() {
  Object.assign(runbookForm, {
    title: '',
    environment: '',
    service: '',
    source_session: '',
    content: '',
    tags: [],
    source_refs_text: '[]',
  })
}

function applyConfig(payload = {}) {
  Object.assign(configForm, {
    default_provider_id: payload.default_provider?.id || null,
    system_prompt: payload.system_prompt || '',
    welcome_message: payload.welcome_message || '',
    suggested_questions: payload.suggested_questions || [],
    enabled_mcp_server_ids: payload.enabled_mcp_server_ids || [],
    enabled_skill_ids: payload.enabled_skill_ids || [],
    is_enabled: payload.is_enabled ?? true,
    allow_action_execution: payload.allow_action_execution ?? true,
    require_confirmation: true,
    show_evidence: payload.show_evidence ?? true,
    allow_analysis: payload.allow_analysis ?? true,
    max_history_messages: payload.max_history_messages || 12,
  })
}

async function optionalLoad(loader, fallback) {
  try {
    return await loader()
  } catch {
    if (typeof fallback === 'function') {
      fallback()
    }
    return null
  }
}

async function loadAll() {
  loading.page = true
  try {
    const [config, providerData, presetData, mcpData, skillData, marketData, actionData, mcpManifestData] = await Promise.all([
      getAIOpsConfig(),
      getAIOpsProviders(),
      getAIOpsProviderPresets(),
      getAIOpsMcpServers(),
      getAIOpsSkills(),
      getAIOpsSkillMarketplace(),
      getAIOpsActions(),
      optionalLoad(() => getAIOpsPlatformMcpManifest({ skipErrorMessage: true })),
    ])
    applyConfig(config)
    providerPresets.value = presetData?.presets || []
    providers.value = normalizeProviderList(providerData)
    mcpServers.value = mcpData || []
    skills.value = skillData || []
    skillMarketplace.value = marketData || { summary: {}, items: [] }
    actionRegistry.value = actionData?.actions || []
    actionRegistrySummary.value = actionData?.summary || {}
    platformMcpManifest.value = mcpManifestData || { tools: [], rate_limit: {} }
    await Promise.all([
      optionalLoad(() => loadA2ATasks(a2aPagination.page, { skipErrorMessage: true }), () => {
        a2aPagination.total = 0
        a2aTasks.value = []
      }),
      optionalLoad(() => loadRunbooks(runbookPagination.page, { skipErrorMessage: true }), () => {
        runbookPagination.total = 0
        runbooks.value = []
      }),
      optionalLoad(() => loadReviewKnowledge(reviewPagination.page, { skipErrorMessage: true }), () => {
        reviewPagination.total = 0
        reviewKnowledge.value = []
      }),
    ])
  } finally {
    loading.page = false
  }
}

async function loadA2ATasks(page = 1, config = {}) {
  try {
    const data = await getAIOpsA2ATasks({ page, page_size: a2aPagination.pageSize }, config)
    a2aPagination.page = page
    a2aPagination.total = data.count || 0
    a2aTasks.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) {
      return loadA2ATasks(page - 1, config)
    }
    throw error
  }
}

async function loadRunbooks(page = 1, config = {}) {
  try {
    const data = await getAIOpsRunbooks({ page, page_size: runbookPagination.pageSize }, config)
    runbookPagination.page = page
    runbookPagination.total = data.count || 0
    runbooks.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) {
      return loadRunbooks(page - 1, config)
    }
    throw error
  }
}

async function loadReviewKnowledge(page = 1, config = {}) {
  try {
    const data = await getAIOpsReviewKnowledge({ page, page_size: reviewPagination.pageSize }, config)
    reviewPagination.page = page
    reviewPagination.total = data.count || 0
    reviewKnowledge.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) {
      return loadReviewKnowledge(page - 1, config)
    }
    throw error
  }
}

async function saveConfig() {
  saving.config = true
  try {
    await updateAIOpsConfig({ ...configForm, require_confirmation: true })
    ElMessage.success('智能体策略已保存')
    await loadAll()
  } finally {
    saving.config = false
  }
}

function openProviderDialog(row) {
  resetProviderForm()
  providerModels.value = []
  providerModelRecommendation.value = null
  if (row) {
    Object.assign(providerForm, row, { api_key: '' })
    selectedProviderPreset.value = detectProviderPreset(row)
    providerForm.provider_preset = selectedProviderPreset.value
  }
  providerDialogVisible.value = true
}

async function saveProvider() {
  saving.provider = true
  try {
    const payload = { ...providerForm }
    payload.provider_preset = selectedProviderPreset.value || payload.provider_preset || ''
    payload.price_currency = payload.price_currency || 'CNY'
    payload.input_token_price_per_1m = Number(payload.input_token_price_per_1m || 0).toFixed(2)
    payload.output_token_price_per_1m = Number(payload.output_token_price_per_1m || 0).toFixed(2)
    if (!payload.api_key) delete payload.api_key
    if (providerForm.id) await updateAIOpsProvider(providerForm.id, payload)
    else await createAIOpsProvider(payload)
    providerDialogVisible.value = false
    ElMessage.success('模型提供商已保存')
    await loadAll()
  } finally {
    saving.provider = false
  }
}

async function handleTestProvider(row) {
  try {
    const result = await testAIOpsProvider(row.id)
    ElMessage.success(result.message)
  } catch (error) {
    ElMessage.error(error.response?.data?.message || row.setup_hint || '模型测试失败')
  } finally {
    await loadAll()
  }
}

async function handleListProviderModels() {
  if (!providerForm.id) {
    ElMessage.warning('请先保存提供商后再拉取模型列表')
    return
  }
  if (providerForm.api_key) {
    ElMessage.warning('检测到 API Key 尚未保存，请先保存后再拉取模型列表')
    return
  }
  saving.models = true
  try {
    const result = await listAIOpsProviderModels(providerForm.id, { probe: true })
    providerModels.value = result.models || []
    providerModelRecommendation.value = result.recommendation || null
    if (result.catalog_error) {
      ElMessage.warning(result.fallback_used ? `模型列表接口不可用，已回退到已配置模型：${result.catalog_error}` : result.catalog_error)
    }
    if (providerModelRecommendation.value?.model) {
      providerForm.default_model = providerModelRecommendation.value.model
      ElMessage.success(providerModelRecommendation.value.message || `已推荐 ${providerModelRecommendation.value.model}`)
    } else if (providerModels.value.length) {
      ElMessage.success(`已拉取 ${providerModels.value.length} 个模型`)
    } else {
      ElMessage.warning('未从供应商返回模型列表')
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '拉取模型列表失败')
  } finally {
    saving.models = false
  }
}

function applyRecommendedModel() {
  if (!providerModelRecommendation.value?.model) return
  providerForm.default_model = providerModelRecommendation.value.model
  const fallback = providerModels.value.find(item => item.id !== providerModelRecommendation.value.model)?.id || providerForm.backup_model
  providerForm.backup_model = fallback || ''
  ElMessage.success('已填入推荐模型，保存后生效')
}

async function handleDeleteProvider(row) {
  await ElMessageBox.confirm(`确认删除模型提供商 ${row.name} 吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsProvider(row.id)
  ElMessage.success('模型提供商已删除')
  await loadAll()
}

function openMcpDialog(row) {
  resetMcpForm()
  if (row) Object.assign(mcpForm, row, { auth_config_text: JSON.stringify(row.auth_config || {}, null, 2) })
  mcpDialogVisible.value = true
}

async function handleTestMcp(row) {
  const result = await testAIOpsMcpServer(row.id)
  ElMessage.success(result.message || 'MCP 连接成功')
}

async function handleListMcpTools(row) {
  const result = await listAIOpsMcpTools(row.id)
  currentMcpToolsTitle.value = `${row.name} / ${result.count || 0} 个工具`
  mcpToolsList.value = result.tools || []
  mcpToolDiagnostics.value = result.diagnostics || []
  mcpToolsDialogVisible.value = true
}

async function saveMcp() {
  saving.mcp = true
  try {
    const payload = { ...mcpForm }
    try {
      payload.auth_config = payload.auth_config_text?.trim() ? JSON.parse(payload.auth_config_text) : {}
    } catch (error) {
      ElMessage.error('鉴权配置不是合法 JSON')
      return
    }
    delete payload.auth_config_text
    if (mcpForm.id) await updateAIOpsMcpServer(mcpForm.id, payload)
    else await createAIOpsMcpServer(payload)
    mcpDialogVisible.value = false
    ElMessage.success('MCP 配置已保存')
    await loadAll()
  } finally {
    saving.mcp = false
  }
}

async function handleDeleteMcp(row) {
  await ElMessageBox.confirm(`确认删除 MCP ${row.name} 吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsMcpServer(row.id)
  ElMessage.success('MCP 已删除')
  await loadAll()
}

function openSkillDialog(row) {
  resetSkillForm()
  if (row) {
    Object.assign(skillForm, {
      ...row,
      applicable_actions: Array.isArray(row.applicable_actions) ? [...row.applicable_actions] : [],
      examples: Array.isArray(row.examples) ? [...row.examples] : [],
      builtin_tools: Array.isArray(row.builtin_tools) ? [...row.builtin_tools] : [],
      recommended_tools: Array.isArray(row.recommended_tools) ? [...row.recommended_tools] : [],
      allowed_role_codes: Array.isArray(row.allowed_role_codes) ? [...row.allowed_role_codes] : [],
      output_contract: row.output_contract && typeof row.output_contract === 'object' ? row.output_contract : {},
      output_contract_text: JSON.stringify(row.output_contract && typeof row.output_contract === 'object' ? row.output_contract : {}, null, 2),
    })
  }
  skillDialogVisible.value = true
}

async function saveSkill() {
  saving.skill = true
  try {
    let outputContract = {}
    try {
      const rawContract = String(skillForm.output_contract_text || '').trim()
      outputContract = rawContract ? JSON.parse(rawContract) : {}
    } catch (error) {
      ElMessage.error('输出约束必须是合法 JSON 对象')
      return
    }
    if (!outputContract || Array.isArray(outputContract) || typeof outputContract !== 'object') {
      ElMessage.error('输出约束必须是 JSON 对象')
      return
    }
    const payload = {
      ...skillForm,
      output_contract: outputContract,
      applicable_actions: skillForm.applicable_actions || [],
      examples: skillForm.examples || [],
      builtin_tools: skillForm.builtin_tools || [],
      recommended_tools: skillForm.recommended_tools || [],
      allowed_role_codes: skillForm.allowed_role_codes || [],
      max_iterations: Number(skillForm.max_iterations || 0),
    }
    delete payload.output_contract_text
    delete payload.id
    delete payload.is_builtin
    if (skillForm.id) await updateAIOpsSkill(skillForm.id, payload)
    else await createAIOpsSkill(payload)
    skillDialogVisible.value = false
    ElMessage.success('Skill 已保存')
    await loadAll()
  } finally {
    saving.skill = false
  }
}

async function handleDeleteSkill(row) {
  await ElMessageBox.confirm(`确认删除 Skill ${row.name} 吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsSkill(row.id)
  ElMessage.success('Skill 已删除')
  await loadAll()
}

function openSkillMarketDialog() {
  skillMarketDialogVisible.value = true
}

async function handleCloneSkill(row) {
  await cloneAIOpsSkill(row.id, {})
  ElMessage.success('已克隆为团队 Skill')
  skillMarketDialogVisible.value = false
  await loadAll()
}

function openA2ADialog() {
  resetA2AForm()
  a2aDialogVisible.value = true
}

async function saveA2ATask() {
  let inputPayload = {}
  try {
    inputPayload = a2aForm.input_payload_text?.trim() ? JSON.parse(a2aForm.input_payload_text) : {}
  } catch (error) {
    ElMessage.error('输入参数必须是合法 JSON 对象')
    return
  }
  if (!inputPayload || Array.isArray(inputPayload) || typeof inputPayload !== 'object') {
    ElMessage.error('输入参数必须是 JSON 对象')
    return
  }
  await createAIOpsA2ATask({
    source_agent: a2aForm.source_agent,
    title: a2aForm.title,
    action_code: a2aForm.action_code,
    input_payload: inputPayload,
  })
  a2aDialogVisible.value = false
  ElMessage.success('协同任务草案已创建')
  await loadA2ATasks(1)
}

async function handleCancelA2ATask(row) {
  await ElMessageBox.confirm(`确认取消外部任务《${row.title}》吗？`, '取消确认', { type: 'warning' })
  await cancelAIOpsA2ATask(row.public_id)
  ElMessage.success('协同任务已取消')
  await loadA2ATasks(a2aPagination.page)
}

async function handleRunA2ATask(row) {
  await runAIOpsA2ATask(row.public_id)
  ElMessage.success('多 Agent 编排已完成')
  await loadA2ATasks(a2aPagination.page)
}

async function handleInterruptA2ATask(row) {
  await ElMessageBox.confirm(`确认中断协同任务《${row.title}》吗？`, '中断确认', { type: 'warning' })
  await interruptAIOpsA2ATask(row.public_id)
  ElMessage.success('协同任务已中断')
  await loadA2ATasks(a2aPagination.page)
}

function openRunbookDialog() {
  resetRunbookForm()
  runbookDialogVisible.value = true
}

async function saveRunbookDraft() {
  let sourceRefs = []
  try {
    sourceRefs = runbookForm.source_refs_text?.trim() ? JSON.parse(runbookForm.source_refs_text) : []
  } catch (error) {
    ElMessage.error('引用来源必须是合法 JSON 数组')
    return
  }
  if (!Array.isArray(sourceRefs)) {
    ElMessage.error('引用来源必须是 JSON 数组')
    return
  }
  const payload = {
    title: runbookForm.title,
    environment: runbookForm.environment,
    service: runbookForm.service,
    content: runbookForm.content,
    tags: runbookForm.tags || [],
    source_refs: sourceRefs,
  }
  if (runbookForm.source_session) {
    await createAIOpsRunbookFromSession({
      ...payload,
      source_session: runbookForm.source_session,
    })
  } else {
    await createAIOpsRunbookDraft(payload)
  }
  runbookDialogVisible.value = false
  ElMessage.success('Runbook 手册草案已生成')
  await loadRunbooks(1)
}

async function handlePublishRunbook(row) {
  await publishAIOpsRunbook(row.id, { change_note: '控制台发布' })
  ElMessage.success('Runbook 已发布并自动沉淀复盘知识')
  await Promise.all([loadRunbooks(runbookPagination.page), loadReviewKnowledge(reviewPagination.page)])
}

async function handleArchiveRunbook(row) {
  await ElMessageBox.confirm(`确认归档 Runbook《${row.title}》吗？`, '归档确认', { type: 'warning' })
  await archiveAIOpsRunbook(row.id, { change_note: '控制台归档' })
  ElMessage.success('Runbook 已归档')
  await loadRunbooks(runbookPagination.page)
}

async function handleViewRunbookVersions(row) {
  const data = await getAIOpsRunbookVersions(row.id)
  runbookVersions.value = data || []
  currentRunbookVersionTitle.value = `${row.title} / ${runbookVersions.value.length} 个版本`
  runbookVersionDialogVisible.value = true
}

async function handleDeleteRunbook(row) {
  await ElMessageBox.confirm(`确认删除 Runbook《${row.title}》吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsRunbook(row.id)
  ElMessage.success('Runbook 手册已删除')
  await loadRunbooks(runbooks.value.length === 1 && runbookPagination.page > 1 ? runbookPagination.page - 1 : runbookPagination.page)
}

async function handleAutoIngestReviewKnowledge(row, type) {
  const payload = {
    title: `${row.title} 复盘知识`,
  }
  if (type === 'task') payload.source_task = row.id
  if (type === 'runbook') payload.source_runbook = row.id
  await autoIngestAIOpsReviewKnowledge(payload)
  ElMessage.success('复盘知识已沉淀')
  await loadReviewKnowledge(1)
}

async function handleDeleteReviewKnowledge(row) {
  await ElMessageBox.confirm(`确认删除复盘知识《${row.title}》吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsReviewKnowledge(row.id)
  ElMessage.success('复盘知识已删除')
  await loadReviewKnowledge(reviewKnowledge.value.length === 1 && reviewPagination.page > 1 ? reviewPagination.page - 1 : reviewPagination.page)
}

function formatJsonCompact(value) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch (error) {
    return String(value || '')
  }
}

onMounted(async () => {
  resetProviderForm()
  resetMcpForm()
  resetSkillForm()
  resetA2AForm()
  resetRunbookForm()
  await loadAll()
})
</script>

<style scoped>
.aiops-config-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fffdf8 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
  padding: 14px 16px;
}

.aiops-config-page :deep(.el-button) {
  border-radius: 10px;
}

.hero-actions :deep(.el-button),
.section-toolbar :deep(.el-button),
.audit-toolbar-actions :deep(.el-button) {
  min-height: 26px;
  padding: 0 9px;
  font-weight: 500;
}

.hero-actions :deep(.el-button:not(.el-button--primary)),
.section-toolbar :deep(.el-button:not(.el-button--primary)),
.audit-toolbar-actions :deep(.el-button:not(.el-button--primary)) {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  color: #475569;
  box-shadow: none;
}

.hero-actions :deep(.el-button:not(.is-link):hover),
.section-toolbar :deep(.el-button:not(.is-link):hover),
.audit-toolbar-actions :deep(.el-button:not(.is-link):hover) {
  border-color: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
  background: #f8fbff;
}

.hero,
.hero-copy,
.hero-title-row,
.hero-actions,
.config-grid,
.switch-list,
.audit-grid,
.audit-toolbar-actions,
.skill-detail-meta {
  display: flex;
  gap: 8px;
}

.hero {
  min-height: 68px;
  padding: 12px 14px;
  align-items: center;
  justify-content: space-between;
}

.hero-copy {
  gap: 4px;
}

.hero-title-row {
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-icon {
  width: 42px;
  height: 42px;
  border-radius: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #0f766e, #2563eb);
}

.hero h2 {
  margin: 0;
  font-size: 23px;
  line-height: 1.1;
  color: #0f172a;
}

.page-inline-desc {
  margin: 0;
  color: #646a73;
  font-size: 13px;
  line-height: 1.45;
}

.hero-actions {
  align-items: center;
  flex-wrap: wrap;
}

.hero-actions :deep(.el-button) {
  min-height: 38px;
  padding: 0 16px;
  border-radius: 12px;
}

.tabs-card {
  display: flex;
  align-items: flex-start;
  width: 100%;
  padding: 4px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.event-like-tabs {
  width: 100%;
}

.event-like-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.event-like-tabs :deep(.el-tabs__nav-wrap) {
  display: block;
  max-width: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.event-like-tabs :deep(.el-tabs__nav-wrap::after),
.event-like-tabs :deep(.el-tabs__active-bar),
.event-like-tabs :deep(.el-tabs__content) {
  display: none;
}

.event-like-tabs :deep(.el-tabs__nav-scroll) {
  overflow: visible;
}

.event-like-tabs :deep(.el-tabs__nav) {
  display: flex;
  gap: 8px;
  border: 0;
}

.event-like-tabs :deep(.el-tabs__item) {
  min-height: 38px;
  height: 38px;
  padding: 0 20px !important;
  border-radius: 8px;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 38px;
}

.event-like-tabs :deep(.el-tabs__item:hover) {
  background: rgba(51, 112, 255, 0.06);
  color: #245bdb;
}

.event-like-tabs :deep(.el-tabs__item.is-active) {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-label :deep(.el-icon) {
  font-size: 15px;
}

.config-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 360px);
  align-items: flex-start;
  gap: 10px;
}

.config-section {
  width: 100%;
}

.config-section--main {
  min-width: 0;
}

.config-section--runtime {
  position: sticky;
  top: 12px;
  padding: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border-color: rgba(96, 165, 250, 0.22);
}

.surface-card {
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94));
  border: 1px solid #e2e8f0;
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

.runtime-note {
  margin: -2px 0 10px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.switch-list {
  flex-direction: column;
  gap: 8px;
}

.switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.switch-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.switch-copy span {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
}

.switch-copy small {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.runtime-form {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.92);
}

.runtime-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.runtime-field-tip {
  width: 100%;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.section-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.toolbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-head {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.toolbar-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.2;
}

.toolbar-desc {
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.4;
}

.provider-strategy-reminder {
  color: #334155;
  font-weight: 700;
}

.strategy-actions {
  margin-top: 0;
}

.dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 10px;
}

.provider-inline-grid {
  display: grid;
  gap: 0 10px;
}

.provider-inline-grid--three,
.provider-runtime-grid,
.provider-billing-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.provider-inline-grid :deep(.el-form-item) {
  min-width: 0;
}

.provider-inline-grid :deep(.el-form-item__label) {
  flex: 0 0 auto;
  width: 90px !important;
  padding-right: 8px;
  justify-content: flex-end;
  white-space: nowrap;
}

.provider-inline-grid :deep(.el-form-item:first-child .el-form-item__label) {
  width: 102px !important;
}

.provider-inline-grid :deep(.el-form-item__content) {
  min-width: 0;
}

.provider-compact-number {
  width: 84px;
}

.provider-compact-number--wide {
  width: 100px;
}

.provider-compact-number :deep(.el-input__inner),
.price-input-row :deep(.el-input__inner) {
  text-align: left;
}

.provider-billing-grid :deep(.el-segmented) {
  width: 150px;
  max-width: 100%;
  padding: 2px;
}

.provider-billing-grid :deep(.el-segmented__item) {
  min-width: 0;
  padding: 0 12px;
}

.provider-unit-input {
  display: inline-grid;
  grid-template-columns: 84px auto;
  align-items: center;
  gap: 6px;
}

.price-input-row {
  display: grid;
  grid-template-columns: 76px minmax(72px, auto);
  align-items: center;
  gap: 6px;
  width: 100%;
}

.price-input-row .el-input-number {
  min-width: 0;
  width: 76px;
}

.provider-unit-input span,
.price-input-row span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.audit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.audit-card {
  padding: 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.audit-card--inline {
  min-height: 68px;
}

.audit-card strong {
  font-size: 24px;
  color: #0f172a;
}

.cost-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 0;
}

.cost-panel {
  padding: 12px;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
}

.cost-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cost-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
}

.cost-row strong {
  color: #0f172a;
  font-weight: 700;
}

.json-preview {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
}

.audit-card--info {
  background: linear-gradient(145deg, #eff6ff 0%, #ffffff 100%);
}

.audit-card--success {
  background: linear-gradient(145deg, #ecfdf5 0%, #ffffff 100%);
}

.audit-card--warning {
  background: linear-gradient(145deg, #fffbeb 0%, #ffffff 100%);
}

.audit-card--danger {
  background: linear-gradient(145deg, #fef2f2 0%, #ffffff 100%);
}

.console-table {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}

.console-table :deep(th.el-table__cell) {
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.model-discovery-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -2px 0 12px 102px;
  padding: 8px 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.model-discovery-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.provider-preset-option {
  float: right;
  margin-left: 18px;
  color: #94a3b8;
  font-size: 12px;
}

.provider-preset-card {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: -4px 0 12px 102px;
  padding: 9px 11px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f8fafc, #eff6ff);
  border: 1px solid #dbeafe;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.provider-preset-card strong {
  color: #0f172a;
  font-size: 13px;
}

.provider-preset-card a {
  color: #2563eb;
  text-decoration: none;
}

.mcp-guard-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: -2px 0 12px 102px;
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f8fafc, #fff7ed);
  border: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.mcp-guard-card strong {
  color: #0f172a;
  font-size: 13px;
}

.mcp-diagnostic-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  padding: 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.mcp-diagnostic-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.muted-text {
  color: #94a3b8;
}

.mcp-server-panel {
  margin: 10px 0 12px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
}

.audit-section {
  margin-top: 12px;
}

.audit-toolbar {
  justify-content: space-between;
  align-items: center;
}

.audit-toolbar-actions {
  align-items: center;
  flex-wrap: wrap;
}

.audit-hint {
  color: #64748b;
  font-size: 12px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.empty-panel {
  padding: 18px 4px 8px;
}

.empty-copy {
  min-height: 120px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  border: 1px dashed rgba(148, 163, 184, 0.35);
  color: #64748b;
  font-size: 13px;
  line-height: 1.8;
}

.skill-summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.skill-summary-item {
  min-height: 58px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.skill-summary-item span {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.skill-summary-item strong {
  color: #0f172a;
  font-size: 22px;
  line-height: 1;
}

.skill-library {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-group {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
  overflow: hidden;
}

.skill-group-head {
  padding: 10px 12px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.skill-group-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.skill-package-list {
  display: flex;
  flex-direction: column;
}

.skill-package-row {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
}

.skill-package-row + .skill-package-row {
  border-top: 1px solid #edf2f7;
}

.skill-package-main {
  min-width: 0;
  flex: 1;
}

.skill-package-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.skill-package-name {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
  line-height: 1.3;
}

.skill-package-desc {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.skill-package-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.skill-package-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.skill-package-stat {
  width: 48px;
  min-height: 46px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.stat-detail-button {
  padding: 0;
  color: inherit;
  font: inherit;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.stat-detail-button:hover {
  border-color: rgba(36, 91, 219, 0.22);
  background: #f8fbff;
  box-shadow: 0 8px 18px rgba(36, 91, 219, 0.06);
  transform: translateY(-1px);
}

.stat-detail-button:focus-visible {
  outline: 2px solid rgba(36, 91, 219, 0.22);
  outline-offset: 2px;
}

.skill-package-stat span {
  color: #94a3b8;
  font-size: 11px;
}

.skill-package-stat strong {
  color: #0f172a;
  font-size: 16px;
  line-height: 1;
}

.action-summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.action-summary-item {
  min-height: 58px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.action-summary-item span {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.action-summary-item strong {
  color: #0f172a;
  font-size: 22px;
  line-height: 1;
}

.action-library {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.action-group {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
  overflow: hidden;
}

.action-group-head {
  padding: 10px 12px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.action-group-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.action-package-list {
  display: flex;
  flex-direction: column;
}

.action-package-row {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
}

.action-package-row + .action-package-row {
  border-top: 1px solid #edf2f7;
}

.action-package-main {
  min-width: 0;
  flex: 1;
}

.action-package-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.action-package-name {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
  line-height: 1.3;
}

.action-package-code {
  color: #64748b;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.3;
}

.action-package-desc {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.action-package-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.action-package-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.action-package-stat {
  width: 48px;
  min-height: 46px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.action-package-stat span {
  color: #94a3b8;
  font-size: 11px;
}

.action-package-stat strong {
  color: #0f172a;
  font-size: 16px;
  line-height: 1;
}

.stat-detail-subtitle {
  margin: -2px 0 10px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.stat-detail-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow: auto;
}

.stat-detail-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.stat-detail-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-detail-label {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
  word-break: break-word;
}

.stat-detail-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.stat-detail-empty {
  padding: 18px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px dashed rgba(148, 163, 184, 0.36);
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
}

.skill-detail-card {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: linear-gradient(145deg, #fff7ed 0%, #f8fafc 100%);
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.skill-detail-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

.skill-detail-meta {
  flex-wrap: wrap;
  color: #475569;
  font-size: 13px;
}

.skill-detail-desc {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.type-tag {
  border-width: 1px;
}

.type-tag--platform_builtin {
  color: #166534;
  border-color: #86efac;
  background: #f0fdf4;
}

.type-tag--stdio {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
}

.type-tag--http {
  color: #92400e;
  border-color: #fcd34d;
  background: #fffbeb;
}

.type-tag--local {
  color: #7c3aed;
  border-color: #c4b5fd;
  background: #f5f3ff;
}

.type-tag--custom {
  color: #0f766e;
  border-color: #99f6e4;
  background: #f0fdfa;
}

@media (max-width: 960px) {
  .audit-grid,
  .skill-summary-row,
  .action-summary-row,
  .dialog-grid {
    grid-template-columns: 1fr;
  }

  .config-grid {
    grid-template-columns: 1fr;
  }

  .config-section--runtime {
    position: static;
  }

  .skill-package-row,
  .skill-package-side,
  .action-package-row,
  .action-package-side {
    flex-direction: column;
    align-items: stretch;
  }

  .skill-package-side,
  .action-package-side {
    gap: 8px;
  }

  .skill-package-stat,
  .action-package-stat {
    width: 100%;
    min-height: 42px;
    flex-direction: row;
    justify-content: space-between;
    padding: 0 12px;
  }

}

@media (max-width: 760px) {
  .hero,
  .switch-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .provider-inline-grid--three,
  .provider-runtime-grid {
    grid-template-columns: 1fr;
  }

  .model-discovery-strip,
  .provider-preset-card,
  .mcp-guard-card {
    margin-left: 0;
  }
}
</style>


