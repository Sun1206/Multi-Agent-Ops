<template>
  <div class="fade-in operation-audit-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row">
          <span class="release-header-icon"><el-icon><DocumentChecked /></el-icon></span>
          <h2>操作审计</h2>
          <p class="page-inline-desc">查看平台关键写操作、执行动作、审批与配置变更记录。</p>
        </div>
      </div>
    </section>

    <div class="audit-grid operation-audit-stats">
      <div class="audit-card audit-card--inline">
        <div class="stat-label">当前结果</div>
        <div class="stat-value">{{ total }}</div>
      </div>
      <div class="audit-card audit-card--inline audit-card--success">
        <div class="stat-label">成功</div>
        <div class="stat-value">{{ visibleSummary.success }}</div>
      </div>
      <div class="audit-card audit-card--inline audit-card--warning">
        <div class="stat-label">待处理 / 部分成功</div>
        <div class="stat-value">{{ visibleSummary.pending }}</div>
      </div>
      <div class="audit-card audit-card--inline audit-card--danger">
        <div class="stat-label">失败</div>
        <div class="stat-value">{{ visibleSummary.failed }}</div>
      </div>
    </div>

    <div class="workbench-card operation-audit-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">审计记录</span>
          <span class="toolbar-desc">按时间、结果、操作人与资源快速定位平台变更链路。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button class="filter-refresh-btn" :loading="loading" @click="fetchAudits">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button v-if="canManageAudit" type="danger" plain @click="cleanupVisible = true">
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history operation-audit-toolbar">
        <div class="workbench-toolbar-left">
          <el-input v-model="filters.search" placeholder="搜索标题 / 资源 / 操作人" clearable style="width: 220px" @keyup.enter="handleSearch" />
          <el-select v-model="filters.result" placeholder="结果" clearable style="width: 104px" @change="handleSearch">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="部分成功" value="partial" />
            <el-option label="待处理" value="pending" />
          </el-select>
          <el-select v-model="filters.module" placeholder="模块" clearable style="width: 104px" @change="handleSearch">
            <el-option v-for="item in moduleOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-input v-model="filters.actor" placeholder="操作人" clearable style="width: 112px" @keyup.enter="handleSearch" />
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            range-separator="至"
            class="audit-time-range"
            @change="handleSearch"
          />
        </div>
        <div class="workbench-toolbar-right">
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <el-table :data="audits" stripe v-loading="loading" style="width: 100%">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column prop="title" label="操作" min-width="220" show-overflow-tooltip />
        <el-table-column label="模块" width="120">
          <template #default="{ row }">{{ moduleLabel(row.module) }}</template>
        </el-table-column>
        <el-table-column label="动作" width="130">
          <template #default="{ row }">{{ row.action || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="140">
          <template #default="{ row }">{{ row.actor_display || row.actor_username || 'system' }}</template>
        </el-table-column>
        <el-table-column label="资源" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ resourceLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="resultTone(row.result)">{{ resultLabel(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">{{ row.source_type_display || row.source_type || '-' }}</template>
        </el-table-column>
        <el-table-column label="请求" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ requestLabel(row) }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          v-model:current-page="page"
          :page-size="20"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchAudits"
        />
      </div>
    </div>

    <el-dialog v-model="cleanupVisible" title="批量删除操作审计" width="460px" destroy-on-close>
      <div class="cleanup-body">
        <p>将删除指定时间之前的操作审计记录，外部事件源接入数据不会被清理。</p>
        <el-date-picker
          v-model="cleanupBeforeAt"
          type="datetime"
          placeholder="选择截止时间"
          style="width: 100%"
        />
      </div>
      <template #footer>
        <el-button @click="cleanupVisible = false">取消</el-button>
        <el-button type="danger" :loading="cleanupLoading" @click="handleCleanup">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, DocumentChecked, RefreshRight } from '@element-plus/icons-vue'
import { getOperationAuditEvents, pruneOperationAuditEvents } from '@/api/modules/eventwall'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const loading = ref(false)
const cleanupLoading = ref(false)
const cleanupVisible = ref(false)
const cleanupBeforeAt = ref(null)
const audits = ref([])
const total = ref(0)
const page = ref(1)
const timeRange = ref([])
const filters = reactive({
  search: '',
  result: '',
  module: '',
  actor: '',
})
const canManageAudit = computed(() => authStore.hasPermission('rbac.audit.manage'))
const moduleOptions = [
  { label: '运维', value: 'ops' },
  { label: 'CMDB', value: 'cmdb' },
  { label: 'SQL 审计', value: 'sqlaudit' },
  { label: '工具市场', value: 'marketplace' },
  { label: '用户权限', value: 'rbac' },
  { label: 'AIOps', value: 'aiops' },
  { label: '事件墙', value: 'eventwall' },
]
const visibleSummary = computed(() => ({
  success: audits.value.filter(item => item.result === 'success').length,
  failed: audits.value.filter(item => item.result === 'failed').length,
  pending: audits.value.filter(item => ['pending', 'partial'].includes(item.result)).length,
}))

function buildParams() {
  const params = { page: page.value }
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.result) params.result = filters.result
  if (filters.module) params.module = filters.module
  if (filters.actor.trim()) params.actor = filters.actor.trim()
  if (Array.isArray(timeRange.value) && timeRange.value.length === 2) {
    params.start_at = new Date(timeRange.value[0]).toISOString()
    params.end_at = new Date(timeRange.value[1]).toISOString()
  }
  return params
}

