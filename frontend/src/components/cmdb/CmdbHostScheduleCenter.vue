<template>
  <div class="schedule-center-page">
    <div class="neo-tabs theme-blue log-center-tabs trace-center-tabs event-tabs-shell schedule-inner-tabs">
      <button
        v-for="tab in innerTabs"
        :key="tab.key"
        class="neo-tab-btn event-tab schedule-inner-tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <el-icon><component :is="tabIcons[tab.key]" /></el-icon>
        <span class="inner-tab-title">{{ tab.label }}</span>
      </button>
    </div>

    <template v-if="activeTab === 'planner'">
      <div class="planner-grid">
        <div class="glass-card side-card">
          <div class="card-head compact-head">
            <span>常用编排</span>
            <el-tag size="small" type="info">快速起步</el-tag>
          </div>

          <div class="preset-grid">
            <button
              v-for="preset in presets"
              :key="preset.key"
              class="preset-card"
              :class="{ active: scheduleForm.preset_key === preset.key }"
              @click="applyPreset(preset)"
            >
              <div class="preset-title">{{ preset.title }}</div>
              <div class="preset-desc">{{ preset.desc }}</div>
            </button>
          </div>

          <div class="mini-panel">
            <div class="mini-panel-title">平台提醒</div>
            <div class="mini-bullet">到点后会自动创建真实主机任务，沿用 SSH / Ansible 执行链路。</div>
            <div class="mini-bullet">调度器命令：`python manage.py run_host_task_scheduler`。</div>
            <div class="mini-bullet">高风险任务建议启用“跳过重叠执行”，避免并发覆盖。</div>
          </div>
        </div>

        <div class="glass-card main-card">
          <div class="card-head">
            <span>{{ editingId ? '编辑定时编排' : '新建定时编排' }}</span>
            <div class="head-actions">
              <el-tag size="small" type="info">命中 {{ previewState.target_count || 0 }} 台</el-tag>
              <el-button v-if="editingId" size="small" @click="resetEditor()">新建编排</el-button>
            </div>
          </div>

          <div class="task-inline-tip">
            定时编排不会直接连接主机，而是在触发时创建真实任务，任务历史和执行明细会完整保留。
          </div>

          <el-form :model="scheduleForm" label-width="88px" class="task-form schedule-form-compact">
            <div class="form-row">
              <el-form-item label="编排名称" class="form-col">
                <el-input v-model="scheduleForm.name" placeholder="例如：生产主机夜间健康巡检" />
              </el-form-item>
              <el-form-item label="任务类型" class="form-col">
                <el-select v-model="scheduleForm.task_type" style="width: 100%" @change="handleTaskTypeChange">
                  <el-option v-for="option in taskTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item label="编排说明">
              <el-input v-model="scheduleForm.description" placeholder="写明执行窗口、用途和预期结果" />
            </el-form-item>

            <div class="form-row">
              <el-form-item label="执行方式" class="form-col">
                <el-select v-model="scheduleForm.execution_mode" style="width: 100%" :disabled="scheduleForm.task_type === 'run_playbook'">
                  <el-option label="SSH 直连" value="ssh" />
                  <el-option label="Ansible 分发" value="ansible" />
                </el-select>
              </el-form-item>
              <el-form-item label="执行策略" class="form-col">
                <el-radio-group v-model="scheduleForm.execution_strategy">
                  <el-radio label="continue">失败继续</el-radio>
                  <el-radio label="stop_on_error">失败即停</el-radio>
                </el-radio-group>
              </el-form-item>
            </div>

            <el-form-item v-if="scheduleForm.task_type === 'run_command'" label="执行命令">
              <el-input
                v-model="scheduleForm.payload.command"
                type="textarea"
                :rows="5"
                placeholder="例如：hostname && uptime && df -h && free -m"
              />
            </el-form-item>

            <template v-else-if="scheduleForm.task_type === 'run_playbook'">
              <div class="form-row">
                <el-form-item label="Playbook 名称" class="form-col">
                  <el-input v-model="scheduleForm.payload.playbook_name" placeholder="例如：nightly-check.yml" />
                </el-form-item>
                <el-form-item label="超时(秒)" class="form-col">
                  <el-input-number v-model="scheduleForm.timeout_seconds" :min="5" :max="300" style="width: 100%" />
                </el-form-item>
              </div>
              <el-form-item label="Playbook 内容">
                <el-input
                  v-model="scheduleForm.payload.playbook_content"
                  type="textarea"
                  :rows="9"
                  placeholder="- hosts: targets&#10;  gather_facts: false&#10;  tasks: []"
                />
              </el-form-item>
            </template>

            <div v-else-if="scheduleForm.task_type === 'service_status'" class="form-row">
              <el-form-item label="服务名称" class="form-col">
                <el-input v-model="scheduleForm.payload.service_name" placeholder="例如：nginx / docker / sshd" />
              </el-form-item>
              <el-form-item label="超时(秒)" class="form-col">
                <el-input-number v-model="scheduleForm.timeout_seconds" :min="5" :max="120" style="width: 100%" />
              </el-form-item>
            </div>

            <div v-else class="form-row">
              <el-form-item label="超时(秒)" class="form-col">
                <el-input-number v-model="scheduleForm.timeout_seconds" :min="5" :max="120" style="width: 100%" />
              </el-form-item>
              <el-form-item label="方式说明" class="form-col">
                <div class="compact-kv">{{ executionModeHint }}</div>
              </el-form-item>
            </div>

            <div v-if="scheduleForm.task_type === 'run_command'" class="form-row">
              <el-form-item label="超时(秒)" class="form-col">
                <el-input-number v-model="scheduleForm.timeout_seconds" :min="5" :max="120" style="width: 100%" />
              </el-form-item>
              <el-form-item label="方式说明" class="form-col">
                <div class="compact-kv">{{ executionModeHint }}</div>
              </el-form-item>
            </div>

            <el-divider content-position="left">调度规则</el-divider>

            <div class="form-row">
              <el-form-item label="调度类型" class="form-col">
                <el-select v-model="scheduleForm.schedule_type" style="width: 100%">
                  <el-option label="Cron 表达式" value="cron" />
                  <el-option label="固定间隔" value="interval" />
                  <el-option label="单次执行" value="once" />
                </el-select>
              </el-form-item>
              <el-form-item label="时区" class="form-col">
                <el-select v-model="scheduleForm.timezone" style="width: 100%">
                  <el-option label="Asia/Shanghai" value="Asia/Shanghai" />
                  <el-option label="UTC" value="UTC" />
                </el-select>
              </el-form-item>
            </div>

            <div v-if="scheduleForm.schedule_type === 'cron'" class="form-row">
              <el-form-item label="Cron 表达式" class="form-col">
                <el-input v-model="scheduleForm.cron_expression" placeholder="例如：0 2 * * *" />
              </el-form-item>
              <el-form-item label="重叠策略" class="form-col">
                <el-radio-group v-model="scheduleForm.overlap_policy">
                  <el-radio label="skip">跳过重叠执行</el-radio>
                  <el-radio label="allow">允许并发执行</el-radio>
                </el-radio-group>
              </el-form-item>
            </div>

            <div v-else-if="scheduleForm.schedule_type === 'interval'" class="form-row">
              <el-form-item label="间隔秒数" class="form-col">
                <el-input-number v-model="scheduleForm.interval_seconds" :min="60" :max="2592000" style="width: 100%" />
              </el-form-item>
              <el-form-item label="首次执行" class="form-col">
                <el-date-picker
                  v-model="scheduleForm.run_at"
                  type="datetime"
                  value-format="YYYY-MM-DDTHH:mm:ss"
                  style="width: 100%"
                  placeholder="留空则从当前时间开始计算"
                />
              </el-form-item>
            </div>

            <div v-else class="form-row">
              <el-form-item label="执行时间" class="form-col">
                <el-date-picker
                  v-model="scheduleForm.run_at"
                  type="datetime"
                  value-format="YYYY-MM-DDTHH:mm:ss"
                  style="width: 100%"
                  placeholder="请选择单次执行时间"
                />
              </el-form-item>
              <el-form-item label="启用状态" class="form-col">
                <el-switch v-model="scheduleForm.enabled" inline-prompt active-text="启用" inactive-text="停用" />
              </el-form-item>
            </div>

            <div v-if="scheduleForm.schedule_type !== 'once'" class="form-row">
              <el-form-item label="启用状态" class="form-col">
                <el-switch v-model="scheduleForm.enabled" inline-prompt active-text="启用" inactive-text="停用" />
              </el-form-item>
              <el-form-item label="重叠策略" class="form-col">
                <el-radio-group v-model="scheduleForm.overlap_policy">
                  <el-radio label="skip">跳过重叠执行</el-radio>
                  <el-radio label="allow">允许并发执行</el-radio>
                </el-radio-group>
              </el-form-item>
            </div>

            <div class="preview-strip">
              <div class="preview-card">
                <span class="preview-label">下次触发</span>
                <strong>{{ formatDateTime(previewState.next_run_at) }}</strong>
              </div>
              <div class="preview-card">
                <span class="preview-label">命中主机</span>
                <strong>{{ previewState.target_count || 0 }} 台</strong>
              </div>
              <div class="preview-card wide">
                <span class="preview-label">未来 5 次</span>
                <strong>{{ previewListText }}</strong>
              </div>
            </div>

            <el-divider content-position="left">目标主机</el-divider>

            <div class="toolbar">
              <div class="toolbar-left">
                <el-input
                  v-model="targetFilters.search"
                  clearable
                  placeholder="搜索主机名 / IP"
                  style="width: 220px"
                  @keyup.enter="fetchTargets"
                >
                  <template #prefix><el-icon><Search /></el-icon></template>
                </el-input>
                <el-select
                  v-model="targetFilters.business_line"
                  clearable
                  filterable
                  placeholder="业务线"
                  style="width: 140px"
                  @change="handleBusinessChange"
                >
                  <el-option v-for="node in bizNodes" :key="node.id" :label="node.name" :value="node.name" />
                </el-select>
                <el-select
                  v-model="targetFilters.environment"
                  clearable
                  placeholder="环境"
                  style="width: 120px"
                  :disabled="!targetFilters.business_line"
                >
                  <el-option v-for="env in currentEnvOptions" :key="env.id" :label="env.name" :value="env.name" />
                </el-select>
                <el-select v-model="targetFilters.status" clearable placeholder="状态" style="width: 110px">
                  <el-option v-for="option in hostStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
              </div>

              <div class="toolbar-right">
                <el-button size="small" @click="fetchTargets">查询主机</el-button>
                <el-button size="small" @click="resetTargetFilters">重置筛选</el-button>
                <el-button size="small" @click="selectAllCurrent">全选当前</el-button>
                <el-button size="small" @click="clearSelection">清空选择</el-button>
              </div>
            </div>

            <div v-if="selectedHostIds.length" class="selection-strip">
              <span class="selection-pill">已选 {{ selectedHostIds.length }} 台</span>
              <span class="selection-pill success">在线 {{ selectedStats.online }}</span>
              <span class="selection-pill warning">告警 {{ selectedStats.warning }}</span>
              <span class="selection-pill danger">离线 {{ selectedStats.offline }}</span>
            </div>

            <el-table
              ref="hostTableRef"
              size="small"
              :data="availableHosts"
              v-loading="targetLoading"
              row-key="id"
              max-height="300"
              @selection-change="handleSelectionChange"
            >
              <el-table-column type="selection" width="44" reserve-selection />
              <el-table-column prop="hostname" label="主机名" min-width="140" />
              <el-table-column prop="ip_address" label="IP 地址" width="140" />
              <el-table-column prop="business_line" label="业务线" width="120" />
              <el-table-column prop="environment_display" label="环境" width="90" />
              <el-table-column prop="status_display" label="状态" width="90" />
            </el-table>

            <div class="submit-row">
              <div class="submit-tip">建议保存前先预览一次规则，确认时间表达式和目标主机范围。</div>
              <div class="submit-actions">
                <el-button :loading="previewLoading" @click="runPreview">预览规则</el-button>
                <el-button :loading="saving" type="primary" @click="submitSchedule">
                  {{ editingId ? '保存变更' : '创建编排' }}
                </el-button>
              </div>
            </div>
          </el-form>
        </div>
      </div>
    </template>

    <template v-else-if="activeTab === 'list'">
      <div class="glass-card">
        <div class="card-head">
          <span>编排列表</span>
          <div class="head-actions">
            <el-tag size="small" type="info">总计 {{ scheduleTotal }}</el-tag>
            <el-button size="small" @click="fetchSchedules">刷新</el-button>
          </div>
        </div>

        <div class="toolbar history-toolbar">
          <div class="toolbar-left">
            <el-input
              v-model="scheduleFilters.search"
              clearable
              placeholder="搜索编排名称 / 说明"
              style="width: 220px"
              @keyup.enter="fetchSchedules"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select v-model="scheduleFilters.schedule_type" clearable placeholder="调度类型" style="width: 130px" @change="fetchSchedules">
              <el-option label="Cron 表达式" value="cron" />
              <el-option label="固定间隔" value="interval" />
              <el-option label="单次执行" value="once" />
            </el-select>
            <el-select v-model="scheduleFilters.enabled" clearable placeholder="启用状态" style="width: 130px" @change="fetchSchedules">
              <el-option label="已启用" value="true" />
              <el-option label="已停用" value="false" />
            </el-select>
          </div>

          <div class="toolbar-right">
            <el-button size="small" @click="resetScheduleFilters">重置筛选</el-button>
          </div>
        </div>

        <el-table size="small" :data="schedules" v-loading="scheduleLoading" row-key="id">
          <el-table-column label="编排任务" min-width="250">
            <template #default="{ row }">
              <div class="history-name-cell">
                <button type="button" class="history-name-button" @click="editSchedule(row)">
                  <strong>{{ row.name }}</strong>
                </button>
                <div class="history-name-meta">
                  <span>{{ row.task_type_display || '-' }}</span>
                  <span>{{ row.schedule_type_display || '-' }}</span>
                  <span>{{ executionModeLabel(row.execution_mode, row.execution_mode_display) }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="target_count" label="目标" width="82" />
          <el-table-column label="下次执行" width="170">
            <template #default="{ row }">{{ formatDateTime(row.next_run_at) }}</template>
          </el-table-column>
          <el-table-column label="最近结果" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.last_status" size="small" :type="statusTagType(row.last_status)">{{ row.last_status_display }}</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_run_count" label="累计执行" width="92" />
          <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="208" fixed="right">
            <template #default="{ row }">
              <div class="history-row-actions">
                <el-button link type="primary" size="small" @click="editSchedule(row)">编辑</el-button>
                <el-button link type="success" size="small" @click="runNow(row)">立即执行</el-button>
                <el-dropdown trigger="click" @command="command => handleScheduleAction(command, row)">
                  <el-button text size="small" class="history-more-btn">更多</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="toggle">{{ row.enabled ? '停用' : '启用' }}</el-dropdown-item>
                      <el-dropdown-item command="copy">转到任务台</el-dropdown-item>
                      <el-dropdown-item command="delete">删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-row">
          <el-pagination
            v-model:current-page="schedulePage"
            :page-size="20"
            :total="scheduleTotal"
            layout="total, prev, pager, next"
            @current-change="fetchSchedules"
          />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="glass-card history-card">
        <div class="card-head">
          <span>执行记录</span>
          <div class="head-actions">
            <el-tag size="small" type="info">近 7 天自动与手动触发记录</el-tag>
            <el-button size="small" @click="fetchExecutions">刷新</el-button>
          </div>
        </div>

        <div class="toolbar history-toolbar">
          <div class="toolbar-left">
            <el-input
              v-model="executionFilters.search"
              clearable
              placeholder="搜索编排 / 触发人 / 摘要"
              style="width: 240px"
              @keyup.enter="fetchExecutions"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select v-model="executionFilters.status" clearable placeholder="执行结果" style="width: 120px" @change="fetchExecutions">
              <el-option v-for="option in executionStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="executionFilters.trigger_source" clearable placeholder="触发方式" style="width: 120px" @change="fetchExecutions">
              <el-option label="调度器" value="scheduler" />
              <el-option label="手动" value="manual" />
            </el-select>
          </div>

          <div class="toolbar-right">
            <el-button size="small" @click="resetExecutionFilters">重置筛选</el-button>
          </div>
        </div>

        <el-table size="small" :data="executions" v-loading="executionLoading" row-key="id">
          <el-table-column label="编排任务" min-width="240">
            <template #default="{ row }">
              <div class="history-name-cell">
                <button type="button" class="history-name-button" @click="openExecutionDetail(row)">
                  <strong>{{ row.schedule_name }}</strong>
                </button>
                <div class="history-name-meta">
                  <span>{{ row.trigger_source_display || '-' }}</span>
                  <span>{{ row.requested_by || '-' }}</span>
                  <span>{{ row.host_task ? `任务 #${row.host_task}` : '未生成任务' }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="执行结果" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)">{{ row.status_display }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="target_count" label="目标" width="84" />
          <el-table-column label="成功/失败" width="120">
            <template #default="{ row }">{{ row.success_count }}/{{ row.failed_count }}</template>
          </el-table-column>
          <el-table-column prop="summary" label="执行摘要" min-width="260" show-overflow-tooltip />
          <el-table-column label="触发时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.requested_at) }}</template>
          </el-table-column>
          <el-table-column label="关联任务" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <el-button v-if="row.host_task" link type="primary" size="small" @click="openExecutionDetail(row)">
                {{ row.host_task_name || `任务 #${row.host_task}` }}
              </el-button>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openExecutionDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-row">
          <el-pagination
            v-model:current-page="executionPage"
            :page-size="20"
            :total="executionTotal"
            layout="total, prev, pager, next"
            @current-change="fetchExecutions"
          />
        </div>
      </div>
    </template>

    <el-drawer v-model="detailVisible" class="schedule-center-drawer" title="执行记录详情" size="68%" append-to-body>
      <div v-loading="detailLoading" class="schedule-detail-shell">
        <template v-if="detailExecution">
          <div class="detail-heading">
            <div class="detail-heading-main">
              <div class="detail-title-row">
                <strong class="detail-main-title">{{ detailExecution.schedule_name }}</strong>
                <el-tag size="small" effect="plain" :type="statusTagType(detailExecution.status)">
                  {{ detailExecution.status_display }}
                </el-tag>
              </div>
              <div class="detail-subline">
                <span>{{ detailExecution.trigger_source_display || '-' }}</span>
                <span>{{ detailExecution.requested_by || '-' }}</span>
                <span>{{ formatDateTime(detailExecution.requested_at) }}</span>
              </div>
            </div>

            <div class="detail-summary compact">
              <div class="detail-chip">目标 {{ detailExecution.target_count || 0 }}</div>
              <div class="detail-chip">成功 {{ detailExecution.success_count || 0 }}</div>
              <div class="detail-chip">失败 {{ detailExecution.failed_count || 0 }}</div>
            </div>
          </div>

          <div class="schedule-metric-grid compact">
            <div class="schedule-metric-card">
              <span class="schedule-metric-label">目标主机</span>
              <strong>{{ detailExecution.target_count || 0 }}</strong>
            </div>
            <div class="schedule-metric-card success">
              <span class="schedule-metric-label">成功</span>
              <strong>{{ detailExecution.success_count || 0 }}</strong>
            </div>
            <div class="schedule-metric-card danger">
              <span class="schedule-metric-label">失败</span>
              <strong>{{ detailExecution.failed_count || 0 }}</strong>
            </div>
            <div class="schedule-metric-card warning">
              <span class="schedule-metric-label">跳过</span>
              <strong>{{ detailExecution.skipped_count || 0 }}</strong>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section-title">执行摘要</div>
            <div class="detail-kv">{{ detailExecution.summary || '暂无摘要' }}</div>
            <div v-if="detailExecution.error_message" class="detail-kv danger-text">错误信息：{{ detailExecution.error_message }}</div>
          </div>

          <div v-if="detailTask" class="detail-section">
            <div class="detail-section-title">关联任务详情</div>
            <div class="detail-actions">
              <el-button size="small" @click="copyExecutionToTaskDraft(detailExecution, detailTask)">继续编辑</el-button>
              <el-button size="small" @click="saveScheduleTaskAsTemplate(detailTask)">保存为模板</el-button>
            </div>
            <div class="detail-summary">
              <div class="detail-chip"><strong>{{ detailTask.name }}</strong></div>
              <div class="detail-chip">{{ detailTask.task_type_display }}</div>
              <div class="detail-chip">执行方式：{{ executionModeLabel(detailTask.execution_mode, detailTask.execution_mode_display) }}</div>
              <div class="detail-chip">状态：{{ detailTask.status_display }}</div>
              <div class="detail-chip">成功率：{{ taskSuccessRate(detailTask) }}%</div>
            </div>
            <div class="detail-kv">{{ detailTask.summary || detailTask.description || '暂无任务说明' }}</div>

            <el-table size="small" :data="detailTask.executions || []" max-height="420" empty-text="暂无执行明细">
              <el-table-column label="目标资源" min-width="180">
                <template #default="{ row }">
                  <div class="execution-target-cell">
                    <strong>{{ scheduleExecutionTargetName(row) }}</strong>
                    <span>{{ scheduleExecutionTargetMeta(row) || '-' }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="92">
                <template #default="{ row }">
                  <el-tag size="small" :type="statusTagType(row.status)">{{ row.status_display }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="耗时" width="92">
                <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
              </el-table-column>
              <el-table-column label="结果输出" min-width="320">
                <template #default="{ row }">
                  <button type="button" class="output-preview-card" @click="openScheduleExecutionOutput(row)">
                    <span class="output-preview-text">{{ previewScheduleExecutionOutput(row) }}</span>
                    <span class="output-preview-action">点击展开</span>
                  </button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div v-else class="detail-section">
            <div class="detail-section-title">关联任务详情</div>
            <div class="detail-actions">
              <el-button size="small" @click="copyScheduleExecutionBySchedule(detailExecution)">继续编辑</el-button>
            </div>
            <div class="detail-kv">当前执行记录尚未关联真实主机任务，可将原编排转到任务工作台后继续处理。</div>
          </div>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="outputDialogVisible" title="结果输出" width="860px" append-to-body destroy-on-close align-center>
      <template #header>
        <span>{{ outputDialogTitle || '结果输出' }}</span>
      </template>
      <pre class="output-dialog-block">{{ outputDialogContent || '-' }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Calendar, Clock, List, Search } from '@element-plus/icons-vue'
import { useRouteTabState } from '@/composables/useRouteTabState'
import {
  createHostTaskTemplate,
  createHostTaskSchedule,
  deleteHostTaskSchedule,
  getHostTask,
  getHostTaskSchedule,
  getHostTaskScheduleExecution,
  getHostTaskScheduleExecutions,
  getHostTaskSchedules,
  getHostTaskTargets,
  previewHostTaskSchedule,
  runHostTaskScheduleNow,
  toggleHostTaskSchedule,
  updateHostTaskSchedule,
} from '@/api/modules/ops'

const props = defineProps({
  resourceTree: {
    type: Array,
    default: () => [],
  },
})

const router = useRouter()
const TASK_DRAFT_STORAGE_KEY = 'sxdevops.task-center.prefill-draft'

const innerTabs = [
  { key: 'planner', label: '任务编排', desc: '配置时间规则、执行方式与目标主机' },
  { key: 'list', label: '编排列表', desc: '查看启停状态与即时操作' },
  { key: 'history', label: '执行记录', desc: '查看触发结果与关联任务' },
]

const tabIcons = {
  planner: Calendar,
  list: List,
  history: Clock,
}

const taskTypeOptions = [
  { label: '批量命令执行', value: 'run_command' },
  { label: 'Ansible Playbook 执行', value: 'run_playbook' },
  { label: 'SSH 连通性校验', value: 'check_connection' },
  { label: '主机信息刷新', value: 'refresh_metrics' },
  { label: '服务状态巡检', value: 'service_status' },
]

const hostStatusOptions = [
  { label: '在线', value: 'online' },
  { label: '离线', value: 'offline' },
  { label: '告警', value: 'warning' },
]

const executionStatusOptions = [
  { label: '待执行', value: 'pending' },
  { label: '执行中', value: 'running' },
  { label: '执行成功', value: 'success' },
  { label: '部分成功', value: 'partial' },
  { label: '执行失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
]

const presets = [
  {
    key: 'nightly-audit',
    title: '夜间健康巡检',
    desc: '每天凌晨批量巡检主机负载与磁盘状态。',
    description: '适合夜间批量巡检并归档执行结果。',
    task_type: 'run_command',
    execution_mode: 'ansible',
    execution_strategy: 'continue',
    timeout_seconds: 30,
    schedule_type: 'cron',
    cron_expression: '0 2 * * *',
    overlap_policy: 'skip',
    payload: { command: 'hostname && uptime && df -h && free -m' },
  },
  {
    key: 'metrics-refresh',
    title: '资源指标刷新',
    desc: '每 30 分钟刷新一次主机资源指标。',
    description: '适合持续校准主机中心中的运行指标。',
    task_type: 'refresh_metrics',
    execution_mode: 'ssh',
    execution_strategy: 'continue',
    timeout_seconds: 20,
    schedule_type: 'interval',
    interval_seconds: 1800,
    overlap_policy: 'skip',
    payload: {},
  },
  {
    key: 'playbook-once',
    title: '窗口期 Playbook',
    desc: '在维护窗口执行一次标准化 Playbook。',
    description: '适合版本切换前后的集中检查。',
    task_type: 'run_playbook',
    execution_mode: 'ansible',
    execution_strategy: 'stop_on_error',
    timeout_seconds: 120,
    schedule_type: 'once',
    overlap_policy: 'skip',
    payload: {
      playbook_name: 'window-check.yml',
      playbook_content: '- hosts: targets\n  gather_facts: false\n  tasks:\n    - name: ping hosts\n      ping:',
    },
  },
]

const tabState = useRouteTabState({
  tabs: () => innerTabs.map(item => item.key),
  defaultTab: 'planner',
  queryKey: 'scheduleTab',
})

const activeTab = tabState.activeTab
const hostTableRef = ref(null)
const editingId = ref(null)
const saving = ref(false)
const previewLoading = ref(false)
const targetLoading = ref(false)
const scheduleLoading = ref(false)
const executionLoading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const availableHosts = ref([])
const selectedRows = ref([])
const schedules = ref([])
const executions = ref([])
const detailExecution = ref(null)
const detailTask = ref(null)
const outputDialogVisible = ref(false)
const outputDialogTitle = ref('')
const outputDialogContent = ref('')
const schedulePage = ref(1)
const scheduleTotal = ref(0)
const executionPage = ref(1)
const executionTotal = ref(0)

const targetFilters = ref({
  search: '',
  business_line: '',
  environment: '',
  status: '',
})

const scheduleFilters = ref({
  search: '',
  schedule_type: '',
  enabled: '',
})

const executionFilters = ref({
  search: '',
  status: '',
  trigger_source: '',
})

const previewState = ref({
  next_run_at: '',
  next_runs: [],
  target_count: 0,
})

function buildTaskDraftFromSchedule(schedule = {}) {
  const snapshot = Array.isArray(schedule.target_snapshot) ? schedule.target_snapshot : []
  return {
    name: schedule.name || '',
    description: schedule.description || '',
    target_type: 'host',
    task_type: schedule.task_type || 'run_command',
    execution_mode: schedule.execution_mode || (schedule.task_type === 'run_playbook' ? 'ansible' : 'ssh'),
    execution_strategy: schedule.execution_strategy || 'continue',
    timeout_seconds: schedule.timeout_seconds || 30,
    payload: { ...(schedule.payload || {}) },
    target_refs: snapshot.filter(item => item?.id).map(item => ({ source: 'host', id: item.id })),
    target_hosts: snapshot,
    trigger_source: 'manual',
    source_context: {
      source: 'task_schedule',
      source_schedule_id: schedule.id,
      source_schedule_name: schedule.name || '',
      request_summary: schedule.description || '',
    },
  }
}

function buildTaskDraftFromTask(task = {}, source = {}) {
  const snapshot = Array.isArray(task.target_snapshot) ? task.target_snapshot : []
  return {
    name: task.name || '',
    description: task.description || '',
    target_type: task.target_type || 'host',
    task_type: task.task_type || 'run_command',
    execution_mode: task.execution_mode || 'ssh',
    execution_strategy: task.execution_strategy || 'continue',
    timeout_seconds: task.timeout_seconds || 30,
    payload: { ...(task.payload || {}) },
    target_refs: snapshot
      .filter(item => item?.id)
      .map(item => (item.source === 'task_resource'
        ? { source: 'task_resource', id: item.resource_id || item.id }
        : { source: 'host', id: item.id })),
    target_hosts: snapshot,
    trigger_source: 'manual',
    source_context: {
      ...(task.source_context || {}),
      ...source,
    },
  }
}

function openTaskWorkbenchWithDraft(taskDraft) {
  sessionStorage.setItem(TASK_DRAFT_STORAGE_KEY, JSON.stringify(taskDraft))
  router.push({ path: '/tasks/workbench', query: { taskDraft: String(Date.now()) } })
}

function defaultPayload() {
  return {
    command: '',
    service_name: '',
    playbook_name: '',
    playbook_content: '',
  }
}

function defaultScheduleForm() {
  return {
    preset_key: 'nightly-audit',
    name: '夜间健康巡检',
    description: '适合夜间批量巡检并归档执行结果。',
    task_type: 'run_command',
    payload: {
      ...defaultPayload(),
      command: 'hostname && uptime && df -h && free -m',
    },
    execution_mode: 'ansible',
    execution_strategy: 'continue',
    timeout_seconds: 30,
    schedule_type: 'cron',
    cron_expression: '0 2 * * *',
    interval_seconds: 1800,
    run_at: '',
    timezone: 'Asia/Shanghai',
    overlap_policy: 'skip',
    enabled: true,
  }
}

const scheduleForm = ref(defaultScheduleForm())
const bizNodes = computed(() => props.resourceTree.filter(item => item.node_type === 'biz'))
const currentEnvOptions = computed(() => (
  bizNodes.value.find(item => item.name === targetFilters.value.business_line)?.children || []
))
const selectedHostIds = computed(() => selectedRows.value.map(item => item.id))
const selectedStats = computed(() => (
  selectedRows.value.reduce((summary, item) => {
    if (item.status === 'online') summary.online += 1
    if (item.status === 'warning') summary.warning += 1
    if (item.status === 'offline') summary.offline += 1
    return summary
  }, { online: 0, offline: 0, warning: 0 })
))
const previewListText = computed(() => (previewState.value.next_runs || []).map(formatDateTime).join(' / ') || '-')
const executionModeHint = computed(() => {
  if (scheduleForm.value.task_type === 'run_playbook') return 'Playbook 仅支持 Ansible 执行。'
  if (scheduleForm.value.execution_mode === 'ansible') return 'Ansible 适合标准化批量分发。'
  return 'SSH 适合少量主机快速诊断。'
})

function executionModeLabel(mode, display) {
  return display || (mode === 'ansible' ? 'Ansible 分发' : 'SSH 直连')
}

function statusTagType(status) {
  if (status === 'success') return 'success'
  if (status === 'partial' || status === 'running') return 'warning'
  if (status === 'failed' || status === 'canceled') return 'danger'
  return 'info'
}

function formatDateTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
}

function taskSuccessRate(task) {
  if (!task?.target_count) return 0
  return Math.round(((task.success_count || 0) / task.target_count) * 1000) / 10
}

function formatDuration(value) {
  const duration = Number(value || 0)
  if (!Number.isFinite(duration) || duration <= 0) return '0ms'
  if (duration < 1000) return `${duration}ms`
  if (duration < 60000) return `${(duration / 1000).toFixed(duration >= 10000 ? 0 : 1)}s`
  const minutes = Math.floor(duration / 60000)
  const seconds = Math.round((duration % 60000) / 1000)
  return seconds ? `${minutes}min ${seconds}s` : `${minutes}min`
}

function scheduleExecutionTargetName(row) {
  return row?.host_name || row?.host_ip || row?.target_id || '-'
}

function scheduleExecutionTargetMeta(row) {
  return row?.host_ip || ''
}

function scheduleExecutionOutputContent(row) {
  return row?.error_message || row?.output || '-'
}

function previewScheduleExecutionOutput(row) {
  const normalized = scheduleExecutionOutputContent(row).replace(/\s+/g, ' ').trim()
  if (!normalized) return '-'
  return normalized.length > 150 ? `${normalized.slice(0, 150)}...` : normalized
}

function openScheduleExecutionOutput(row) {
  outputDialogTitle.value = `结果输出 · ${scheduleExecutionTargetName(row)}`
  outputDialogContent.value = scheduleExecutionOutputContent(row)
  outputDialogVisible.value = true
}

function normalizePayloadByType(taskType, source = {}) {
  if (taskType === 'run_command') return { command: (source.command || '').trim() }
  if (taskType === 'run_playbook') {
    return {
      playbook_name: (source.playbook_name || '').trim(),
      playbook_content: (source.playbook_content || '').trim(),
    }
  }
  if (taskType === 'service_status') return { service_name: (source.service_name || '').trim() }
  return {}
}

function validatePayload() {
  const payload = normalizePayloadByType(scheduleForm.value.task_type, scheduleForm.value.payload || {})
  if (scheduleForm.value.task_type === 'run_command' && !payload.command) {
    ElMessage.warning('请填写执行命令')
    return null
  }
  if (scheduleForm.value.task_type === 'run_playbook' && !payload.playbook_content) {
    ElMessage.warning('请填写 Playbook 内容')
    return null
  }
  if (scheduleForm.value.task_type === 'service_status' && !payload.service_name) {
    ElMessage.warning('请填写服务名称')
    return null
  }
  return payload
}

function buildSubmitPayload() {
  const payload = validatePayload()
  if (!payload) return null
  if (!scheduleForm.value.name) {
    ElMessage.warning('请填写编排名称')
    return null
  }
  return {
    name: scheduleForm.value.name,
    description: scheduleForm.value.description,
    task_type: scheduleForm.value.task_type,
    payload,
    selection_filters: { ...targetFilters.value },
    target_host_ids: selectedHostIds.value,
    execution_mode: scheduleForm.value.task_type === 'run_playbook' ? 'ansible' : scheduleForm.value.execution_mode,
    execution_strategy: scheduleForm.value.execution_strategy,
    timeout_seconds: scheduleForm.value.timeout_seconds,
    schedule_type: scheduleForm.value.schedule_type,
    cron_expression: scheduleForm.value.schedule_type === 'cron' ? scheduleForm.value.cron_expression : '',
    interval_seconds: scheduleForm.value.schedule_type === 'interval' ? scheduleForm.value.interval_seconds : null,
    run_at: ['once', 'interval'].includes(scheduleForm.value.schedule_type) ? (scheduleForm.value.run_at || null) : null,
    timezone: scheduleForm.value.timezone,
    overlap_policy: scheduleForm.value.overlap_policy,
    enabled: scheduleForm.value.enabled,
  }
}

function handleSelectionChange(rows) {
  selectedRows.value = rows
}

function handleBusinessChange() {
  targetFilters.value.environment = ''
}

function handleTaskTypeChange() {
  if (scheduleForm.value.task_type === 'run_playbook') scheduleForm.value.execution_mode = 'ansible'
  if (scheduleForm.value.task_type !== 'run_command') scheduleForm.value.payload.command = ''
  if (scheduleForm.value.task_type !== 'run_playbook') {
    scheduleForm.value.payload.playbook_name = ''
    scheduleForm.value.payload.playbook_content = ''
  }
  if (scheduleForm.value.task_type !== 'service_status') scheduleForm.value.payload.service_name = ''
}

function applyPreset(preset) {
  scheduleForm.value = {
    ...defaultScheduleForm(),
    preset_key: preset.key,
    name: preset.title,
    description: preset.description || preset.desc || '',
    task_type: preset.task_type,
    payload: { ...defaultPayload(), ...(preset.payload || {}) },
    execution_mode: preset.execution_mode,
    execution_strategy: preset.execution_strategy,
    timeout_seconds: preset.timeout_seconds,
    schedule_type: preset.schedule_type,
    cron_expression: preset.cron_expression || '',
    interval_seconds: preset.interval_seconds || 1800,
    run_at: '',
    timezone: 'Asia/Shanghai',
    overlap_policy: preset.overlap_policy,
    enabled: true,
  }
  editingId.value = null
  previewState.value = { next_run_at: '', next_runs: [], target_count: 0 }
}

function resetEditor(switchTab = true) {
  applyPreset(presets[0])
  clearSelection()
  if (switchTab) activeTab.value = 'planner'
}

function fillSelectionBySnapshot(snapshot = []) {
  const ids = new Set(snapshot.map(item => item.id))
  selectedRows.value = availableHosts.value.filter(item => ids.has(item.id))
  hostTableRef.value?.clearSelection()
  availableHosts.value.forEach((row) => {
    if (ids.has(row.id)) hostTableRef.value?.toggleRowSelection(row, true)
  })
}

function editSchedule(row) {
  editingId.value = row.id
  scheduleForm.value = {
    preset_key: row.id,
    name: row.name,
    description: row.description || '',
    task_type: row.task_type,
    payload: { ...defaultPayload(), ...(row.payload || {}) },
    execution_mode: row.execution_mode || (row.task_type === 'run_playbook' ? 'ansible' : 'ssh'),
    execution_strategy: row.execution_strategy || 'continue',
    timeout_seconds: row.timeout_seconds || 15,
    schedule_type: row.schedule_type,
    cron_expression: row.cron_expression || '',
    interval_seconds: row.interval_seconds || 1800,
    run_at: row.run_at || '',
    timezone: row.timezone || 'Asia/Shanghai',
    overlap_policy: row.overlap_policy || 'skip',
    enabled: row.enabled,
  }
  previewState.value = {
    next_run_at: row.next_run_at,
    next_runs: row.next_runs_preview || [],
    target_count: row.target_count || 0,
  }
  activeTab.value = 'planner'
  fetchTargets().then(() => fillSelectionBySnapshot(row.target_snapshot || []))
}

async function copyScheduleToTaskDraft(row) {
  try {
    const schedule = row?.payload && Array.isArray(row?.target_snapshot) ? row : await getHostTaskSchedule(row.id)
    openTaskWorkbenchWithDraft(buildTaskDraftFromSchedule(schedule))
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载编排草稿失败')
  }
}

async function copyExecutionToTaskDraft(execution, task) {
  try {
    const sourceTask = task?.payload ? task : await getHostTask(task.id)
    openTaskWorkbenchWithDraft(buildTaskDraftFromTask(sourceTask, {
      source: 'task_schedule_execution',
      source_execution_id: execution?.id,
      source_task_id: sourceTask.id,
      request_summary: sourceTask.description || sourceTask.summary || '',
    }))
    detailVisible.value = false
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '载入任务草稿失败')
  }
}

async function copyScheduleExecutionBySchedule(execution) {
  const scheduleId = execution?.schedule
  if (!scheduleId) {
    ElMessage.warning('当前记录未关联编排')
    return
  }
  try {
    const schedule = await getHostTaskSchedule(scheduleId)
    openTaskWorkbenchWithDraft(buildTaskDraftFromSchedule(schedule))
    detailVisible.value = false
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载编排草稿失败')
  }
}

async function saveScheduleTaskAsTemplate(task) {
  const sourceTask = task?.payload ? task : await getHostTask(task.id)
  const payload = normalizePayloadByType(sourceTask.task_type, sourceTask.payload || {})
  let templateName = sourceTask.name || ''
  try {
    const { value } = await ElMessageBox.prompt('请输入模板名称', '保存为模板', {
      confirmButtonText: '保存为模板',
      cancelButtonText: '取消',
      inputValue: templateName,
      inputValidator: value => !!String(value || '').trim(),
    })
    templateName = String(value || '').trim()
  } catch {
    return
  }
  try {
    await createHostTaskTemplate({
      name: templateName,
      target_type: sourceTask.target_type || 'host',
      task_type: sourceTask.task_type,
      description: sourceTask.description || '',
      payload,
      execution_mode: sourceTask.execution_mode,
      execution_strategy: sourceTask.execution_strategy || 'continue',
      timeout_seconds: sourceTask.timeout_seconds || 30,
    })
    ElMessage.success('模板已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存模板失败')
  }
}

async function fetchTargets() {
  targetLoading.value = true
  try {
    const res = await getHostTaskTargets({ ...targetFilters.value })
    availableHosts.value = Array.isArray(res) ? res : (res.results || [])
  } catch {
    ElMessage.error('加载目标主机失败')
  } finally {
    targetLoading.value = false
  }
}

async function fetchSchedules() {
  scheduleLoading.value = true
  try {
    const res = await getHostTaskSchedules({
      page: schedulePage.value,
      search: scheduleFilters.value.search || undefined,
      schedule_type: scheduleFilters.value.schedule_type || undefined,
      enabled: scheduleFilters.value.enabled || undefined,
    })
    schedules.value = res.results || res || []
    scheduleTotal.value = res.count || schedules.value.length
  } catch {
    ElMessage.error('加载编排列表失败')
  } finally {
    scheduleLoading.value = false
  }
}

async function fetchExecutions() {
  executionLoading.value = true
  try {
    const res = await getHostTaskScheduleExecutions({
      page: executionPage.value,
      search: executionFilters.value.search || undefined,
      status: executionFilters.value.status || undefined,
      trigger_source: executionFilters.value.trigger_source || undefined,
    })
    executions.value = res.results || res || []
    executionTotal.value = res.count || executions.value.length
  } catch {
    ElMessage.error('加载执行记录失败')
  } finally {
    executionLoading.value = false
  }
}

async function openExecutionDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detailExecution.value = row
  detailTask.value = null
  try {
    const execution = await getHostTaskScheduleExecution(row.id)
    detailExecution.value = execution
    if (execution?.host_task) {
      try {
        detailTask.value = await getHostTask(execution.host_task)
      } catch {
        ElMessage.warning('已打开执行记录，但关联任务详情加载失败')
      }
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载执行记录详情失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function runPreview() {
  const payload = buildSubmitPayload()
  if (!payload) return
  previewLoading.value = true
  try {
    previewState.value = await previewHostTaskSchedule(payload)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '预览编排失败')
  } finally {
    previewLoading.value = false
  }
}

async function submitSchedule() {
  const payload = buildSubmitPayload()
  if (!payload) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateHostTaskSchedule(editingId.value, payload)
    } else {
      await createHostTaskSchedule(payload)
    }
    ElMessage.success(editingId.value ? '编排已更新' : '编排已创建')
    await Promise.all([fetchSchedules(), fetchExecutions()])
    resetEditor(false)
    activeTab.value = 'list'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存编排失败')
  } finally {
    saving.value = false
  }
}

async function toggleSchedule(row) {
  try {
    await toggleHostTaskSchedule(row.id)
    ElMessage.success(row.enabled ? '编排已停用' : '编排已启用')
    await Promise.all([fetchSchedules(), fetchExecutions()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '切换编排状态失败')
  }
}

async function runNow(row) {
  try {
    await ElMessageBox.confirm(`确认立即执行编排“${row.name}”吗？`, '立即执行', {
      type: 'warning',
      confirmButtonText: '立即执行',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await runHostTaskScheduleNow(row.id)
    ElMessage.success('编排已触发，正在后台创建任务')
    await Promise.all([fetchSchedules(), fetchExecutions()])
    activeTab.value = 'history'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '触发编排失败')
  }
}

async function removeSchedule(row) {
  try {
    await ElMessageBox.confirm(`确认删除编排“${row.name}”吗？`, '删除编排', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteHostTaskSchedule(row.id)
    ElMessage.success('编排已删除')
    await Promise.all([fetchSchedules(), fetchExecutions()])
    if (editingId.value === row.id) resetEditor()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '删除编排失败')
  }
}

function selectAllCurrent() {
  hostTableRef.value?.clearSelection()
  availableHosts.value.forEach(row => hostTableRef.value?.toggleRowSelection(row, true))
}

function clearSelection() {
  hostTableRef.value?.clearSelection()
  selectedRows.value = []
}

function resetTargetFilters() {
  targetFilters.value = { search: '', business_line: '', environment: '', status: '' }
  clearSelection()
  fetchTargets()
}

function resetScheduleFilters() {
  scheduleFilters.value = { search: '', schedule_type: '', enabled: '' }
  schedulePage.value = 1
  fetchSchedules()
}

function resetExecutionFilters() {
  executionFilters.value = { search: '', status: '', trigger_source: '' }
  executionPage.value = 1
  fetchExecutions()
}

function handleScheduleAction(command, row) {
  if (command === 'toggle') {
    toggleSchedule(row)
    return
  }
  if (command === 'copy') {
    copyScheduleToTaskDraft(row)
    return
  }
  if (command === 'delete') {
    removeSchedule(row)
  }
}

onMounted(async () => {
  applyPreset(presets[0])
  await Promise.all([fetchTargets(), fetchSchedules(), fetchExecutions(), runPreview()])
})
</script>

<style scoped>
.schedule-center-page {
  --sc-border: rgba(15, 23, 42, 0.08);
  --sc-border-strong: rgba(59, 130, 246, 0.18);
  --sc-panel: linear-gradient(180deg, #ffffff 0%, #f8fbfc 100%);
  --sc-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  --sc-shadow-hover: 0 14px 30px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.schedule-inner-tabs {
  display: flex;
  width: 100%;
  align-self: stretch;
  margin-bottom: 2px;
  padding: 4px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.schedule-inner-tab-btn {
  min-height: 38px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  gap: 6px;
}

.schedule-inner-tab-btn:hover {
  background: rgba(51, 112, 255, 0.06);
}

.schedule-inner-tab-btn.active {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.inner-tab-title {
  font-size: 13px;
  font-weight: 700;
  color: inherit;
  line-height: 1.1;
}

.glass-card {
  background: var(--sc-panel);
  border: 1px solid var(--sc-border);
  border-radius: 14px;
  box-shadow: var(--sc-shadow);
  padding: 14px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  font-weight: 600;
  color: #0f172a;
}

.compact-head {
  margin-bottom: 8px;
}

.planner-grid {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 12px;
}

.side-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.preset-grid {
  display: grid;
  gap: 8px;
}

.preset-card {
  padding: 12px;
  border: 1px solid var(--sc-border);
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #fafcff 100%);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.preset-card:hover {
  border-color: var(--sc-border-strong);
  box-shadow: var(--sc-shadow-hover);
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  transform: translateY(-1px);
}

.preset-card.active {
  border-color: rgba(37, 99, 235, 0.22);
  background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.preset-title {
  color: #0f172a;
  font-weight: 600;
}

.preset-desc,
.task-inline-tip {
  margin-top: 4px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.task-inline-tip {
  margin-bottom: 8px;
  padding: 7px 10px;
  border-radius: 12px;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.06) 0%, rgba(14, 165, 233, 0.03) 100%);
  border: 1px solid rgba(37, 99, 235, 0.1);
}

.mini-panel {
  padding: 14px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.mini-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 10px;
}

.mini-bullet {
  position: relative;
  padding-left: 14px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.6;
}

.mini-bullet::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #60a5fa;
}

.task-form {
  margin-top: 2px;
}

.schedule-form-compact :deep(.el-form-item) {
  margin-bottom: 12px;
}

.form-row {
  display: flex;
  gap: 10px;
}

.form-col {
  flex: 1;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  padding: 6px 8px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92) 0%, rgba(255, 255, 255, 0.96) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.toolbar :deep(.el-input__wrapper),
.toolbar :deep(.el-select__wrapper) {
  min-height: 28px;
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.12) inset;
  background: rgba(255, 255, 255, 0.94);
}

.toolbar :deep(.el-tag) {
  height: 26px;
  border-radius: 8px;
}

.toolbar :deep(.el-input__wrapper:hover),
.toolbar :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.16) inset;
}

.toolbar-right :deep(.el-button),
.head-actions :deep(.el-button) {
  min-height: 26px;
  padding: 0 9px;
  border-radius: 8px;
  font-weight: 500;
}

.toolbar-right :deep(.el-button:not(.el-button--primary)),
.head-actions :deep(.el-button:not(.el-button--primary)) {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  color: #475569;
  box-shadow: none;
}

.toolbar-right :deep(.el-button:not(.is-link):hover),
.head-actions :deep(.el-button:not(.is-link):hover) {
  border-color: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
  background: #f8fbff;
}

.selection-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.selection-pill {
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 11px;
}

.selection-pill.success {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.selection-pill.warning {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.selection-pill.danger {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.submit-row {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.submit-tip {
  color: #64748b;
  font-size: 11px;
}

.submit-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.template-payload-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.preview-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}

.preview-card {
  padding: 10px 12px;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.preview-label {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 11px;
}

.compact-kv {
  padding: 5px 0;
  min-height: 28px;
  color: #475569;
  font-size: 12px;
  line-height: 1.55;
}

.history-toolbar {
  margin: 6px 0;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.history-row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  flex-wrap: nowrap;
}

.history-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.history-name-button {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.history-name-button:hover strong {
  color: #2563eb;
}

.history-name-button:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.22);
  outline-offset: 2px;
  border-radius: 8px;
}

.history-name-cell strong {
  color: #0f172a;
  font-size: 12px;
  line-height: 1.35;
  transition: color 0.2s ease;
}

.history-name-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
}

.history-more-btn {
  color: #64748b;
  padding: 4px 8px;
  border-radius: 999px;
}

.schedule-center-page :deep(.history-more-btn.el-button:hover) {
  color: #2563eb;
  background: rgba(37, 99, 235, 0.08);
}

.schedule-detail-shell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-heading-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-main-title {
  color: #0f172a;
  font-size: 15px;
  line-height: 1.3;
}

.detail-subline {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 11px;
}

.detail-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 0;
}

.detail-summary.compact {
  gap: 4px;
  justify-content: flex-end;
}

.detail-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.12);
  color: #1e3a8a;
  font-size: 11px;
  line-height: 1.4;
}

.schedule-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.schedule-metric-grid.compact {
  gap: 5px;
}

.schedule-metric-card {
  padding: 8px 10px;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.schedule-metric-card.success {
  background: linear-gradient(180deg, #f0fdf4 0%, #f7fee7 100%);
}

.schedule-metric-card.danger {
  background: linear-gradient(180deg, #fff1f2 0%, #fef2f2 100%);
}

.schedule-metric-card.warning {
  background: linear-gradient(180deg, #fffbeb 0%, #fefce8 100%);
}

.schedule-metric-label {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 11px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 0;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-section-title {
  margin-bottom: 0;
  color: #0f172a;
  font-size: 11px;
  font-weight: 600;
}

.detail-kv {
  color: #475569;
  font-size: 11px;
  line-height: 1.5;
}

.execution-target-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.execution-target-cell strong {
  color: #0f172a;
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-target-cell span {
  color: #64748b;
  font-size: 11px;
}

.output-preview-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-radius: 12px;
  background: #0f172a;
  color: #e2e8f0;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
  cursor: pointer;
}

.output-preview-card:hover {
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.32);
}

.output-preview-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.45;
}

.output-preview-action {
  flex: none;
}

.danger-text {
  color: #b91c1c;
}

.output-block {
  max-height: 120px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 9px 10px;
  border-radius: 12px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: Consolas, Monaco, monospace;
  font-size: 11px;
  line-height: 1.55;
}

.output-dialog-block {
  margin: 0;
  max-height: 62vh;
  overflow: auto;
  white-space: pre;
  word-break: normal;
  padding: 14px 16px;
  border-radius: 14px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
}

.schedule-center-page :deep(.el-input__wrapper),
.schedule-center-page :deep(.el-textarea__inner),
.schedule-center-page :deep(.el-select__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.16) inset;
  background: rgba(255, 255, 255, 0.92);
}

.schedule-center-page :deep(.el-input__wrapper:hover),
.schedule-center-page :deep(.el-select__wrapper:hover),
.schedule-center-page :deep(.el-textarea__inner:hover) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.18) inset;
}

.schedule-center-page :deep(.el-input__wrapper.is-focus),
.schedule-center-page :deep(.el-select__wrapper.is-focused),
.schedule-center-page :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.22) inset;
}

.schedule-center-page :deep(.el-button) {
  border-radius: 10px;
}

.schedule-center-page :deep(.el-table) {
  --el-table-border-color: rgba(148, 163, 184, 0.16);
  --el-table-header-bg-color: #f8fafc;
  --el-table-row-hover-bg-color: #f8fbff;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 12px;
  overflow: hidden;
}

.schedule-center-page :deep(.el-table th.el-table__cell) {
  color: #475569;
  font-weight: 600;
  background: #f8fafc;
}

.schedule-center-page :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.schedule-center-page :deep(.schedule-center-drawer) {
  height: 100vh;
  max-height: 100vh;
}

.schedule-center-page :deep(.schedule-center-drawer .el-drawer__header) {
  padding: 14px 18px 10px;
}

.schedule-center-page :deep(.schedule-center-drawer .el-drawer__body) {
  min-height: calc(100vh - 56px);
  max-height: calc(100vh - 56px);
  overflow-y: auto;
  padding: 14px 16px 16px;
  background: #f8fafc;
}

@media (max-width: 1100px) {
  .planner-grid,
  .preview-strip,
  .schedule-metric-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .form-row,
  .submit-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
