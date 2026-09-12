<template>
  <div class="logs-page">
    <section class="hero panel">
      <div>
        <p class="eyebrow">Log Center</p>
        <h2>Unified Log Workspace</h2>
        <p class="subtitle">
          Switch between Loki, Elasticsearch, and Aliyun SLS without leaving the page.
        </p>
      </div>
      <div class="hero-actions">
        <el-button @click="loadCatalog" :loading="catalogLoading">Refresh catalog</el-button>
        <el-button type="primary" @click="runQuery" :loading="queryLoading">Run query</el-button>
      </div>
    </section>

    <section class="provider-grid">
      <button
        v-for="provider in providers"
        :key="provider.id"
        class="provider-card"
        :class="{ active: activeProvider === provider.id }"
        @click="activeProvider = provider.id"
      >
        <div class="provider-head">
          <strong>{{ provider.name }}</strong>
          <el-tag size="small" :type="provider.configured ? 'success' : 'info'">
            {{ provider.configured ? 'Configured' : 'Optional' }}
          </el-tag>
        </div>
        <p>{{ provider.description }}</p>
      </button>
    </section>

    <section class="content-grid">
      <div class="panel">
        <div class="panel-head">
          <h3>Connection</h3>
          <span>{{ currentProviderName }}</span>
        </div>

        <el-form label-position="top">
          <template v-if="isLoki">
            <el-form-item label="Loki endpoint">
              <el-input v-model="configs.loki.endpoint" placeholder="http://localhost:3100" />
            </el-form-item>
          </template>

          <template v-else-if="isElk">
            <el-form-item label="Elasticsearch endpoint">
              <el-input v-model="configs.elk.endpoint" placeholder="https://es.example.com:9200" />
            </el-form-item>
            <el-form-item label="Auth mode">
              <el-select v-model="configs.elk.auth_type">
                <el-option label="No auth" value="none" />
                <el-option label="Basic auth" value="basic" />
                <el-option label="API key" value="api_key" />
                <el-option label="Bearer token" value="bearer" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="configs.elk.auth_type === 'basic'" label="Username">
              <el-input v-model="configs.elk.username" />
            </el-form-item>
            <el-form-item v-if="configs.elk.auth_type === 'basic'" label="Password">
              <el-input v-model="configs.elk.password" show-password />
            </el-form-item>
            <el-form-item v-if="configs.elk.auth_type === 'api_key'" label="API key">
              <el-input v-model="configs.elk.api_key" show-password />
            </el-form-item>
            <el-form-item v-if="configs.elk.auth_type === 'bearer'" label="Bearer token">
              <el-input v-model="configs.elk.bearer_token" show-password />
            </el-form-item>
            <el-form-item label="Index pattern">
              <el-input v-model="configs.elk.index_pattern" placeholder="logs-*" />
            </el-form-item>
            <el-form-item label="Time field">
              <el-input v-model="configs.elk.time_field" placeholder="@timestamp" />
            </el-form-item>
            <el-form-item label="Message fields">
              <el-input v-model="configs.elk.message_fields" placeholder="message,log,msg" />
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="SLS endpoint">
              <el-input v-model="configs.sls.endpoint" placeholder="cn-hangzhou.log.aliyuncs.com" />
            </el-form-item>
            <el-form-item label="Project">
              <el-input v-model="configs.sls.project" />
            </el-form-item>
            <el-form-item label="AccessKey ID">
              <el-input v-model="configs.sls.access_key_id" />
            </el-form-item>
            <el-form-item label="AccessKey secret">
              <el-input v-model="configs.sls.access_key_secret" show-password />
            </el-form-item>
            <el-form-item label="Default logstore">
              <el-input v-model="configs.sls.logstore" />
            </el-form-item>
            <el-form-item label="Topic">
              <el-input v-model="configs.sls.topic" />
            </el-form-item>
          </template>
        </el-form>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h3>Query</h3>
          <span>{{ queryLabel }}</span>
        </div>

        <el-form label-position="top">
          <el-form-item label="Time range">
            <el-date-picker
              v-model="timeRange"
              type="datetimerange"
              value-format="x"
              format="YYYY-MM-DD HH:mm:ss"
              range-separator="to"
              start-placeholder="Start time"
              end-placeholder="End time"
            />
          </el-form-item>
          <el-form-item label="Result limit">
            <el-input-number v-model="limit" :min="20" :max="2000" :step="20" />
          </el-form-item>

          <template v-if="isLoki">
            <el-form-item label="Label filters">
              <div class="stack">
                <div v-for="(filter, index) in labelFilters" :key="index" class="filter-row">
                  <el-select v-model="filter.key" placeholder="Label" filterable @change="onLokiLabelKeyChange(index)">
                    <el-option v-for="item in lokiLabels" :key="item" :label="item" :value="item" />
                  </el-select>
                  <el-select v-model="filter.operator" class="operator-select">
                    <el-option label="=" value="=" />
                    <el-option label="!=" value="!=" />
                    <el-option label="=~" value="=~" />
                    <el-option label="!~" value="!~" />
                  </el-select>
                  <el-select
                    v-model="filter.value"
                    placeholder="Value"
                    filterable
                    allow-create
                    @focus="loadLokiLabelValues(index)"
                  >
                    <el-option v-for="item in filter.options" :key="item" :label="item" :value="item" />
                  </el-select>
                  <el-button text type="danger" @click="removeLabelFilter(index)">Remove</el-button>
                </div>
                <el-button text type="primary" @click="addLabelFilter">Add filter</el-button>
              </div>
            </el-form-item>
            <el-form-item label="Content search">
              <el-input v-model="lokiContentQuery" placeholder="error OR timeout" />
            </el-form-item>
            <el-form-item label="Manual LogQL">
              <el-input
                v-model="lokiManualQuery"
                type="textarea"
                :rows="4"
                placeholder='{job="nginx"} |= "error"'
              />
              <div class="helper">Leave blank to use generated query: {{ generatedLokiQuery }}</div>
            </el-form-item>
          </template>

          <template v-else-if="isElk">
            <el-form-item label="Index">
              <el-select
                v-model="sourceName"
                placeholder="Index pattern or discovered index"
                filterable
                allow-create
                clearable
              >
                <el-option v-for="item in catalogItems" :key="item.name" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="Lucene query">
              <el-input
                v-model="queryText"
                type="textarea"
                :rows="4"
                placeholder='service.name:"payment" AND level:error'
              />
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="Logstore">
              <el-select v-model="sourceName" placeholder="Logstore" filterable allow-create clearable>
                <el-option v-for="item in catalogItems" :key="item.name" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="SLS query">
              <el-input
                v-model="queryText"
                type="textarea"
                :rows="4"
                placeholder='level:error AND service:"payment"'
              />
            </el-form-item>
          </template>
        </el-form>
      </div>
    </section>

    <section class="stats-grid">
      <div class="stat-card warm">
        <span>Total logs</span>
        <strong>{{ results.total || 0 }}</strong>
      </div>
      <div class="stat-card cool">
        <span>Current source</span>
        <strong>{{ results.source || currentProviderName || '--' }}</strong>
      </div>
      <div class="stat-card accent">
        <span>Query latency</span>
        <strong>{{ results.took_ms != null ? `${results.took_ms} ms` : '--' }}</strong>
      </div>
      <div class="stat-card neutral">
        <span>Error logs</span>
        <strong>{{ errorCount }}</strong>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h3>Trend</h3>
        <span>{{ results.logs.length ? 'Recent buckets' : 'No data yet' }}</span>
      </div>
      <div ref="chartRef" class="chart"></div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h3>Results</h3>
        <el-tag v-if="results.progress" type="info">{{ results.progress }}</el-tag>
      </div>
      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <div v-else-if="queryLoading" class="empty-state">Loading logs...</div>
      <div v-else-if="!results.logs.length" class="empty-state">Run a query to inspect logs.</div>
      <div v-else class="log-list">
        <article v-for="(item, index) in results.logs" :key="`${item.timestamp}-${index}`" class="log-card">
          <button class="log-main" @click="toggleRow(index)">
            <div class="log-meta">
              <span>{{ formatTimestamp(item.timestamp) }}</span>
              <el-tag size="small" :type="levelTagType(item)">{{ levelLabel(item) }}</el-tag>
              <span>{{ item.source }}</span>
            </div>
            <div class="log-message" v-html="formatMessage(item.message)"></div>
          </button>
          <div v-if="expandedRows.has(index)" class="log-detail">
            <div class="attribute-grid">
              <div v-for="attr in displayAttributes(item.attributes)" :key="attr.key" class="attribute-card">
                <strong>{{ attr.key }}</strong>
                <span>{{ attr.value }}</span>
              </div>
            </div>
            <pre>{{ item.message }}</pre>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import echarts from '@/lib/echarts'
