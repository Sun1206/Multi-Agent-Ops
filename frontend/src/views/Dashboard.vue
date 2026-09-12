<template>
  <div v-loading="auditLoading" class="dashboard-page workbench-page-shell">
    <section class="workbench-card dashboard-aiops-overview">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">运行概览</span>
          <span class="toolbar-desc">聚焦所选时间范围内的调用命中明细与模型成本。</span>
        </div>
        <div class="overview-time-controls">
          <el-date-picker
            v-model="overviewTimeRange"
            class="overview-time-picker"
            size="small"
            type="datetimerange"
            format="YYYY-MM-DD HH:mm"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            :clearable="false"
            :shortcuts="overviewTimeShortcuts"
            @change="handleOverviewRangeChange"
          />
          <el-button size="small" :type="overviewAllTime ? 'primary' : 'default'" plain @click="selectAllOverviewTime">
            全部时间
          </el-button>
          <el-button class="filter-refresh-btn" size="small" plain :loading="auditLoading" @click="loadAuditOverview">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="overview-dashboard-grid">
        <div class="overview-invocation-section">
          <div class="invocation-chart-grid">
            <div v-for="chart in overviewInvocationCharts" :key="chart.key" class="invocation-chart-card">
              <div class="invocation-chart-head">
                <strong>{{ chart.title }}</strong>
                <el-tag size="small" effect="plain">{{ formatNumber(chart.total) }} 次</el-tag>
              </div>
              <div class="invocation-pie-layout">
                <div class="invocation-pie" :style="chart.pieStyle">
                  <div class="invocation-pie-core">
                    <strong>{{ formatNumber(chart.total) }}</strong>
                    <span>总计</span>
                  </div>
                </div>
                <div v-if="chart.total" class="invocation-pie-legend">
                  <div v-for="item in chart.rows.slice(0, 5)" :key="item.key" class="invocation-pie-row">
                    <div class="invocation-pie-row-head">
                      <span class="invocation-dot" :style="{ background: item.color }"></span>
                      <span>{{ item.label }}</span>
                      <em>{{ formatPercent(item.value, chart.total) }}</em>
                      <strong>{{ formatNumber(item.value) }}</strong>
                    </div>
                  </div>
                </div>
                <div v-else class="overview-empty">{{ chart.emptyText }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="overview-panel overview-panel--model">
          <div class="overview-panel-head">
            <span class="section-title">模型成本</span>
          </div>
          <div class="overview-mini-grid">
            <div class="overview-mini-stat">
              <span>模型调用</span>
              <strong>{{ formatNumber(modelCostSummary.total_calls) }}</strong>
            </div>
            <div class="overview-mini-stat">
              <span>Token</span>
              <strong>{{ formatTokenCount(modelCostSummary.total_tokens) }}</strong>
            </div>
            <div class="overview-mini-stat">
              <span>费用</span>
              <strong>{{ formatModelCostSummary(modelCostSummary) }}</strong>
            </div>
            <div class="overview-mini-stat">
              <span>平均耗时</span>
              <strong>{{ formatLatency(modelCostSummary.avg_latency_ms) }}</strong>
            </div>
          </div>
          <div class="overview-rank-list">
            <div v-for="item in modelProviderRows" :key="`${item.provider}-${item.cost_currency || 'USD'}`" class="overview-rank-row">
              <div class="overview-rank-main">
                <div class="overview-rank-title">
                  <span>{{ item.provider }}</span>
                  <strong>{{ formatNumber(item.calls) }} 次</strong>
                </div>
                <div class="overview-rank-meta">
                  <span>{{ formatTokenCount(item.tokens) }} Token</span>
                  <span>{{ formatCost(item.estimated_cost_usd, item.cost_currency) }}</span>
                  <span>平均 {{ formatLatency(item.avg_latency_ms) }}</span>
                </div>
                <div class="overview-rank-bar"><span :style="{ width: `${item.percent}%` }"></span></div>
              </div>
            </div>
            <div v-if="!modelProviderRows.length" class="overview-empty">暂无模型调用数据</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { getAIOpsAuditCosts, getAIOpsAuditOverview } from '@/api/modules/aiops'

const OVERVIEW_DEFAULT_DAYS = 7

const authStore = useAuthStore()
const auditLoading = ref(false)
const auditOverview = ref({})
const auditCosts = ref({})
const overviewAllTime = ref(false)
const overviewRecentDays = ref(OVERVIEW_DEFAULT_DAYS)
const overviewTimeRange = ref(buildRecentTimeRange(OVERVIEW_DEFAULT_DAYS))
const overviewTimeShortcuts = [
  { text: '最近 24 小时', value: () => buildRecentTimeRange(1) },
  { text: '最近 7 天', value: () => buildRecentTimeRange(7) },
  { text: '最近 30 天', value: () => buildRecentTimeRange(30) },
  { text: '最近 90 天', value: () => buildRecentTimeRange(90) },
]

const canViewAiopsAudit = computed(() => authStore.hasPermission('aiops.audit.view'))

const invocationPiePalettes = {
  mcp: ['#245bdb', '#3b82f6', '#60a5fa', '#93c5fd', '#1d4ed8', '#2563eb', '#38bdf8', '#0ea5e9'],
  skills: ['#16a34a', '#22c55e', '#4ade80', '#86efac', '#15803d', '#059669', '#34d399', '#10b981'],
  actions: ['#f59e0b', '#fbbf24', '#f97316', '#fb923c', '#d97706', '#ea580c', '#facc15', '#eab308'],
}

const modelCostSummary = computed(() => auditCosts.value?.model || {})
const toolCostSummary = computed(() => auditCosts.value?.tools || {})
const modelProviderRows = computed(() => {
  const rows = Array.isArray(modelCostSummary.value.by_provider) ? modelCostSummary.value.by_provider : []
  const maxCalls = Math.max(...rows.map(item => toNumber(item.calls)), 1)
  return rows.slice(0, 6).map(item => ({
    ...item,
    percent: Math.max(6, Math.round((toNumber(item.calls) / maxCalls) * 100)),
  }))
})

const overviewInvocationCharts = computed(() => {
  const distribution = auditOverview.value?.invocation_distribution || {}
  const fallbackMcpItems = Array.isArray(toolCostSummary.value.by_tool)
    ? toolCostSummary.value.by_tool.map(item => ({
      key: item.tool_name || 'unknown',
      label: item.tool_name || '未命名工具',
      count: item.calls,
    }))
    : []
  return [
    buildInvocationPieChart({
      key: 'mcp',
      title: 'MCP 工具调用',
      items: Array.isArray(distribution.mcp_tools) ? distribution.mcp_tools : fallbackMcpItems,
      palette: invocationPiePalettes.mcp,
      emptyText: '暂无 MCP 工具调用',
    }),
    buildInvocationPieChart({
      key: 'skills',
      title: 'Skill 命中',
      items: Array.isArray(distribution.skills) ? distribution.skills : [],
      palette: invocationPiePalettes.skills,
      emptyText: '暂无 Skill 命中记录',
    }),
    buildInvocationPieChart({
      key: 'actions',
      title: 'Action 命中',
      items: Array.isArray(distribution.actions) ? distribution.actions : [],
      palette: invocationPiePalettes.actions,
      emptyText: '暂无 Action 命中记录',
    }),
  ]
})

function toNumber(value) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : 0
}

