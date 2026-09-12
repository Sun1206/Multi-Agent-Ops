<template>
  <div class="fade-in host-center-page">
    <section class="hero panel">
      <div class="host-hero-copy">
        <div class="host-hero-title-row host-hero-title-inline">
          <span class="host-header-icon"><el-icon><Monitor /></el-icon></span>
          <h2>{{ activeTabMeta?.label || '主机中心' }}</h2>
          <p class="host-subtitle inline-subtitle">{{ heroSubtitle }}</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" :loading="overviewLoading" @click="reloadOverview">刷新</el-button>
      </div>
    </section>

    <div class="stats-grid host-stats">
      <div v-for="card in summaryCards" :key="card.label" class="stat-card release-stat-card" :class="card.tone">
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-label">{{ card.label }}</div>
        <div class="release-stat-desc">{{ card.desc }}</div>
      </div>
    </div>

    <div class="neo-tabs theme-purple host-center-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="neo-tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        <el-icon style="margin-right:4px;"><component :is="tab.icon" /></el-icon>
        {{ tab.label }}
      </button>
    </div>

    <div class="host-center-content">
      <CmdbHostsPanel v-if="activeTab === 'assets'" :resource-tree="resourceTree" />
      <CmdbHostScheduleCenter v-else-if="activeTab === 'schedule-center'" :resource-tree="resourceTree" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Timer } from '@element-plus/icons-vue'
import CmdbHostsPanel from '@/components/cmdb/CmdbHostsPanel.vue'
import CmdbHostScheduleCenter from '@/components/cmdb/CmdbHostScheduleCenter.vue'
import { useAuthStore } from '@/stores/auth'
import { getHosts, getHostTaskScheduleStats } from '@/api/modules/ops'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const resourceTree = ref([])
const hostSummary = ref({ total: 0, online: 0, offline: 0, warning: 0 })
const scheduleSummary = ref({ total: 0, enabled: 0, due_soon: 0, success_rate: 0 })
const overviewLoading = ref(false)

const canViewAssets = computed(() => authStore.hasAnyPermission(['ops.host.view', 'ops.host.manage', 'ops.host.terminal']))
const canViewSchedules = computed(() => authStore.hasAnyPermission(['ops.host.schedule.view', 'ops.host.schedule.manage', 'ops.host.schedule.execute']))

const tabs = computed(() => [
  canViewAssets.value && { key: 'assets', label: '主机资产', icon: Monitor, path: '/hosts/assets' },
  canViewSchedules.value && { key: 'schedule-center', label: '定时任务', icon: Timer, path: '/hosts/schedules' },
].filter(Boolean))

const routeTabMap = {
  HostsAssets: 'assets',
  HostSchedules: 'schedule-center',
}

const activeTab = computed(() => routeTabMap[route.name] || tabs.value[0]?.key || 'assets')
const activeTabMeta = computed(() => tabs.value.find(item => item.key === activeTab.value))
const heroSubtitle = computed(() => {
  if (activeTab.value === 'schedule-center') return '支持 SSH 与 Ansible 两种执行方式，可按 Cron、间隔或单次触发。'
  return '统一查看主机状态、归属与基础运行信息。'
})

const summaryCards = computed(() => {
  if (activeTab.value === 'schedule-center' && canViewSchedules.value) {
    return [
      { label: '编排总数', value: scheduleSummary.value.total, desc: '定时任务中心当前纳管的自动化编排数量', tone: '' },
      { label: '已启用', value: scheduleSummary.value.enabled, desc: '正在等待调度器触发的编排任务数量', tone: 'success-card' },
      { label: '1 小时内到点', value: scheduleSummary.value.due_soon, desc: '未来 1 小时内即将触发的编排数量', tone: 'warning-card' },
    ]
  }
  if (canViewAssets.value) {
    return [
      { label: '主机总数', value: hostSummary.value.total, desc: '纳入主机中心的资产总量', tone: '' },
      { label: '在线主机', value: hostSummary.value.online, desc: '当前状态为在线的主机数', tone: 'success-card' },
      { label: '待关注', value: hostSummary.value.offline + hostSummary.value.warning, desc: '离线与告警主机需要优先排查', tone: 'warning-card' },
    ]
  }
  return []
})

async function fetchResourceTree() {
  resourceTree.value = []
}