async function fetchAudits() {
  loading.value = true
  try {
    const response = await getOperationAuditEvents(buildParams())
    audits.value = response.results || response || []
    total.value = response.count || audits.value.length
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchAudits()
}

function resetFilters() {
  filters.search = ''
  filters.result = ''
  filters.module = ''
  filters.actor = ''
  timeRange.value = []
  handleSearch()
}

async function handleCleanup() {
  if (!cleanupBeforeAt.value) {
    ElMessage.warning('请选择截止时间')
    return
  }
  const cutoff = new Date(cleanupBeforeAt.value)
  if (Number.isNaN(cutoff.getTime())) {
    ElMessage.warning('截止时间无效')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除 ${formatTime(cutoff)} 之前的操作审计记录吗？该操作不可恢复。`,
      '确认批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  cleanupLoading.value = true
  try {
    const response = await pruneOperationAuditEvents({ before_at: cutoff.toISOString() })
    ElMessage.success(`已删除 ${response.deleted || 0} 条操作审计记录`)
    cleanupVisible.value = false
    cleanupBeforeAt.value = null
    page.value = 1
    await fetchAudits()
  } finally {
    cleanupLoading.value = false
  }
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

function moduleLabel(module) {
  return {
    ops: '运维',
    cmdb: 'CMDB',
    sqlaudit: 'SQL 审计',
    marketplace: '工具市场',
    rbac: '用户权限',
    aiops: 'AIOps',
    eventwall: '事件墙',
  }[module] || module || '-'
}

function resultLabel(row) {
  return row.result_display || {
    success: '成功',
    failed: '失败',
    partial: '部分成功',
    pending: '待处理',
    rejected: '已拒绝',
  }[row.result] || row.result || '-'
}

function resultTone(result) {
  return {
    success: 'success',
    failed: 'danger',
    partial: 'warning',
    pending: 'warning',
    rejected: 'info',
  }[result] || 'info'
}

function resourceLabel(row) {
  return [row.resource_type, row.resource_name || row.resource_id].filter(Boolean).join(' / ') || '-'
}

function requestLabel(row) {
  return [row.request_method, row.source_path].filter(Boolean).join(' ') || row.ip_address || '-'
}

onMounted(fetchAudits)
</script>

<style scoped>
.operation-audit-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel {
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(250,252,255,.96) 100%);
  border: 1px solid rgba(15,23,42,.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
  padding: 14px 16px;
}

.hero {
  margin-bottom: 0;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36,91,219,.09);
}

.release-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.release-hero-title-row h2 {
  color: #0f172a;
  font-size: 23px;
  margin: 0;
}

.release-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%);
  border: 1px solid rgba(36,91,219,.12);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}

.page-inline-desc {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
}

.operation-audit-stats {
  gap: 10px;
}

.operation-audit-toolbar {
  margin-top: 0;
  flex-wrap: nowrap;
  overflow-x: auto;
}

.operation-audit-toolbar .workbench-toolbar-left,
.operation-audit-toolbar .workbench-toolbar-right {
  flex-wrap: nowrap;
}

.operation-audit-toolbar .workbench-toolbar-left {
  min-width: 0;
  flex: 1;
}

.operation-audit-toolbar .workbench-toolbar-right {
  flex-shrink: 0;
}

.audit-time-range {
  width: 280px;
  flex-shrink: 0;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.cleanup-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cleanup-body p {
  margin: 0;
  color: #475569;
  line-height: 1.6;
}

@media (max-width: 900px) {
  .audit-time-range {
    width: 100%;
  }
}
</style>