function normalizeInvocationPieRows(items, palette) {
  const rowMap = new Map()
  ;(Array.isArray(items) ? items : []).forEach((item, index) => {
    const value = toNumber(item?.count ?? item?.value ?? item?.calls)
    if (!value) return
    const label = String(item?.label || item?.name || item?.tool_name || item?.code || item?.key || '未命名').trim()
    const key = String(item?.key || item?.slug || item?.code || item?.tool_name || label || index).trim()
    const current = rowMap.get(key) || { key, label, value: 0 }
    current.value += value
    rowMap.set(key, current)
  })
  return Array.from(rowMap.values())
    .sort((left, right) => right.value - left.value || left.label.localeCompare(right.label, 'zh-CN'))
    .map((item, index) => ({
      ...item,
      color: palette[index % palette.length],
    }))
}

function buildInvocationPieStyle(rows, total) {
  if (!total) return { background: 'conic-gradient(#e2e8f0 0deg 360deg)' }
  let cursor = 0
  const segments = rows.map((item) => {
    const start = cursor
    cursor += (item.value / total) * 360
    return `${item.color} ${start.toFixed(2)}deg ${cursor.toFixed(2)}deg`
  })
  return { background: `conic-gradient(${segments.join(', ')})` }
}

function buildInvocationPieChart({ key, title, items, palette, emptyText }) {
  const rows = normalizeInvocationPieRows(items, palette)
  const total = rows.reduce((sum, item) => sum + item.value, 0)
  return {
    key,
    title,
    rows,
    total,
    emptyText,
    pieStyle: buildInvocationPieStyle(rows, total),
  }
}

