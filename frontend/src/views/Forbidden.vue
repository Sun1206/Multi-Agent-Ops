<template>
  <div class="forbidden-page">
    <div class="forbidden-card">
      <div class="forbidden-code">403</div>
      <h1>无权访问</h1>
      <p>当前账号没有访问该页面的权限，请联系管理员分配角色或用户组。</p>
      <div class="actions">
        <el-button @click="$router.back()">返回上一页</el-button>
        <el-button type="primary" @click="$router.push('/dashboard')">回到首页</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.forbidden-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
  padding: 24px;
}

.forbidden-card {
  width: min(520px, 100%);
  padding: 40px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  text-align: center;
}

.forbidden-code {
  font-size: 72px;
  font-weight: 800;
  line-height: 1;
  color: #f97316;
}

h1 {
  margin: 16px 0 12px;
  color: #0f172a;
}

p {
  margin: 0;
  color: #475569;
}

.actions {
  margin-top: 24px;
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