import { ElMessage } from 'element-plus'
import { getLogProviderCatalog, getLogProviders, queryLogs } from '@/api/modules/ops'

const providers = ref([])
const activeProvider = ref('loki')
const catalogItems = ref([])
const catalogLoading = ref(false)
const queryLoading = ref(false)
const errorMessage = ref('')
const chartRef = ref(null)
let chart = null

const configs = reactive({
  loki: { endpoint: '' },
  elk: {
    endpoint: '',
    auth_type: 'none',
    username: '',
    password: '',
    api_key: '',
    bearer_token: '',
    index_pattern: 'logs-*',
    time_field: '@timestamp',
    message_fields: 'message,log,msg',
  },
  sls: {
    endpoint: '',
    project: '',
    logstore: '',
    topic: '',
    access_key_id: '',
    access_key_secret: '',
  },
})

const timeRange = ref(defaultTimeRange())
const limit = ref(200)
const sourceName = ref('')
const queryText = ref('')
const lokiLabels = ref([])
const labelFilters = ref([])
const lokiContentQuery = ref('')
const lokiManualQuery = ref('')
const expandedRows = reactive(new Set())
const results = reactive({ provider: '', source: '', total: 0, took_ms: null, progress: '', logs: [] })

const isLoki = computed(() => activeProvider.value === 'loki')
const isElk = computed(() => activeProvider.value === 'elk')
const currentProviderName = computed(() => providers.value.find((item) => item.id === activeProvider.value)?.name || '')
const queryLabel = computed(() => {
  if (isLoki.value) return 'LogQL with label discovery'
  if (isElk.value) return 'Lucene query syntax'
  return 'Aliyun SLS query syntax'
})
const errorCount = computed(() => results.logs.filter((item) => normalizeLogLevel(item) === 'error').length)
const generatedLokiQuery = computed(() => {
  const selector = labelFilters.value
    .filter((item) => item.key && item.value)
    .map((item) => `${item.key}${item.operator}"${escapeLogValue(item.value)}"`)
  const base = selector.length ? `{${selector.join(',')}}` : '{job!=""}'
  return lokiContentQuery.value.trim() ? `${base} |= "${escapeLogValue(lokiContentQuery.value.trim())}"` : base
})