function buildRecentTimeRange(days) {
  const end = new Date()
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000)
  return [start, end]
}

function formatDateTimeParam(value) {
  if (!value) return ''
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toISOString()
}

function buildOverviewCostParams() {
  if (overviewAllTime.value) return { range: 'all' }
  if (overviewRecentDays.value) return { days: overviewRecentDays.value }
  const [start, end] = Array.isArray(overviewTimeRange.value) ? overviewTimeRange.value : []
  const startParam = formatDateTimeParam(start)
  const endParam = formatDateTimeParam(end)
  if (startParam && endParam) return { start: startParam, end: endParam }
  return { days: OVERVIEW_DEFAULT_DAYS }
}

function inferRecentDaysFromRange(range) {
  if (!Array.isArray(range) || range.length !== 2) return null
  const [start, end] = range
  const startDate = start instanceof Date ? start : new Date(start)
  const endDate = end instanceof Date ? end : new Date(end)
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return null
  const now = Date.now()
  const endDelta = Math.abs(now - endDate.getTime())
  const diffDays = (endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000)
  if (endDelta > 10 * 60 * 1000) return null
  return [1, 7, 14, 30, 90].find(days => Math.abs(diffDays - days) < 0.02) || null
}

function formatNumber(value) {
  return toNumber(value).toLocaleString('zh-CN')
}

function formatPercent(value, total) {
  const totalValue = toNumber(total)
  if (!totalValue) return '0%'
  const percent = (toNumber(value) / totalValue) * 100
  return `${percent >= 10 ? Math.round(percent) : percent.toFixed(1)}%`
}

function formatTokenCount(value) {
  const numberValue = Math.round(toNumber(value))
  if (Math.abs(numberValue) < 1000000) return formatNumber(numberValue)
  const millionValue = numberValue / 1000000
  const digits = Math.abs(millionValue) < 10 ? 2 : 1
  return `${millionValue.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')}M`
}

function normalizeCostCurrency(currency) {
  return String(currency || '').toUpperCase() === 'CNY' ? 'CNY' : 'USD'
}

function currencySymbol(currency) {
  return normalizeCostCurrency(currency) === 'CNY' ? '¥' : '$'
}

function formatCost(value, currency = 'USD') {
  const numberValue = toNumber(value)
  const symbol = currencySymbol(currency)
  if (!numberValue) return `${symbol}0`
  return `${symbol}${numberValue.toFixed(numberValue < 1 ? 4 : 2)}`
}

function formatModelCostSummary(summary = {}) {
  const byCurrency = Array.isArray(summary.by_currency) ? summary.by_currency.filter(item => toNumber(item.estimated_cost_usd)) : []
  if (byCurrency.length > 1) return byCurrency.map(item => formatCost(item.estimated_cost_usd, item.currency)).join(' / ')
  const currency = byCurrency[0]?.currency || summary.cost_currency || 'USD'
  return formatCost(summary.estimated_cost_usd, currency)
}

function formatLatency(value) {
  const numberValue = Math.round(toNumber(value))
  return numberValue ? `${formatNumber(numberValue)} ms` : '-'
}

