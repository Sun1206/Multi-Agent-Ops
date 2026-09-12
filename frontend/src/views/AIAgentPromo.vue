<template>
  <div class="promo-page">
    <div class="promo-toolbar">
      <button class="promo-back" type="button" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回</span>
      </button>
      <div class="promo-title">AI Ops AI Agent 产品介绍</div>
      <a class="promo-open" href="/promo/sxdevops-ai-agent-promo.html" target="_blank" rel="noopener">
        新窗口打开
      </a>
    </div>
    <iframe
      class="promo-frame"
      src="/promo/sxdevops-ai-agent-promo.html"
      title="AI Ops AI Agent 产品介绍"
    ></iframe>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  router.replace('/login')
}
</script>

<style scoped>
.promo-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #111827;
}

.promo-toolbar {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 18px;
  background: rgba(15, 23, 42, 0.96);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  color: #e5edf8;
}

.promo-back,
.promo-open {
  min-width: 96px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.08);
  color: #dbeafe;
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.promo-back:hover,
.promo-open:hover {
  border-color: rgba(96, 165, 250, 0.56);
  background: rgba(59, 130, 246, 0.18);
  color: #ffffff;
}

.promo-title {
  min-width: 0;
  flex: 1;
  text-align: center;
  color: #f8fafc;
  font-size: 14px;
  font-weight: 800;
}

.promo-frame {
  flex: 1;
  width: 100%;
  border: 0;
  background: #171b1f;
}

@media (max-width: 640px) {
  .promo-toolbar {
    padding: 0 10px;
    gap: 8px;
  }

  .promo-back,
  .promo-open {
    min-width: auto;
    padding: 0 10px;
    font-size: 12px;
  }

  .promo-title {
    font-size: 12px;
  }
}
</style>