watch(activeProvider, async () => {
  sourceName.value = ''
  queryText.value = ''
  errorMessage.value = ''
  resetResults()
  expandedRows.clear()
  await loadCatalog()
  await nextTick()
  renderChart()
})

function defaultTimeRange() {
  const end = Date.now()
  return [String(end - 3600 * 1000), String(end)]
}

function escapeLogValue(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function applyDefaults(provider) {
  Object.entries(provider.defaults || {}).forEach(([key, value]) => {
    if (value && value !== 'configured' && !configs[provider.id][key]) {
      configs[provider.id][key] = value
    }
  })
}

function activeConfig() {
  return { ...configs[activeProvider.value] }
}

function resetResults() {
  results.provider = ''
  results.source = ''
  results.total = 0
  results.took_ms = null
  results.progress = ''
  results.logs = []
}

async function fetchProviders() {
  const response = await getLogProviders()
  providers.value = response.providers || []
  providers.value.forEach(applyDefaults)
  if (!providers.value.find((item) => item.id === activeProvider.value) && providers.value.length) {
    activeProvider.value = providers.value[0].id
  }
}

async function loadCatalog() {
  catalogLoading.value = true
  try {
    if (isLoki.value) {
      const response = await getLogProviderCatalog('loki', {
        config: activeConfig(),
        action: 'labels',
        start_ms: timeRange.value[0],
        end_ms: timeRange.value[1],
      })
      lokiLabels.value = response.items || []
      if (!labelFilters.value.length) addLabelFilter()
      catalogItems.value = []
    } else {
      const provider = isElk.value ? 'elk' : 'sls'
      const response = await getLogProviderCatalog(provider, {
        config: activeConfig(),
        action: 'sources',
        index_pattern: configs.elk.index_pattern,
      })
      catalogItems.value = response.items || []
      if (!sourceName.value && catalogItems.value.length) {
        sourceName.value = catalogItems.value[0].name
      }
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || 'Failed to load provider catalog')
  } finally {
    catalogLoading.value = false
  }
}

function addLabelFilter() {
  labelFilters.value.push({ key: '', operator: '=', value: '', options: [] })
}

function removeLabelFilter(index) {
  labelFilters.value.splice(index, 1)
  if (!labelFilters.value.length) addLabelFilter()
}

async function onLokiLabelKeyChange(index) {
  labelFilters.value[index].value = ''
  labelFilters.value[index].options = []
  await loadLokiLabelValues(index)
}

async function loadLokiLabelValues(index) {
  const filter = labelFilters.value[index]
  if (!filter.key) return
  const response = await getLogProviderCatalog('loki', {
    config: activeConfig(),
    action: 'label_values',
    label: filter.key,
    start_ms: timeRange.value[0],
    end_ms: timeRange.value[1],
  })
  filter.options = response.items || []
}

function buildPayload() {
  const payload = {
    provider: activeProvider.value,
    config: activeConfig(),
    start_ms: timeRange.value[0],
    end_ms: timeRange.value[1],
    limit: limit.value,
  }
  if (isLoki.value) {
    payload.query = lokiManualQuery.value.trim() || generatedLokiQuery.value
  } else if (isElk.value) {
    payload.query = queryText.value.trim()
    payload.source = sourceName.value || configs.elk.index_pattern
    payload.index_pattern = sourceName.value || configs.elk.index_pattern
    payload.time_field = configs.elk.time_field
    payload.message_fields = configs.elk.message_fields
  } else {
    payload.query = queryText.value.trim()
    payload.source = sourceName.value || configs.sls.logstore
    payload.logstore = sourceName.value || configs.sls.logstore
    payload.topic = configs.sls.topic
  }
  return payload
}

async function runQuery() {
  queryLoading.value = true
  errorMessage.value = ''
  expandedRows.clear()
  try {
    const response = await queryLogs(buildPayload())
    results.provider = response.provider
    results.source = response.source
    results.total = response.total || 0
    results.took_ms = response.took_ms
    results.progress = response.progress || ''
    results.logs = response.logs || []
    await nextTick()
    renderChart()
  } catch (error) {
    resetResults()
    errorMessage.value = error.response?.data?.error || error.message || 'Log query failed'
  } finally {
    queryLoading.value = false
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const buckets = bucketize()
  chart.setOption(
    {
      grid: { left: 36, right: 18, top: 24, bottom: 28 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: buckets.map((item) => item.label),
        axisLabel: { color: '#6b7280', fontSize: 11 },
        axisLine: { lineStyle: { color: '#cbd5e1' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#6b7280', fontSize: 11 },
        splitLine: { lineStyle: { color: '#e5e7eb' } },
      },
      series: [
        {
          name: 'Logs',
          type: 'bar',
          data: buckets.map((item) => item.total),
          itemStyle: { color: '#2563eb', borderRadius: [8, 8, 0, 0] },
        },
        {
          name: 'Errors',
          type: 'line',
          smooth: true,
          data: buckets.map((item) => item.error),
          itemStyle: { color: '#ea580c' },
          lineStyle: { color: '#ea580c', width: 2 },
        },
      ],
    },
    true
  )
}

function bucketize() {
  const points = results.logs
    .map((item) => new Date(item.timestamp).getTime())
    .filter((item) => !Number.isNaN(item))
    .sort((a, b) => a - b)
  if (!points.length) return []

  const min = points[0]
  const max = points[points.length - 1]
  const count = Math.min(24, Math.max(6, Math.ceil(points.length / 12)))
  const step = Math.max(60000, Math.ceil(Math.max(1, max - min) / count))
  const buckets = Array.from({ length: count }, (_, index) => ({
    start: min + index * step,
    total: 0,
    error: 0,
  }))

  results.logs.forEach((item) => {
    const time = new Date(item.timestamp).getTime()
    if (Number.isNaN(time)) return
    const index = Math.min(count - 1, Math.floor((time - min) / step))
    buckets[index].total += 1
    if (normalizeLogLevel(item) === 'error') buckets[index].error += 1
  })

  return buckets.map((item) => ({
    total: item.total,
    error: item.error,
    label: `${String(new Date(item.start).getHours()).padStart(2, '0')}:${String(
      new Date(item.start).getMinutes()
    ).padStart(2, '0')}`,
  }))
}

function toggleRow(index) {
  if (expandedRows.has(index)) expandedRows.delete(index)
  else expandedRows.add(index)
}

function displayAttributes(attributes) {
  return Object.entries(attributes || {})
    .filter(([key]) => !['message', 'log', 'msg'].includes(key))
    .slice(0, 10)
    .map(([key, value]) => ({
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value),
    }))
}

function formatTimestamp(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function formatMessage(message) {
  const safe = escapeHtml(message || '')
  const query = isLoki.value ? lokiContentQuery.value.trim() : queryText.value.trim()
  if (!query) return safe
  const words = query
    .split(/\s+/)
    .filter((item) => item && !['AND', 'OR', 'NOT'].includes(item.toUpperCase()))
    .slice(0, 4)
  return words.reduce(
    (content, word) => content.replace(new RegExp(`(${escapeRegex(escapeHtml(word))})`, 'gi'), '<mark>$1</mark>'),
    safe
  )
}

function escapeHtml(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function rawLogLevel(item) {
  if (item && typeof item === 'object') {
    return item.attributes?.detected_level || item.attributes?.detectedLevel || item.attributes?.level || item.level
  }
  return item
}

function normalizeLevel(level) {
  const normalized = String(level || '').trim().toLowerCase()
  if (['error', 'err', 'fatal', 'critical', 'crit'].includes(normalized)) return 'error'
  if (['warning', 'warn'].includes(normalized)) return 'warning'
  if (['info', 'information', 'notice'].includes(normalized)) return 'info'
  if (['debug', 'trace', 'verbose'].includes(normalized)) return 'debug'
  return 'unknown'
}

function normalizeLogLevel(item) {
  return normalizeLevel(rawLogLevel(item))
}

function levelTagType(item) {
  return { error: 'danger', warning: 'warning', info: 'success', debug: 'info' }[normalizeLogLevel(item)] || ''
}

function levelLabel(item) {
  return { error: 'ERROR', warning: 'WARN', info: 'INFO', debug: 'DEBUG', unknown: 'UNKNOWN' }[normalizeLogLevel(item)] || 'UNKNOWN'
}

function handleResize() {
  chart?.resize()
}

onMounted(async () => {
  addLabelFilter()
  try {
    await fetchProviders()
    await loadCatalog()
    renderChart()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || error.message || 'Failed to initialize log center')
  }
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
</script>

<style scoped>
.logs-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fffdf8 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 20px;
  padding: 22px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
}

.hero {
  align-items: center;
  background:
    radial-gradient(circle at top left, rgba(251, 191, 36, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(37, 99, 235, 0.15), transparent 28%),
    linear-gradient(135deg, #fff7ed 0%, #f8fbff 100%);
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.eyebrow {
  color: #9a3412;
  font-size: 12px;
  letter-spacing: 0.16em;
  margin: 0 0 8px;
  text-transform: uppercase;
}

.hero h2,
.panel h3 {
  color: #0f172a;
  margin: 0;
}

.hero h2 {
  font-size: 23px;
}

.subtitle {
  color: #475569;
  margin: 8px 0 0;
  max-width: 620px;
  line-height: 1.45;
}

.hero-actions,
.content-grid,
.provider-grid,
.stats-grid,
.panel-head,
.log-meta {
  display: flex;
  gap: 12px;
}
.hero-actions {
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hero-actions :deep(.el-button) {
  min-height: 38px;
  padding: 0 16px;
  border-radius: 12px;
}

.provider-grid,
.stats-grid {
  flex-wrap: wrap;
}

.provider-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid #dbe4f0;
  border-radius: 20px;
  cursor: pointer;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 220px;
  padding: 18px;
  text-align: left;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.provider-card:hover,
.provider-card.active {
  border-color: #2563eb;
  box-shadow: 0 16px 34px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}

.provider-head,
.panel-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.provider-card p,
.panel-head span,
.helper,
.empty-state,
.log-meta {
  color: #64748b;
}

.content-grid {
  align-items: flex-start;
}

.content-grid > .panel {
  flex: 1;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-row {
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) 96px minmax(0, 1fr) auto;
}

.operator-select {
  width: 96px;
}

.helper {
  font-size: 12px;
  margin-top: 8px;
}

.stats-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.stat-card {
  border-radius: 22px;
  color: #0f172a;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 116px;
  padding: 18px;
}

.stat-card span {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.stat-card strong {
  font-size: 28px;
  line-height: 1.1;
}

.stat-card.warm {
  background: linear-gradient(135deg, #fef3c7 0%, #fed7aa 100%);
}

.stat-card.cool {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
}

.stat-card.accent {
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
}

.stat-card.neutral {
  background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
}

.chart {
  height: 260px;
}

.empty-state {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: 180px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-card {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  overflow: hidden;
}

.log-main {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 0;
  cursor: pointer;
  padding: 16px 18px;
  text-align: left;
  width: 100%;
}

.log-meta {
  flex-wrap: wrap;
  font-size: 12px;
  margin-bottom: 8px;
}

.log-message {
  color: #0f172a;
  line-height: 1.75;
  word-break: break-word;
}

.log-message :deep(mark) {
  background: rgba(250, 204, 21, 0.32);
  border-radius: 4px;
  padding: 0 2px;
}

.log-detail {
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
  padding: 16px 18px 18px;
}

.attribute-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 8px;
}

.attribute-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
}

.attribute-card span {
  color: #475569;
  word-break: break-word;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1080px) {
  .content-grid,
  .hero {
    flex-direction: column;
  }

  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .filter-row,
  .attribute-grid,
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions,
  .panel-head {
    align-items: stretch;
    flex-direction: column;
  }
}
.hero.panel { border-radius: 20px; }
</style>


