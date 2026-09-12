<template>
  <div class="fade-in task-page-shell">
    <section class="hero panel task-hero-panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon hero-icon-timer"><el-icon><Timer /></el-icon></span>
          <h2>计划任务</h2>
          <p class="page-inline-desc">承载周期编排、单次触发与执行记录，面向自动化调度与结果追踪场景。</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" :icon="Refresh" :loading="loading" @click="reloadResourceTree">刷新资源</el-button>
      </div>
    </section>

    <CmdbHostScheduleCenter :resource-tree="resourceTree" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Refresh, Timer } from '@element-plus/icons-vue'
import CmdbHostScheduleCenter from '@/components/cmdb/CmdbHostScheduleCenter.vue'
import { getTaskResourceTree } from '@/api/modules/ops'

const loading = ref(false)
const resourceTree = ref([])

function normalizeTree(list = []) {
  return list.map((env) => ({
    ...env,
    treeKey: `environment:${env.id}`,
    children: (env.children || []).map((system) => ({
      ...system,
      treeKey: `system:${system.id}`,
      children: [],
    })),
  }))
}

async function reloadResourceTree() {
  loading.value = true
  try {
    const tree = await getTaskResourceTree()
    resourceTree.value = normalizeTree(tree || [])
  } finally {
    loading.value = false
  }
}

onMounted(reloadResourceTree)
</script>

<style scoped>
.task-page-shell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hero.panel.task-hero-panel {
  align-items: center;
  background: linear-gradient(180deg, #ffffff 0%, #fcfdff 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
  display: flex;
  justify-content: space-between;
  padding: 10px 14px;
}

.hero-copy,
.hero-actions {
  display: flex;
  gap: 4px;
}

.hero-copy {
  flex-wrap: wrap;
}

.hero-title-row {
  align-items: center;
  display: flex;
  gap: 10px;
}

.hero-title-row h2 {
  color: #0f172a;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.1;
  margin: 0;
}

.page-inline-desc {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
}

.hero-icon {
  align-items: center;
  border-radius: 16px;
  color: #fff;
  display: inline-flex;
  font-size: 20px;
  height: 36px;
  justify-content: center;
  width: 36px;
}

.hero-icon-timer {
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
}

.hero-actions .el-button {
  border-radius: 10px;
  font-weight: 500;
  min-height: 30px;
  padding: 0 12px;
}

.panel {
  background: #fff;
  border: 1px solid #eff0f2;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(31, 35, 41, 0.06);
  padding: 12px 14px;
}

@media (max-width: 760px) {
  .hero.panel.task-hero-panel {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
