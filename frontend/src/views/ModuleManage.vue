<template>
  <div class="fade-in module-manage-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row">
          <span class="release-header-icon"><el-icon><Menu /></el-icon></span>
          <h2>模块管理</h2>
          <p class="page-inline-desc">配置左侧菜单模块的显示状态，必选模块保持固定展示。</p>
        </div>
      </div>
    </section>

    <div class="workbench-card module-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">菜单模块</span>
          <span class="toolbar-desc">工单系统和容器管理可按需隐藏，其余核心模块保持显示。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button class="filter-refresh-btn" :loading="loading" @click="fetchSettings">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="modules" stripe style="width: 100%" class="module-table">
        <el-table-column label="模块" min-width="180">
          <template #default="{ row }">
            <div class="module-name-cell">
              <span class="module-name">{{ row.title }}</span>
              <span class="module-code">{{ row.code }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="280" show-overflow-tooltip />
        <el-table-column label="配置类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.required ? 'info' : 'success'">
              {{ row.required ? '必选模块' : '可隐藏' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="显示状态" width="150">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              inline-prompt
              active-text="显示"
              inactive-text="隐藏"
              :disabled="row.required"
            />
          </template>
        </el-table-column>
        <el-table-column label="最近更新" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="更新人" width="120">
          <template #default="{ row }">{{ row.updated_by || '-' }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Menu, RefreshRight } from '@element-plus/icons-vue'
import { getModuleSettings, updateModuleSettings } from '@/api/modules/rbac'

const loading = ref(false)
const saving = ref(false)
const modules = ref([])

function normalizeModules(list = []) {
  return list.map(item => ({
    ...item,
    enabled: item.required ? true : item.enabled !== false,
  }))
}

async function fetchSettings() {
  loading.value = true
  try {
    modules.value = normalizeModules(await getModuleSettings())
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const payload = modules.value.map(item => ({
      code: item.code,
      enabled: item.required ? true : item.enabled,
    }))
    const response = await updateModuleSettings(payload)
    modules.value = normalizeModules(response.data || response || [])
    window.dispatchEvent(new Event('sxdevops-module-settings-updated'))
    ElMessage.success('模块显示配置已保存')
  } finally {
    saving.value = false
  }
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(fetchSettings)
</script>

<style scoped>
.module-manage-page {
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

.module-content-card {
  display: flex;
  flex-direction: column;
}

.module-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.module-name {
  color: #0f172a;
  font-weight: 700;
}

.module-code {
  color: #94a3b8;
  font-size: 12px;
}

:deep(.module-table .el-switch.is-disabled) {
  opacity: 0.72;
}

@media (max-width: 760px) {
  .section-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}

.hero.panel { border-radius: 20px; }
</style>