async function loadAuditOverview() {
  if (!canViewAiopsAudit.value) return
  auditLoading.value = true
  try {
    const params = buildOverviewCostParams()
    const [overviewData, costData] = await Promise.all([
      getAIOpsAuditOverview(params, { skipErrorMessage: true }),
      getAIOpsAuditCosts(params, { skipErrorMessage: true }),
    ])
    auditOverview.value = overviewData || {}
    auditCosts.value = costData || {}
  } finally {
    auditLoading.value = false
  }
}

async function handleOverviewRangeChange() {
  overviewAllTime.value = false
  overviewRecentDays.value = inferRecentDaysFromRange(overviewTimeRange.value)
  await loadAuditOverview()
}

async function selectAllOverviewTime() {
  overviewAllTime.value = true
  overviewRecentDays.value = null
  overviewTimeRange.value = []
  await loadAuditOverview()
}

onMounted(loadAuditOverview)
</script>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.workbench-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(250, 252, 255, 0.96) 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  padding: 16px;
}

.dashboard-aiops-overview {
  min-height: calc(100vh - 128px);
}

.section-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.toolbar-head {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.toolbar-title,
.section-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.toolbar-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.overview-time-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.overview-time-picker {
  width: 330px;
}

.filter-refresh-btn {
  min-height: 28px;
}

.overview-dashboard-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.invocation-chart-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.invocation-chart-card,
.overview-panel {
  min-width: 0;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, #fff 0%, #fbfdff 100%);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
  padding: 12px 14px;
}

.invocation-chart-head,
.overview-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.invocation-chart-head strong {
  color: #0f172a;
  font-size: 14px;
}

.invocation-pie-layout {
  display: grid;
  grid-template-rows: auto minmax(96px, 1fr);
  gap: 10px;
  min-height: 330px;
}

.invocation-pie {
  position: relative;
  width: 168px;
  height: 168px;
  margin: 6px auto 0;
  border-radius: 50%;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
}

.invocation-pie::after {
  position: absolute;
  inset: 36px;
  content: '';
  border-radius: 50%;
  background: #f8fafc;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.04);
}

.invocation-pie-core {
  position: absolute;
  z-index: 1;
  inset: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f8fafc;
}

.invocation-pie-core strong {
  color: #0f172a;
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
}

.invocation-pie-core span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  margin-top: 8px;
}

.invocation-pie-legend {
  overflow: hidden auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 128px;
  padding-right: 4px;
}

.invocation-pie-row {
  border-radius: 9px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.62);
  padding: 6px 8px;
}

.invocation-pie-row-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 6px;
}

.invocation-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.invocation-pie-row-head span:not(.invocation-dot) {
  min-width: 0;
  overflow: hidden;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.invocation-pie-row-head em {
  color: #94a3b8;
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
}

.invocation-pie-row-head strong {
  color: #0f172a;
  font-size: 12px;
}

.overview-mini-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.overview-mini-stat {
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  padding: 12px 14px;
}

.overview-mini-stat span {
  display: block;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}

.overview-mini-stat strong {
  color: #0f172a;
  font-size: 23px;
  font-weight: 800;
}

.overview-rank-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.overview-rank-row {
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.82);
  padding: 10px 12px;
}

.overview-rank-title,
.overview-rank-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.overview-rank-title span {
  min-width: 0;
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-rank-title strong {
  color: #0f172a;
  flex: 0 0 auto;
  font-size: 13px;
}

.overview-rank-meta {
  justify-content: flex-start;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 12px;
  margin-top: 6px;
}

.overview-rank-bar {
  overflow: hidden;
  height: 5px;
  margin-top: 9px;
  border-radius: 999px;
  background: #e8eef7;
}

.overview-rank-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #2563eb);
}

.overview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
  color: #94a3b8;
  font-size: 12px;
}

@media (max-width: 980px) {
  .invocation-chart-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-mini-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .section-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .overview-time-picker {
    width: 100%;
  }

  .invocation-chart-grid,
  .overview-mini-grid {
    grid-template-columns: 1fr;
  }
}
</style>
