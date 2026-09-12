<template>
  <div class="observability-page workbench-page-shell">
    <section class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon"><el-icon><Share /></el-icon></span>
          <h2>可观测总览</h2>
          <span class="page-inline-desc">统一维护日志、链路、指标、看板与告警的关联配置。</span>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" :loading="loading" @click="loadOverview">
          <el-icon><RefreshRight /></el-icon>
          刷新
        </el-button>
      </div>
    </section>

    <div class="audit-grid">
      <div v-for="card in capabilityCards" :key="card.label" class="audit-card audit-card--inline" :class="card.tone">
        <div class="stat-value">{{ card.value }}</div>
        <div class="stat-label">{{ card.label }}</div>
      </div>
    </div>

    <section v-if="canViewLinks" class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">关联配置</span>
          <span class="toolbar-desc">日志、链路和看板之间的跳转关系会作为 AIOps 分析上下文。</span>
        </div>
      </div>
      <ObservabilityDataSourceLinks embedded />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RefreshRight, Share } from '@element-plus/icons-vue'
import { getObservabilityOverview } from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import ObservabilityDataSourceLinks from './ObservabilityDataSourceLinks.vue'

const authStore = useAuthStore()
const loading = ref(false)
const overview = ref({ modules: {}, summary: {} })
const canViewLinks = computed(() => authStore.hasPermission('ops.observability.link.view'))

const capabilityCards = computed(() => [
  {
    label: '监控看板',
    value: overview.value.modules?.grafana?.dashboard_count || 0,
    tone: '',
  },
  {
    label: '日志数据源',
    value: overview.value.modules?.logs?.datasource_count || 0,
    tone: 'audit-card--success',
  },
  {
    label: '链路数据源',
    value: overview.value.modules?.tracing?.datasource_count || 0,
    tone: 'audit-card--warning',
  },
  {
    label: '未确认告警',
    value: overview.value.modules?.alerts?.unacknowledged || 0,
    tone: 'audit-card--danger',
  },
])

async function loadOverview() {
  loading.value = true
  try {
    overview.value = await getObservabilityOverview()
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<style scoped>
.observability-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border: 1px solid rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  padding: 14px 16px;
}

.hero {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.hero-title-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-icon {
  align-items: center;
  background: rgba(51, 112, 255, 0.1);
  border-radius: 14px;
  color: #245bdb;
  display: inline-flex;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.observability-page h2 {
  color: #0f172a;
  font-size: 23px;
  margin: 0;
}

.page-inline-desc {
  color: #475569;
  font-size: 13px;
}

.audit-grid {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.hero-actions :deep(.el-button) {
  border-radius: 10px;
  font-weight: 500;
  min-height: 32px;
  padding: 0 14px;
}

@media (max-width: 900px) {
  .audit-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .audit-grid {
    grid-template-columns: 1fr;
  }
}
</style>