async function fetchHostSummary() {
  if (!canViewAssets.value) return
  try {
    const [totalRes, onlineRes, offlineRes, warningRes] = await Promise.all([
      getHosts({ page: 1 }),
      getHosts({ page: 1, status: 'online' }),
      getHosts({ page: 1, status: 'offline' }),
      getHosts({ page: 1, status: 'warning' }),
    ])
    hostSummary.value = {
      total: totalRes.count || (totalRes.results || totalRes).length,
      online: onlineRes.count || (onlineRes.results || onlineRes).length,
      offline: offlineRes.count || (offlineRes.results || offlineRes).length,
      warning: warningRes.count || (warningRes.results || warningRes).length,
    }
  } catch (error) {}
}

async function fetchScheduleSummary() {
  if (!canViewSchedules.value) return
  try { scheduleSummary.value = await getHostTaskScheduleStats() } catch (error) {}
}

function switchTab(tabKey) {
  const matched = tabs.value.find(item => item.key === tabKey)
  if (matched && matched.path !== route.path) router.push(matched.path)
}

function ensureAccessibleRoute() {
  const currentTab = routeTabMap[route.name]
  if (!tabs.value.length) return router.replace('/403')
  if (!tabs.value.some(item => item.key === currentTab)) router.replace(tabs.value[0].path)
}

watch(tabs, ensureAccessibleRoute, { immediate: true })
watch(() => route.name, () => { reloadOverview() })

async function reloadOverview() {
  overviewLoading.value = true
  try {
    await Promise.all([
      fetchResourceTree(),
      fetchHostSummary(),
      fetchScheduleSummary(),
    ])
  } finally {
    overviewLoading.value = false
  }
}

onMounted(async () => { await reloadOverview() })
</script>

<style scoped>
.host-center-page{display:flex;flex-direction:column;gap:8px}
.panel{background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);border:1px solid #dbe4f0;border-radius:24px;box-shadow:0 14px 34px rgba(15,23,42,.06);padding:14px 22px}
.hero{background:linear-gradient(135deg,#fff7ed 0%,#f8fbff 100%);display:flex;gap:12px;justify-content:space-between;align-items:center}
.host-hero-copy{display:flex;flex-direction:column}.host-hero-title-row{display:flex;align-items:center;gap:12px}.host-hero-title-inline{flex-wrap:wrap}.host-header-icon{width:42px;height:42px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;font-size:20px;color:#fff;background:linear-gradient(135deg,#409eff,#36cfc9);box-shadow:0 10px 20px rgba(64,158,255,.2)}
.hero-actions{display:flex;align-items:center;gap:8px}.hero h2{color:#0f172a;font-size:23px;margin:0}.host-subtitle,.inline-subtitle{margin:0;max-width:none;font-size:13px;line-height:1.45;color:#475569}
.stats-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.host-stats{gap:8px}
.release-stat-card{position:relative;min-height:76px;background:linear-gradient(145deg,#ffffff 0%,#f6faff 100%);border:1px solid rgba(148,163,184,.18);box-shadow:0 16px 34px rgba(15,23,42,.07);text-align:left;padding:12px 16px;overflow:hidden}
.release-stat-card::after{content:'';position:absolute;inset:auto -24px -30px auto;width:108px;height:108px;border-radius:50%;background:radial-gradient(circle,rgba(64,158,255,.16) 0%,rgba(64,158,255,0) 70%)}.warning-card::after{background:radial-gradient(circle,rgba(245,158,11,.18) 0%,rgba(245,158,11,0) 70%)}.success-card::after{background:radial-gradient(circle,rgba(16,185,129,.18) 0%,rgba(16,185,129,0) 70%)}
.stat-value{font-size:24px;line-height:1.05;color:#0f172a;font-weight:700}.stat-label{margin-top:4px;color:#64748b;font-size:13px}.release-stat-desc{margin-top:6px;color:#64748b;font-size:12px}
.host-center-tabs{width:100%;margin-top:-16px;padding:4px;border-radius:12px;background:rgba(255,255,255,.9);border:1px solid rgba(148,163,184,.16);box-shadow:0 12px 26px rgba(15,23,42,.04)}.host-center-content{min-width:0;margin-top:-4px}
@media (max-width: 900px) { .hero{flex-direction:column;align-items:flex-start} .stats-grid{grid-template-columns:1fr} }
.hero.panel { border-radius: 20px; }
</style>

