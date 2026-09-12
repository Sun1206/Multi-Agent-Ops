<template>
  <div class="fade-in workbench-page-shell k8s-page-shell">
    <section class="hero panel k8s-hero">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="release-header-icon k8s-header-icon"><el-icon><Monitor /></el-icon></span>
          <h2>K8s 集群管理</h2>
          <p class="subtitle inline-subtitle k8s-hero-desc">统一查看集群、工作负载、网络与存储。</p>
        </div>
      </div>
    </section>

    <div class="audit-grid k8s-top-stats">
      <div v-for="card in summaryCards" :key="card.label" class="audit-card audit-card--inline k8s-summary-card" :class="card.tone">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
      </div>
    </div>

    <div class="neo-tabs theme-blue k8s-main-tabs">
      <button v-for="tab in mainTabs" :key="tab.key" class="neo-tab-btn" :class="{ active: activeTab === tab.key }" @click="switchTab(tab.key)">
        <el-icon style="margin-right:4px;"><component :is="tab.icon" /></el-icon>
        {{ tab.label }}
      </button>
    </div>

    <div v-if="activeTab !== 'clusters' && selectedClusterId && !selectedClusterConnected" class="empty-state">
      <div class="empty-icon">⚙</div>
      <div class="empty-text">当前集群未连接，请先测试连接或切换到已连接集群。</div>
      <div style="display:flex;gap:8px;margin-top:8px;">
        <el-button type="primary" @click="switchTab('clusters')">前往集群管理</el-button>
        <el-button @click="refreshView">重新加载</el-button>
      </div>
    </div>

    <template v-if="activeTab === 'clusters'">
      <div class="workbench-card k8s-cluster-card">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">集群列表</span>
            <span class="toolbar-desc">统一管理已接入的 K8s 集群。</span>
          </div>
          <div class="workbench-card-actions">
            <el-button class="filter-refresh-btn" @click="fetchClusters">
              <el-icon><RefreshRight /></el-icon>
              刷新
            </el-button>
            <el-button v-if="canManageK8s" class="filter-refresh-btn" @click="openClusterDialog()">
              <el-icon><Plus /></el-icon>
              新增集群
            </el-button>
          </div>
        </div>
        <div class="workbench-toolbar workbench-toolbar--history k8s-cluster-toolbar">
          <div class="workbench-toolbar-left">
            <el-input v-model="tableSearchKeyword" clearable placeholder="搜索集群名称 / API Server / 描述" style="width: 320px" />
          </div>
          <div class="workbench-toolbar-right">
            <el-tag size="large" type="info">集群总数 {{ clusters.length }}</el-tag>
            <el-tag size="large" type="success">运行中 {{ clusters.filter(item => item.status === 'connected').length }}</el-tag>
          </div>
        </div>
        <el-table :data="filterRows(clusters, ['name', 'api_server', 'status', 'description'])" stripe v-loading="loading" style="width:100%" class="k8s-cluster-table">
          <el-table-column prop="name" label="集群名称" min-width="180">
            <template #default="{ row }">
              <div style="display:flex;align-items:center;gap:8px;">
                <span class="state-pulse" :class="row.status==='connected'?'running':'exited'"></span>
                <span style="font-weight:600">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="api_server" label="API Server" min-width="260" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.status === 'connected' ? 'success' : 'danger'" size="small">{{ row.status === 'connected' ? '运行中' : '未连接' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
          <el-table-column v-if="canManageK8s" label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="testCluster(row)">测试连接</el-button>
              <el-button link type="info" size="small" @click="openClusterDialog(row)">编辑</el-button>
              <el-popconfirm title="确定删除该集群？" @confirm="delCluster(row)">
                <template #reference><el-button link type="danger" size="small">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <template v-else-if="selectedClusterId">
      <div class="workbench-card k8s-resource-card">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">{{ resourcePanelTitle }}</span>
            <span class="toolbar-desc">{{ resourcePanelDesc }}</span>
          </div>
          <div class="workbench-card-actions">
            <el-button @click="refreshView"><el-icon><RefreshRight /></el-icon>刷新</el-button>
          </div>
        </div>

        <div v-if="activeTab === 'workloads'" class="neo-sub-tabs theme-blue k8s-resource-sub-tabs">
          <button v-for="st in workloadSubTabs" :key="st" class="neo-sub-tab-btn" :class="{ active: workloadSub === st }" @click="workloadSub = st">{{ st }}</button>
        </div>
        <div v-else-if="activeTab === 'network'" class="neo-sub-tabs theme-blue k8s-resource-sub-tabs">
          <button v-for="st in networkSubTabs" :key="st" class="neo-sub-tab-btn" :class="{ active: networkSub === st }" @click="networkSub = st">{{ st }}</button>
        </div>
        <div v-else-if="activeTab === 'storage'" class="neo-sub-tabs theme-blue k8s-resource-sub-tabs">
          <button v-for="st in storageSubTabs" :key="st" class="neo-sub-tab-btn" :class="{ active: storageSub === st }" @click="storageSub = st">{{ st }}</button>
        </div>
        <div v-else-if="activeTab === 'config'" class="neo-sub-tabs theme-blue k8s-resource-sub-tabs">
          <button v-for="st in configSubTabs" :key="st" class="neo-sub-tab-btn" :class="{ active: configSub === st }" @click="configSub = st">{{ st }}</button>
        </div>

        <div class="workbench-toolbar workbench-toolbar--history filter-bar--context">
          <div class="workbench-toolbar-left">
            <el-input v-model="tableSearchKeyword" clearable placeholder="搜索当前列表名称、镜像、IP 或描述" style="width: 320px" />
          </div>
          <div class="workbench-toolbar-right k8s-context-toolbar-right">
            <div class="filter-inline-group filter-inline-group--nowrap">
              <div class="filter-inline-context">
                <span class="filter-inline-label">当前集群</span>
                <el-select
                  v-model="selectedClusterId"
                  placeholder="选择集群"
                  @change="onClusterChange"
                  class="industrial-select toolbar-filter-select filter-inline-select"
                  popper-class="k8s-context-popper k8s-context-popper--cluster"
                >
                  <el-option v-for="c in clusters" :key="c.id" :label="c.name" :value="c.id">
                    <div class="context-option-row">
                      <div class="context-option-main">
                        <div class="context-option-head">
                          <div class="context-option-main context-option-main--cluster">
                            <span class="state-pulse" :class="c.status==='connected'?'running':'exited'"></span>
                            <span class="context-option-title">{{ c.name }}</span>
                          </div>
                          <span class="context-status-pill" :class="c.status === 'connected' ? 'context-status-pill--success' : 'context-status-pill--info'">
                            {{ c.status === 'connected' ? '在线' : '离线' }}
                          </span>
                        </div>
                        <span class="context-option-subtitle">{{ clusterOptionMeta(c) }}</span>
                      </div>
                    </div>
                  </el-option>
                </el-select>
              </div>
              <div v-if="needsNamespace" class="filter-inline-context">
                <span class="filter-inline-label">当前命名空间</span>
                <el-select
                  v-model="selectedNamespace"
                  placeholder="选择命名空间"
                  @change="fetchCurrentTab"
                  class="industrial-select toolbar-filter-select filter-inline-select filter-inline-select--namespace"
                  popper-class="k8s-context-popper k8s-context-popper--namespace"
                  :popper-style="namespacePopperStyle"
                >
                  <template #empty>
                    <div class="context-dropdown-empty">当前集群未返回命名空间</div>
                  </template>
                  <el-option label="全部命名空间" value="_all">
                    <div class="context-option-row context-option-row--all">
                      <div class="context-option-main">
                        <div class="context-option-head">
                          <span class="context-option-title">全部命名空间</span>
                          <span class="context-status-pill context-status-pill--info">ALL</span>
                        </div>
                        <span class="context-option-subtitle">跨命名空间聚合视图</span>
                      </div>
                    </div>
                  </el-option>
                  <el-option v-for="ns in namespaceOptions" :key="ns.name" :label="ns.name" :value="ns.name">
                    <div class="context-option-row">
                      <div class="context-option-main">
                        <div class="context-option-head">
                          <span class="context-option-title">{{ ns.name }}</span>
                          <span
                            class="context-status-pill"
                            :class="namespaceStatusTagClass(ns.status)"
                          >
                            {{ namespaceStatusText(ns.status) }}
                          </span>
                        </div>
                        <span class="context-option-subtitle">{{ namespaceOptionMeta(ns) }}</span>
                      </div>
                    </div>
                  </el-option>
                </el-select>
              </div>
            </div>
            <el-tag v-if="summary.pvcs_pending" size="large" type="warning">PVC Pending {{ summary.pvcs_pending }}</el-tag>
          </div>
        </div>

        <template v-if="activeTab === 'nodes'">
      <el-table :data="filterRows(nodes, ['name', 'internal_ip', 'roles', 'version', 'os_image'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="节点名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Ready'?'running':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }"><el-tag :type="row.status === 'Ready' ? 'success' : 'danger'" size="small">{{ row.status === 'Ready' ? '就绪' : '未就绪' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="roles" label="角色" width="120">
          <template #default="{ row }"><el-tag size="small" type="info">{{ row.roles }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="version" label="Kubelet 版本" width="120" />
        <el-table-column prop="internal_ip" label="内部 IP" width="140" />
        <el-table-column label="CPU/内存" width="150">
          <template #default="{ row }">
            <div style="font-size:12px">CPU: <b>{{ row.cpu }}</b></div>
            <div style="font-size:12px">Memory: <b>{{ row.memory }}</b></div>
          </template>
        </el-table-column>
        <el-table-column prop="os_image" label="系统" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('node', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('node', row.name)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ 命名空间 ============ -->
        <template v-if="activeTab === 'namespaces'">
      <el-table :data="filterRows(nsData, ['name', 'status', 'created'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="命名空间名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Active'?'running':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }"><el-tag :type="row.status==='Active'?'success':'danger'" size="small">{{ row.status==='Active'?'活跃':'终止' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('namespace', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ Pod 管理 ============ -->
        <template v-if="activeTab === 'pods'">
      <el-table :data="filterRows(pods, podSearchFields)" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="Pod 名称" min-width="260">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Running'?'running':row.status==='Pending'?'restarting':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status==='Running'?'success':row.status==='Pending'?'warning':'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="restarts" label="重启次数" width="80">
          <template #default="{ row }">
            <span :style="{ color: row.restarts > 0 ? '#f59e0b' : '#10b981', fontWeight: 600 }">{{ row.restarts }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="node" label="节点" width="140" show-overflow-tooltip />
        <el-table-column prop="ip" label="Pod 地址" width="150" show-overflow-tooltip />
        <el-table-column label="容器" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            {{ normalizeContainerNames(row.containers).join(', ') || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="镜像" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            {{ (row.containers || []).map(item => typeof item === 'string' ? item : item?.image).filter(Boolean).join(', ') || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-popconfirm v-if="canManageK8s" title="Restart this pod?" @confirm="restartListedPod(row)">
                <template #reference>
                  <el-tooltip content="重启 Pod" placement="top" :show-after="500">
                    <button class="pod-op-btn pod-op-event"><el-icon :size="14"><RefreshRight /></el-icon></button>
                  </el-tooltip>
                </template>
              </el-popconfirm>
              <el-tooltip v-if="canExecK8s" content="Pod Exec" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#0f766e,#0d9488);" @click="openExecDialog(row)"><el-icon :size="14"><Monitor /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Logs" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" @click="showPodLog(row.name, row.namespace, normalizeContainerNames(row.containers))"><el-icon :size="14"><Monitor /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="View YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('pod', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Events" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('pod', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>

        <template v-if="activeTab === 'workloads'">
      <el-table v-if="workloadSub==='Deployment'" :data="filterRows(deployments, ['name', 'namespace', 'images'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready_replicas===row.replicas?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="副本数" width="100"><template #default="{ row }"><span :style="{color:row.ready_replicas===row.replicas?'#10b981':'#f59e0b',fontWeight:600}">{{ row.ready_replicas }}/{{ row.replicas }}</span></template></el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="176" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManageK8s" content="Scale" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);" @click="openScaleDialog('deployment', row)"><el-icon :size="14"><RefreshRight /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Pods" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="showPodDetail('deployment', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="View YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('deployment', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Events" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('deployment', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='StatefulSet'" :data="filterRows(statefulsets, ['name', 'namespace', 'images'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready_replicas===row.replicas?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="副本数" width="100"><template #default="{ row }"><span :style="{color:row.ready_replicas===row.replicas?'#10b981':'#f59e0b',fontWeight:600}">{{ row.ready_replicas }}/{{ row.replicas }}</span></template></el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="176" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManageK8s" content="Scale" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);" @click="openScaleDialog('statefulset', row)"><el-icon :size="14"><RefreshRight /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Pods" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="showPodDetail('statefulset', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="View YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('statefulset', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Events" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('statefulset', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='DaemonSet'" :data="filterRows(daemonsets, ['name', 'namespace', 'images', 'node_selector'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready===row.desired?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="就绪数" width="100"><template #default="{ row }"><span :style="{color:row.ready===row.desired?'#10b981':'#f59e0b',fontWeight:600}">{{ row.ready }}/{{ row.desired }}</span></template></el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="Pods" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="showPodDetail('daemonset', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="View YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('daemonset', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Events" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('daemonset', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='Job'" :data="filterRows(jobs, ['name', 'namespace', 'images', 'status'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Complete'?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="completions" label="完成数" width="100" />
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status==='Complete'?'success':'warning'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="images" label="镜像" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="Pods" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="showPodDetail('job', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="View YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('job', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Events" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('job', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='CronJob'" :data="filterRows(cronjobs, ['name', 'namespace', 'images', 'schedule'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.suspend?'exited':'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="schedule" label="调度策略" width="140"><template #default="{ row }"><code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:3px">{{ row.schedule }}</code></template></el-table-column>
            <el-table-column label="是否暂停" width="88"><template #default="{ row }"><el-tag :type="row.suspend ? 'danger' : 'success'" size="small">{{ row.suspend ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column prop="last_schedule" label="最近调度" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="Pods" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9);" @click="showPodDetail('cronjob', row.name, row.namespace)"><el-icon :size="14"><Menu /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="View YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('cronjob', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="Events" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('cronjob', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>

        <template v-if="activeTab === 'network'">
      <el-table v-if="networkSub==='Service'" :data="filterRows(services, ['name', 'namespace', 'type', 'cluster_ip', 'ports'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="type" label="类型" width="110"><template #default="{ row }"><el-tag size="small" :type="row.type==='LoadBalancer'?'warning':row.type==='NodePort'?'success':'info'">{{ row.type }}</el-tag></template></el-table-column>
        <el-table-column prop="cluster_ip" label="Cluster IP" width="140" />
        <el-table-column prop="ports" label="端口" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('service', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('service', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="networkSub==='Ingress'" :data="filterRows(ingresses, ['name', 'namespace', 'class', 'hosts', 'address'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="class" label="Ingress Class" width="120" />
        <el-table-column prop="hosts" label="域名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="address" label="地址" width="140" />
        <el-table-column prop="ports" label="端口" width="100" />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('ingress', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('ingress', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ 存储管理 ============ -->
        <template v-if="activeTab === 'storage'">
      <el-table v-if="storageSub==='PV'" :data="filterRows(pvs, ['name', 'capacity', 'access_modes', 'status', 'claim', 'storage_class'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Bound'?'running':row.status==='Available'?'running':'warning'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="capacity" label="容量" width="90" />
        <el-table-column prop="access_modes" label="访问模式" width="100" />
        <el-table-column prop="reclaim_policy" label="回收策略" width="100" />
        <el-table-column prop="status" label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status==='Bound'?'success':row.status==='Available'?'info':'warning'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="claim" label="绑定声明" min-width="250" show-overflow-tooltip />
        <el-table-column prop="storage_class" label="存储类" width="120" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('pv', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="storageSub==='PVC'" :data="filterRows(pvcs, ['name', 'namespace', 'status', 'capacity', 'storage_class', 'volume'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="240">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Bound'?'running':'warning'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="status" label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status==='Bound'?'success':'warning'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="capacity" label="容量" width="90" />
        <el-table-column prop="access_modes" label="访问模式" width="100" />
        <el-table-column prop="storage_class" label="存储类" width="120" />
        <el-table-column prop="volume" label="PV" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('pvc', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('pvc', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="storageSub==='StorageClass'" :data="filterRows(storageclasses, ['name', 'provisioner', 'reclaim_policy', 'binding_mode'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
              <el-tag v-if="row.is_default" type="primary" size="small" style="margin-left:6px">默认</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="provisioner" label="Provisioner" min-width="220" show-overflow-tooltip />
        <el-table-column prop="reclaim_policy" label="回收策略" width="100" />
        <el-table-column prop="binding_mode" label="绑定模式" width="180" />
            <el-table-column label="允许扩展" width="90"><template #default="{ row }"><el-tag :type="row.allow_expansion ? 'success' : 'info'" size="small">{{ row.allow_expansion ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('storageclass', row.name)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ 配置管理 ============ -->
        <template v-if="activeTab === 'config'">
      <el-table v-if="configSub==='ConfigMap'" :data="filterRows(configmaps, ['name', 'namespace', 'data_count', 'created'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="250">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="data_count" label="键值数" width="100" />
        <el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManageK8s" content="编辑配置" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#0f766e,#0d9488);" @click="openConfigEditor('configmap', row)"><el-icon :size="14"><Setting /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('configmap', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="configSub==='Secret'" :data="filterRows(secrets, ['name', 'namespace', 'type', 'data_count', 'created'])" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="250">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="type" label="类型" min-width="240"><template #default="{ row }"><code style="font-size:11px;background:#f1f5f9;padding:2px 6px;border-radius:3px">{{ row.type }}</code></template></el-table-column>
        <el-table-column prop="data_count" label="键值数" width="100" />
        <el-table-column prop="created" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-tooltip v-if="canManageK8s" content="编辑配置" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" style="background:linear-gradient(135deg,#0f766e,#0d9488);" @click="openConfigEditor('secret', row)"><el-icon :size="14"><Setting /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('secret', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
        </template>
      </div>
    </template>
    <template v-else>
      <div class="empty-state">
        <div class="empty-icon">⚙</div>
        <div class="empty-text">当前集群未连接，请先测试连接或切换到已连接集群。</div>
        <div style="display:flex;gap:8px;margin-top:8px;">
          <el-button type="primary" @click="switchTab('clusters')">前往集群管理</el-button>
          <el-button @click="refreshView">重新加载</el-button>
        </div>
      </div>
    </template>
<!-- ============ 集群弹窗 ============ -->
    <el-dialog v-model="clusterDialogVisible" :title="editingClusterId ? '编辑集群' : '新增 K8s 集群'" width="90%" style="max-width:600px;" top="5vh" append-to-body destroy-on-close>
      <el-form :model="clusterForm" label-width="110px">
        <el-form-item label="集群名称"><el-input v-model="clusterForm.name" placeholder="例如 prod-cluster" /></el-form-item>
        <el-form-item label="API Server"><el-input v-model="clusterForm.api_server" placeholder="填写证书匹配的域名或 IP，例如 https://k8s.example.com:6443（可选）" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="clusterForm.description" placeholder="集群用途描述" /></el-form-item>
        <el-form-item label="KubeConfig"><el-input v-model="clusterForm.kubeconfig" type="textarea" :rows="12" placeholder="粘贴 kubeconfig YAML 内容" style="font-family:monospace;font-size:12px;" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="clusterDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCluster" :loading="savingCluster">保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ YAML 查看弹窗 ============ -->
    <el-dialog v-model="yamlDialogVisible" :title="'YAML - ' + yamlResourceName" width="90%" style="max-width:800px;" top="3vh" append-to-body destroy-on-close>
      <div class="yaml-viewer-toolbar">
        <span class="yaml-viewer-badge">{{ yamlResourceType }}</span>
        <el-button size="small" type="primary" plain @click="copyYaml"><el-icon><DocumentCopy /></el-icon> 复制</el-button>
      </div>
      <div class="yaml-viewer-container" v-loading="yamlLoading">
        <pre class="yaml-viewer-code"><code>{{ yamlContent }}</code></pre>
      </div>
    </el-dialog>

    <!-- ============ Pod 详情弹窗 ============ -->
    <el-dialog v-model="podDialogVisible" :title="'Pod 列表 - ' + podWorkloadName" width="95%" style="max-width:1200px;" top="3vh" append-to-body destroy-on-close>
      <el-table :data="filterRows(podList, ['name', 'namespace', 'status', 'node', 'pod_ip', 'host_ip', 'cpu_request', 'memory_request'])" stripe v-loading="podLoading" style="width:100%" size="small">
        <el-table-column prop="name" label="Pod 名称" min-width="280">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Running'?'running':row.status==='Pending'?'restarting':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status==='Running'?'success':row.status==='Pending'?'warning':'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="restarts" label="重启" width="70">
          <template #default="{ row }">
            <span :style="{color: row.restarts > 0 ? '#f59e0b' : '#10b981', fontWeight: 600}">{{ row.restarts }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="node" label="节点" width="120" show-overflow-tooltip />
        <el-table-column label="IP 地址" width="160">
          <template #default="{ row }">
            <div style="font-size:11px;line-height:1.6">
              <div>Pod: <b style="color:#3b82f6">{{ row.pod_ip || '-' }}</b></div>
              <div>Host: <span style="color:#64748b">{{ row.host_ip || '-' }}</span></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="资源" width="150">
          <template #default="{ row }">
            <div style="font-size:11px;line-height:1.6">
              <div>CPU: <el-tag size="small" type="info" style="font-size:11px">{{ row.cpu_request }}</el-tag></div>
              <div>Mem: <el-tag size="small" type="info" style="font-size:11px">{{ row.memory_request }}</el-tag></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="age" label="运行时间" width="90">
          <template #default="{ row }">
            <span style="font-family:monospace;font-size:12px;color:#64748b">{{ row.age }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="176" fixed="right">
          <template #default="{ row }">
            <div style="display:flex;gap:6px;">
              <el-popconfirm v-if="canManageK8s" title="确定重启该 Pod？" @confirm="restartPod(row)">
                <template #reference>
                  <el-tooltip content="重启 Pod" placement="top" :show-after="500">
                    <button class="pod-op-btn pod-op-event"><el-icon :size="14"><RefreshRight /></el-icon></button>
                  </el-tooltip>
                </template>
              </el-popconfirm>
              <el-tooltip content="查看日志" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-log" @click="showPodLog(row.name, row.namespace, row.containers)"><el-icon :size="14"><Monitor /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看 YAML" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-yaml" @click="showYaml('pod', row.name, row.namespace)"><el-icon :size="14"><Document /></el-icon></button>
              </el-tooltip>
              <el-tooltip content="查看事件" placement="top" :show-after="500">
                <button class="pod-op-btn pod-op-event" @click="showEvents('pod', row.name, row.namespace)"><el-icon :size="14"><Bell /></el-icon></button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- ============ 日志查看弹窗 ============ -->
    <el-dialog v-model="logDialogVisible" :title="'日志 - ' + logPodName" width="90%" style="max-width:900px;" top="3vh" append-to-body destroy-on-close>
      <div class="log-viewer-toolbar">
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="yaml-viewer-badge" style="background:linear-gradient(135deg,#10b981,#059669)">{{ logContainer }}</span>
          <el-select v-if="logContainers.length > 1" v-model="logContainer" size="small" style="width:140px" @change="fetchPodLog">
            <el-option v-for="c in logContainers" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:12px;color:#94a3b8">行数:</span>
          <el-select v-model="logTailLines" size="small" style="width:80px" @change="fetchPodLog">
            <el-option :value="50" label="50" /><el-option :value="100" label="100" /><el-option :value="200" label="200" /><el-option :value="500" label="500" />
          </el-select>
          <el-button size="small" type="primary" plain @click="copyLogContent"><el-icon><DocumentCopy /></el-icon> 复制</el-button>
        </div>
      </div>
      <div class="log-viewer-container" v-loading="logLoading" ref="logContainerRef">
        <pre class="log-viewer-code">{{ logContent }}</pre>
      </div>
    </el-dialog>

    <!-- ============ 事件查看弹窗 ============ -->
    <el-dialog v-model="eventsDialogVisible" :title="'事件 - ' + eventsResourceName" width="90%" style="max-width:800px;" top="3vh" append-to-body destroy-on-close>
      <div v-loading="eventsLoading" style="min-height:120px;">
        <div v-if="eventsList.length === 0 && !eventsLoading" style="text-align:center;padding:40px;color:#94a3b8;">
          <el-icon :size="48" style="margin-bottom:8px;opacity:0.4"><Bell /></el-icon>
          <div>暂无事件</div>
        </div>
        <div v-else class="events-timeline">
          <div v-for="(ev, i) in eventsList" :key="i" class="event-item" :class="ev.type === 'Warning' ? 'event-warning' : 'event-normal'">
            <div class="event-indicator"></div>
            <div class="event-body">
              <div class="event-header">
                <el-tag :type="ev.type==='Warning'?'warning':''" size="small" effect="dark" style="font-size:11px">{{ ev.type }}</el-tag>
                <span class="event-reason">{{ ev.reason }}</span>
                <span v-if="ev.count > 1" class="event-count">脳{{ ev.count }}</span>
                <span class="event-time">{{ formatEventTime(ev.last_time) }}</span>
              </div>
              <div class="event-message">{{ ev.message }}</div>
              <div class="event-source" v-if="ev.source">{{ ev.source }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="execDialogVisible" :title="'Pod Terminal - ' + execForm.pod_name" width="92%" style="max-width:1100px;" top="4vh" append-to-body destroy-on-close>
      <div class="filter-bar" style="margin-bottom:8px;">
        <el-tag size="large" type="info">{{ execForm.namespace }}</el-tag>
        <el-select
          v-if="execContainers.length > 1"
          v-model="execForm.container"
          size="small"
          style="width:180px"
          @change="reconnectExecTerminal"
        >
          <el-option v-for="name in execContainers" :key="name" :label="name" :value="name" />
        </el-select>
        <el-tag v-else-if="execForm.container" size="large">容器: {{ execForm.container }}</el-tag>
        <el-tag :type="execStatusTagType" size="large">{{ execStatusText }}</el-tag>
        <el-button size="small" plain :disabled="!execDialogVisible" @click="reconnectExecTerminal">
          <el-icon><RefreshRight /></el-icon> 重连
        </el-button>
        <el-button size="small" plain :disabled="!execSessionLog" @click="downloadExecSessionLog">下载浼氳瘽日志</el-button>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
        <el-button
          v-for="preset in execPresetCommands"
          :key="preset.command"
          size="small"
          plain
          @click="runExecPreset(preset.command)"
        >
          {{ preset.label }}
        </el-button>
      </div>
      <div ref="execTerminalRef" style="height:420px;background:#0f172a;border-radius:12px;overflow:hidden;padding:8px;"></div>
    </el-dialog>

    <el-dialog v-model="scaleDialogVisible" :title="'弹性伸缩 - ' + scaleForm.name" width="90%" style="max-width:420px;" top="8vh" append-to-body destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="工作负载">
          <el-tag>{{ scaleForm.workload_type }}</el-tag>
        </el-form-item>
        <el-form-item label="命名空间">
          <el-tag type="info">{{ scaleForm.namespace }}</el-tag>
        </el-form-item>
        <el-form-item label="副本数">
          <el-input-number v-model="scaleForm.replicas" :min="0" :max="200" controls-position="right" style="width:180px;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scaleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="scaleLoading" @click="submitScale">搴旂敤</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="configEditorVisible" :title="configDialogTitle" width="90%" style="max-width:980px;" top="3vh" append-to-body destroy-on-close>
      <div class="filter-bar" style="margin-bottom:8px;">
        <el-tag type="info">{{ configForm.namespace }}</el-tag>
        <el-tag>{{ configForm.type }}</el-tag>
        <el-tag v-if="configForm.rollback_available" type="warning">可回滚</el-tag>
        <el-tag v-if="configForm.revision_count" type="success">历史 {{ configForm.revision_count }}</el-tag>
        <span class="config-editor-note">仅编辑 data/stringData，保存前建议先预览差异。</span>
      </div>
      <el-input v-model="configForm.content" type="textarea" :rows="18" placeholder="key: value" style="font-family:'Cascadia Code','Consolas',monospace;" />
      <div class="config-history-panel">
        <div class="config-history-head">
          <div class="config-history-title">
            <strong class="config-history-heading">历史版本</strong>
            <span class="config-history-note">每次保存前和回滚前都会自动留档，可随时预览差异并回滚到指定版本。</span>
          </div>
          <el-button size="small" plain :loading="configRevisionLoading" @click="fetchConfigRevisions">刷新历史</el-button>
        </div>
        <el-table :data="configRevisions" size="small" stripe v-loading="configRevisionLoading" max-height="220" empty-text="暂无历史版本">
          <el-table-column prop="created_at" label="时间" min-width="180" show-overflow-tooltip />
          <el-table-column prop="action" label="动作" width="110">
            <template #default="{ row }">
              <el-tag :type="row.action === 'rollback' ? 'warning' : 'info'" size="small">
                {{ row.action === 'rollback' ? '回滚前快照' : '更新前快照' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="120" show-overflow-tooltip />
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <div style="display:flex;gap:6px;">
                <el-button link type="primary" @click="previewConfigRevision(row)">预览</el-button>
                <el-button v-if="canManageK8s" link type="warning" @click="applyConfigRevisionRollback(row)">回滚</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div style="display:flex;justify-content:space-between;gap:8px;margin-top:8px;flex-wrap:wrap;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <el-button @click="configEditorVisible = false">关闭</el-button>
          <el-button type="info" plain :loading="configPreviewLoading" @click="previewConfigChange">预览本次变更</el-button>
          <el-button type="warning" plain :disabled="!configForm.rollback_available" :loading="configPreviewLoading" @click="previewConfigRollback">预览最近一次回滚</el-button>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <el-button v-if="configForm.rollback_available" type="warning" :loading="configSaving" @click="applyConfigRollback">回滚到上一版本</el-button>
          <el-button type="primary" :loading="configSaving" @click="saveConfigResource">保存配置</el-button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="diffDialogVisible" :title="diffDialogTitle" width="90%" style="max-width:980px;" top="4vh" append-to-body destroy-on-close>
      <pre class="log-output terminal-log" style="min-height:320px;">{{ diffDialogContent || '暂无差异' }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouteTabState } from '@/composables/useRouteTabState'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { DocumentCopy, Document, Monitor, Bell, Plus, Connection, FolderOpened, Menu, RefreshRight, Box, WarningFilled, Setting } from '@element-plus/icons-vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import {
  getK8sClusters, createK8sCluster, updateK8sCluster, deleteK8sCluster,
  testK8sConnection, getK8sSummary, getK8sNamespaces,
  getK8sPods, getK8sServices, getK8sDeployments, restartK8sPod,
  getK8sNodes, getK8sStatefulSets, getK8sDaemonSets, getK8sJobs, getK8sCronJobs,
  getK8sIngresses, getK8sPVs, getK8sPVCs, getK8sStorageClasses,
  getK8sConfigMaps, getK8sSecrets, getK8sResourceYaml,
  getK8sWorkloadPods, getK8sPodLogs, getK8sResourceEvents,
  scaleK8sWorkload, getK8sConfigResourceDetail,
  previewK8sConfigResource, updateK8sConfigResource,
  getK8sConfigRevisions, getK8sConfigRevisionPreview,
  getK8sConfigRollbackPreview, rollbackK8sConfigResource,
  rollbackK8sConfigResourceToRevision,
} from '@/api/modules/container'

const authStore = useAuthStore()
const canManageK8s = computed(() => authStore.hasPermission('ops.k8s.manage'))
const canExecK8s = computed(() => authStore.hasPermission('ops.k8s.exec'))

const mainTabs = [
  { key: 'clusters',   label: '集群管理', icon: 'OfficeBuilding' },
  { key: 'nodes',      label: '节点管理', icon: 'Monitor' },
  { key: 'namespaces', label: '命名空间', icon: 'FolderOpened' },
  { key: 'workloads',  label: '工作负载', icon: 'Cpu' },
  { key: 'pods',       label: 'Pod 管理', icon: 'Box' },
  { key: 'network',    label: '网络管理', icon: 'Connection' },
  { key: 'storage',    label: '存储管理', icon: 'Coin' },
  { key: 'config',     label: '配置管理', icon: 'Setting' },
]

const tabState = useRouteTabState({
  tabs: () => mainTabs.map(item => item.key),
  defaultTab: 'clusters',
})
const activeTab = tabState.activeTab
const loading = ref(false)
const namespacePopperStyle = {
  width: '220px',
  minWidth: '220px',
  maxWidth: '220px',
}

// ====== 集群 ======
const clusters = ref([])
const selectedClusterId = ref(null)
const selectedNamespace = ref('_all')
const namespaces = ref([])
const tableSearchKeyword = ref('')
const selectedCluster = computed(() => clusters.value.find(item => item.id === selectedClusterId.value) || null)
const selectedClusterConnected = computed(() => selectedCluster.value?.status === 'connected')
const namespaceOptions = computed(() => normalizeNamespaceItems(namespaces.value))
const namespaceCache = ref({})

const needsNamespace = computed(() => ['pods', 'namespaces', 'workloads', 'network', 'config'].includes(activeTab.value) || (activeTab.value === 'storage' && storageSub.value === 'PVC'))

function createEmptySummary() {
  return {
    status: 'disconnected',
    nodes_total: 0,
    nodes_ready: 0,
    pods_total: 0,
    pods_abnormal: 0,
    total_restarts: 0,
    workloads_total: 0,
    pvcs_pending: 0,
    alerts: [],
  }
}

const summary = ref(createEmptySummary())
const lastNonZeroSummaryByCluster = ref({})
const effectiveSummary = computed(() => {
  const cachedSummary = lastNonZeroSummaryByCluster.value[selectedClusterId.value]
  const base = isZeroRuntimeSummary(summary.value) && cachedSummary
    ? { ...cachedSummary, degraded: true, alerts: summary.value.alerts || cachedSummary.alerts || [] }
    : { ...summary.value }
  mergeLoadedResourceSummary(base)
  return base
})
const summaryCards = computed(() => {
  if (activeTab.value === 'clusters') {
    const connected = clusters.value.filter(item => item.status === 'connected').length
    return [
      { label: '集群数', value: clusters.value.length, meta: '纳管集群', tone: '' },
      { label: '已连接', value: connected, meta: '可访问集群', tone: 'success-card' },
      { label: '离线集群', value: Math.max(clusters.value.length - connected, 0), meta: '待排查目标', tone: 'warning-card' },
      { label: '当前集群', value: selectedCluster.value?.name || '未选择', meta: '活动上下文', tone: 'context-card' },
    ]
  }
  return [
    { label: 'Ready 节点', value: `${effectiveSummary.value.nodes_ready}/${effectiveSummary.value.nodes_total}`, meta: '节点健康度', tone: '' },
    { label: 'Pod 总数', value: effectiveSummary.value.pods_total, meta: '运行实例', tone: 'success-card' },
    { label: '异常 Pod', value: effectiveSummary.value.pods_abnormal, meta: '需要处理', tone: 'warning-card' },
    { label: '工作负载', value: effectiveSummary.value.workloads_total, meta: 'Deployment / Job 等', tone: 'danger-card' },
  ]
})
const podSearchFields = [
  'name',
  'namespace',
  'status',
  'node',
  'ip',
  (row) => normalizeContainerNames(row.containers),
  (row) => (row.containers || []).map(item => typeof item === 'string' ? item : item?.image),
]

// ====== 鍚?Tab 鏁版嵁 ======
const nodes = ref([])
const nsData = ref([])
const pods = ref([])
const deployments = ref([])
const statefulsets = ref([])
const daemonsets = ref([])
const jobs = ref([])
const cronjobs = ref([])
const services = ref([])
const ingresses = ref([])
const pvs = ref([])
const pvcs = ref([])
const storageclasses = ref([])
const configmaps = ref([])
const secrets = ref([])

// ====== Sub-tabs ======
const workloadSubTabs = ['Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob']
const networkSubTabs = ['Service', 'Ingress']
const storageSubTabs = ['PV', 'PVC', 'StorageClass']
const configSubTabs = ['ConfigMap', 'Secret']
const workloadSub = useRouteTabState({
  tabs: () => workloadSubTabs,
  defaultTab: 'Deployment',
  queryKey: 'workloadSub',
}).activeTab
const networkSub = useRouteTabState({
  tabs: () => networkSubTabs,
  defaultTab: 'Service',
  queryKey: 'networkSub',
}).activeTab
const storageSub = useRouteTabState({
  tabs: () => storageSubTabs,
  defaultTab: 'PV',
  queryKey: 'storageSub',
}).activeTab
const configSub = useRouteTabState({
  tabs: () => configSubTabs,
  defaultTab: 'ConfigMap',
  queryKey: 'configSub',
}).activeTab

const resourcePanelMeta = computed(() => {
  const map = {
    nodes: {
      title: '节点列表',
      desc: '延续任务工作台的列表密度，集中查看节点状态、版本与基础资源。',
    },
    namespaces: {
      title: '命名空间列表',
      desc: '统一承接命名空间状态和元数据视图，保持工作台式筛选与浏览节奏。',
    },
    workloads: {
      title: '工作负载列表',
      desc: '将 Deployment、StatefulSet 等资源收拢到同一工作台卡片内浏览和操作。',
    },
    pods: {
      title: 'Pod 列表',
      desc: '在同一工作台容器中完成检索、日志、重启和事件查看。',
    },
    network: {
      title: '网络资源列表',
      desc: '统一查看 Service 与 Ingress，保持与任务工作台一致的承载层级。',
    },
    storage: {
      title: '存储资源列表',
      desc: '聚合 PV、PVC 与存储类资源，用一张卡片承接筛选与列表。',
    },
    config: {
      title: '配置资源列表',
      desc: '统一承接 ConfigMap 与 Secret 的检索、编辑和 YAML 查看。',
    },
  }
  return map[activeTab.value] || {
    title: '资源列表',
    desc: '统一使用任务工作台的上下文筛选和列表承载方式。',
  }
})

const resourcePanelTitle = computed(() => resourcePanelMeta.value.title)
const resourcePanelDesc = computed(() => resourcePanelMeta.value.desc)

// ====== 切换 Tab ======
function switchTab(tab) {
  tabState.switchTab(tab)
}

function normalizeSearchValue(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeSearchValue).join(' ')
  }
  if (value && typeof value === 'object') {
    return Object.values(value).map(normalizeSearchValue).join(' ')
  }
  return String(value || '').toLowerCase()
}

function filterRows(rows, fields = []) {
  const keyword = tableSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return rows
  return rows.filter((row) => fields.some((field) => {
    const value = typeof field === 'function' ? field(row) : row?.[field]
    return normalizeSearchValue(value).includes(keyword)
  }))
}

function summaryAlertType(level) {
  const mapping = { success: 'success', warning: 'warning', danger: 'error' }
  return mapping[level] || 'info'
}

function safeInt(value) {
  const number = Number(value || 0)
  return Number.isFinite(number) ? number : 0
}

function runtimeSummaryTotal(payload) {
  return [
    'nodes_total',
    'pods_total',
    'services_total',
    'ingresses_total',
    'workloads_total',
    'pvcs_total',
    'configmaps_total',
    'secrets_total',
  ].reduce((total, key) => total + safeInt(payload?.[key]), 0)
}

function isZeroRuntimeSummary(payload) {
  return Boolean(payload?.degraded) && runtimeSummaryTotal(payload) === 0
}

function rememberUsableSummary(payload) {
  if (!payload || isZeroRuntimeSummary(payload) || runtimeSummaryTotal(payload) === 0) return
  if (!selectedClusterId.value) return
  lastNonZeroSummaryByCluster.value = {
    ...lastNonZeroSummaryByCluster.value,
    [selectedClusterId.value]: { ...payload },
  }
}

function podStatusAbnormal(row) {
  return !['Running', 'Succeeded'].includes(String(row?.status || ''))
}

function mergeLoadedResourceSummary(target) {
  if (nodes.value.length) {
    target.nodes_total = Math.max(safeInt(target.nodes_total), nodes.value.length)
    target.nodes_ready = Math.max(
      safeInt(target.nodes_ready),
      nodes.value.filter((item) => item.status === 'Ready').length,
    )
  }
  if (pods.value.length) {
    target.pods_total = Math.max(safeInt(target.pods_total), pods.value.length)
    target.pods_abnormal = Math.max(safeInt(target.pods_abnormal), pods.value.filter(podStatusAbnormal).length)
    target.total_restarts = Math.max(
      safeInt(target.total_restarts),
      pods.value.reduce((total, item) => total + safeInt(item.restarts), 0),
    )
  }
  const loadedWorkloads = deployments.value.length + statefulsets.value.length + daemonsets.value.length + jobs.value.length + cronjobs.value.length
  if (loadedWorkloads) {
    target.workloads_total = Math.max(safeInt(target.workloads_total), loadedWorkloads)
  }
}

function normalizeNamespaceItem(item) {
  if (typeof item === 'string') {
    const name = item.trim()
    return name ? { name, status: '', created: '', labels: {}, labelCount: 0 } : null
  }
  if (!item || typeof item !== 'object') return null
  const name = String(item.name || item.namespace || item.metadata?.name || '').trim()
  if (!name) return null
  const labels = item.labels && typeof item.labels === 'object'
    ? item.labels
    : (item.metadata?.labels && typeof item.metadata.labels === 'object' ? item.metadata.labels : {})
  return {
    ...item,
    name,
    status: String(item.status || item.phase || item.status?.phase || '').trim(),
    created: String(item.created || item.creation_timestamp || item.creationTimestamp || item.metadata?.creationTimestamp || '').trim(),
    labels,
    labelCount: Object.keys(labels).length,
  }
}

function normalizeNamespaceItems(items) {
  const uniqueMap = new Map()
  for (const item of Array.isArray(items) ? items : []) {
    const normalized = normalizeNamespaceItem(item)
    if (normalized?.name) uniqueMap.set(normalized.name, normalized)
  }
  return Array.from(uniqueMap.values()).sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
}

function namespaceStatusText(status) {
  const value = String(status || '').trim()
  if (!value) return '可用'
  if (value === 'Active') return '活跃'
  if (value === 'Terminating') return '终止中'
  return value
}

function namespaceStatusTagType(status) {
  const value = String(status || '').trim()
  if (!value || value === 'Active') return 'success'
  if (value === 'Terminating') return 'warning'
  return 'info'
}

function namespaceStatusTagClass(status) {
  const type = namespaceStatusTagType(status)
  if (type === 'success') return 'context-status-pill--success'
  if (type === 'warning') return 'context-status-pill--warning'
  return 'context-status-pill--info'
}

function namespaceOptionMeta(namespace) {
  const created = String(namespace?.created || '').trim()
  const meta = []
  if (created) meta.push(`创建于 ${created.replace('T', ' ').slice(0, 16)}`)
  if (namespace?.labelCount) meta.push(`${namespace.labelCount} 个标签`)
  if (meta.length) return meta.join(' · ')
  return '命名空间资源视图'
}

function clusterOptionMeta(cluster) {
  const endpoint = String(cluster?.api_server || '').trim()
  const description = String(cluster?.description || '').trim()
  const meta = []
  if (endpoint) {
    try {
      meta.push(new URL(endpoint).host || endpoint)
    } catch {
      meta.push(endpoint)
    }
  }
  if (description) meta.push(description)
  return meta.join(' · ') || 'Kubernetes 集群连接'
}

function syncSelectedNamespace(preferred = selectedNamespace.value) {
  if (!preferred || preferred === '_all') {
    selectedNamespace.value = '_all'
    return
  }
  selectedNamespace.value = namespaceOptions.value.some((item) => item.name === preferred) ? preferred : '_all'
}

function setClusterStatus(clusterId, status) {
  const cluster = clusters.value.find((item) => item.id === clusterId)
  if (cluster && status && cluster.status !== status) {
    cluster.status = status
  }
}

async function loadNamespaces(clusterId, options = {}) {
  const { force = false } = options
  if (!clusterId) {
    namespaces.value = []
    return []
  }
  if (!force && namespaceCache.value[clusterId]?.length) {
    namespaces.value = namespaceCache.value[clusterId]
    return namespaces.value
  }
  try {
    const items = normalizeNamespaceItems(await getK8sNamespaces(clusterId))
    namespaces.value = items
    namespaceCache.value = {
      ...namespaceCache.value,
      [clusterId]: items,
    }
    return items
  } catch (e) {
    namespaces.value = []
    return []
  }
}

async function fetchClusters() {
  loading.value = true
  try {
    const res = await getK8sClusters()
    clusters.value = res.results || res

    const connectedCluster = clusters.value.find(item => item.status === 'connected')
    const current = clusters.value.find(item => item.id === selectedClusterId.value)
    if (current) {
      selectedClusterId.value = current.id
    } else if (activeTab.value !== 'clusters' && connectedCluster) {
      selectedClusterId.value = connectedCluster.id
    } else {
      selectedClusterId.value = clusters.value[0]?.id || null
    }
    if (!selectedClusterId.value) {
      summary.value = createEmptySummary()
    }

    if (selectedClusterId.value && activeTab.value !== 'clusters') {
      await onClusterChange()
    } else if (!selectedClusterId.value) {
      summary.value = createEmptySummary()
    }
  } catch (e) { /* */ }
  loading.value = false
}

async function fetchSummary(options = {}) {
  const { probe = false } = options
  if (!selectedClusterId.value) {
    summary.value = createEmptySummary()
    return false
  }
  if (!probe && !selectedClusterConnected.value) {
    summary.value = createEmptySummary()
    return false
  }
  try {
    summary.value = await getK8sSummary(selectedClusterId.value)
    rememberUsableSummary(summary.value)
    setClusterStatus(selectedClusterId.value, summary.value.status || 'connected')
    return true
  } catch (e) {
    const cachedSummary = lastNonZeroSummaryByCluster.value[selectedClusterId.value]
    if (cachedSummary) {
      summary.value = { ...cachedSummary, degraded: true }
      return true
    }
    summary.value = createEmptySummary()
    setClusterStatus(selectedClusterId.value, 'error')
    return false
  }
}

function refreshView() {
  if (activeTab.value === 'clusters') {
    fetchClusters()
    return
  }
  refreshClusterContext()
}

async function refreshClusterContext(options = {}) {
  const { forceSummary = true, forceNamespaces = true } = options
  const previousNamespace = selectedNamespace.value
  if (!selectedClusterId.value) {
    summary.value = createEmptySummary()
    return
  }
  const namespaceTask = needsNamespace.value
    ? loadNamespaces(selectedClusterId.value, { force: forceNamespaces })
    : Promise.resolve([])
  const summaryTask = forceSummary
    ? fetchSummary({ probe: true })
    : Promise.resolve(selectedClusterConnected.value)
  const [summaryReady] = await Promise.all([summaryTask, namespaceTask])
  if (!summaryReady) {
    return
  }
  syncSelectedNamespace(previousNamespace)
  await fetchCurrentTab()
}

async function onClusterChange() {
  selectedNamespace.value = '_all'
  await refreshClusterContext({ forceSummary: true, forceNamespaces: false })
}

async function fetchCurrentTab() {
  if (activeTab.value !== 'clusters' && (!selectedClusterId.value || !selectedClusterConnected.value)) return
  loading.value = true
  const id = selectedClusterId.value
  const ns = selectedNamespace.value
  try {
    switch (activeTab.value) {
      case 'nodes': nodes.value = await getK8sNodes(id); break
      case 'namespaces':
        if (!namespaceOptions.value.length) {
          await loadNamespaces(id, { force: false })
        }
        nsData.value = namespaceOptions.value
        break
      case 'pods': pods.value = await getK8sPods(id, ns); break
      case 'workloads':
        if (workloadSub.value === 'Deployment') deployments.value = await getK8sDeployments(id, ns)
        else if (workloadSub.value === 'StatefulSet') statefulsets.value = await getK8sStatefulSets(id, ns)
        else if (workloadSub.value === 'DaemonSet') daemonsets.value = await getK8sDaemonSets(id, ns)
        else if (workloadSub.value === 'Job') jobs.value = await getK8sJobs(id, ns)
        else if (workloadSub.value === 'CronJob') cronjobs.value = await getK8sCronJobs(id, ns)
        break
      case 'network':
        if (networkSub.value === 'Service') services.value = await getK8sServices(id, ns)
        else ingresses.value = await getK8sIngresses(id, ns)
        break
      case 'storage':
        if (storageSub.value === 'PV') pvs.value = await getK8sPVs(id)
        else if (storageSub.value === 'PVC') pvcs.value = await getK8sPVCs(id, ns)
        else storageclasses.value = await getK8sStorageClasses(id)
        break
      case 'config':
        if (configSub.value === 'ConfigMap') configmaps.value = await getK8sConfigMaps(id, ns)
        else secrets.value = await getK8sSecrets(id, ns)
        break
    }
  } catch (e) {
    ElMessage.error('获取数据失败')
  }
  loading.value = false
}

function normalizeContainerNames(containers) {
  return (containers || []).map((item) => (typeof item === 'string' ? item : item?.name)).filter(Boolean)
}

// ====== 集群 CRUD ======
const clusterDialogVisible = ref(false)
const editingClusterId = ref(null)
const savingCluster = ref(false)
const clusterForm = ref({ name: '', api_server: '', description: '', kubeconfig: '' })

function openClusterDialog(cluster) {
  if (!canManageK8s.value) return
  if (cluster) {
    editingClusterId.value = cluster.id
    clusterForm.value = { name: cluster.name, api_server: cluster.api_server, description: cluster.description, kubeconfig: '' }
  } else {
    editingClusterId.value = null
    clusterForm.value = { name: '', api_server: '', description: '', kubeconfig: '' }
  }
  clusterDialogVisible.value = true
}

async function saveCluster() {
  if (!canManageK8s.value) return
  if (!clusterForm.value.name) return ElMessage.warning('请填写集群名称')
  if (!clusterForm.value.kubeconfig && !editingClusterId.value) return ElMessage.warning('请粘贴 KubeConfig')
  savingCluster.value = true
  try {
    const data = { ...clusterForm.value }
    if (!data.kubeconfig) delete data.kubeconfig
    if (editingClusterId.value) {
      await updateK8sCluster(editingClusterId.value, data)
      ElMessage.success('集群已更新')
    } else {
      await createK8sCluster(data)
      ElMessage.success('集群已添加')
    }
    clusterDialogVisible.value = false
    fetchClusters()
  } catch (e) { /* */ }
  savingCluster.value = false
}

async function testCluster(row) {
  if (!canManageK8s.value) return
  try {
    const res = await testK8sConnection(row.id)
    if (res.success) ElMessage.success(res.message)
    else ElMessage.error(res.message)
    fetchClusters()
  } catch (e) { ElMessage.error('连接测试失败') }
}

async function delCluster(row) {
  if (!canManageK8s.value) return
  try {
    await deleteK8sCluster(row.id)
    ElMessage.success('集群已删除')
    fetchClusters()
  } catch (e) { ElMessage.error('删除失败') }
}

// ====== YAML 查看 ======
const yamlDialogVisible = ref(false)
const yamlContent = ref('')
const yamlResourceName = ref('')
const yamlResourceType = ref('')
const yamlLoading = ref(false)

async function showYaml(type, name, namespace) {
  if (!selectedClusterId.value) return ElMessage.warning('请先选择集群')
  yamlResourceType.value = type
  yamlResourceName.value = name
  yamlContent.value = ''
  yamlDialogVisible.value = true
  yamlLoading.value = true
  try {
    const ns = namespace || selectedNamespace.value || 'default'
    const res = await getK8sResourceYaml(selectedClusterId.value, type, name, ns)
    yamlContent.value = res.yaml || res
  } catch (e) {
    yamlContent.value = '# 获取 YAML 失败'
    ElMessage.error('获取 YAML 失败')
  }
  yamlLoading.value = false
}

function copyYaml() {
  navigator.clipboard.writeText(yamlContent.value).then(() => {
  ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

// ====== Pod 详情 ======
const podDialogVisible = ref(false)
const podWorkloadName = ref('')
const podWorkloadType = ref('')
const podWorkloadNamespace = ref('default')
const podList = ref([])
const podLoading = ref(false)

async function showPodDetail(workloadType, name, namespace) {
  if (!selectedClusterId.value) return ElMessage.warning('请先选择集群')
  podWorkloadType.value = workloadType
  podWorkloadName.value = name
  podWorkloadNamespace.value = namespace || selectedNamespace.value || 'default'
  podList.value = []
  podDialogVisible.value = true
  podLoading.value = true
  try {
    const ns = podWorkloadNamespace.value
    podList.value = await getK8sWorkloadPods(selectedClusterId.value, workloadType, name, ns)
  } catch (e) {
    ElMessage.error('获取 Pod 列表失败')
  }
  podLoading.value = false
}

async function restartPod(row) {
  if (!canManageK8s.value) return
  try {
    await performPodRestart(row)
    await showPodDetail(podWorkloadType.value, podWorkloadName.value, podWorkloadNamespace.value)
  } catch (e) {
    ElMessage.error('Pod 重启失败')
  }
}

async function performPodRestart(row) {
  const res = await restartK8sPod(selectedClusterId.value, row.name, row.namespace)
  ElMessage.success(res.message || 'Pod 正在重启')
  await fetchSummary()
}

async function restartListedPod(row) {
  if (!canManageK8s.value) return
  try {
    await performPodRestart(row)
    await fetchCurrentTab()
  } catch (e) {
    ElMessage.error('Pod 重启失败')
  }
}

// ====== Pod 日志 ======
const logDialogVisible = ref(false)
const logPodName = ref('')
const logContent = ref('')
const logContainer = ref('')
const logContainers = ref([])
const logTailLines = ref(200)
const logLoading = ref(false)
const logPodNs = ref('default')
const logContainerRef = ref(null)

function showPodLog(podName, namespace, containers) {
  logPodName.value = podName
  logPodNs.value = namespace || 'default'
  logContainers.value = containers || ['main']
  logContainer.value = logContainers.value[0]
  logContent.value = ''
  logDialogVisible.value = true
  fetchPodLog()
}

async function fetchPodLog() {
  logLoading.value = true
  try {
    const res = await getK8sPodLogs(selectedClusterId.value, logPodName.value, logPodNs.value, logContainer.value, logTailLines.value)
    logContent.value = res.logs || ''
    await nextTick()
    if (logContainerRef.value) {
      logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    }
  } catch (e) {
    logContent.value = '# 获取日志失败'
    ElMessage.error('获取日志失败')
  }
  logLoading.value = false
}

function copyLogContent() {
  navigator.clipboard.writeText(logContent.value).then(() => {
    ElMessage.success('Copied')
  }).catch(() => { ElMessage.error('Copy failed') })
}

// ====== 事件查看 ======
const execDialogVisible = ref(false)
const execForm = ref({ pod_name: '', namespace: 'default', container: '' })
const execContainers = ref([])
const execTerminalRef = ref(null)
const execSessionLog = ref('')
const execPresetCommands = [
  { label: 'pwd', command: 'pwd' },
  { label: 'env', command: 'env' },
  { label: 'ps aux', command: 'ps aux' },
  { label: 'df -h', command: 'df -h' },
  { label: 'kubectl get pods', command: 'kubectl get pods' },
]
const execWsStatus = ref('disconnected')
const execStatusText = computed(() => ({
  connecting: '连接中',
  connected: '已连接',
  error: '异常',
  disconnected: '未连接',
}[execWsStatus.value] || '未连接'))
const execStatusTagType = computed(() => ({
  connecting: 'warning',
  connected: 'success',
  error: 'danger',
  disconnected: 'info',
}[execWsStatus.value] || 'info'))

let execTerminal = null
let execFitAddon = null
let execSocket = null
let execResizeObserver = null
let execClosingByClient = false

function appendExecSessionLog(chunk) {
  if (!chunk) return
  execSessionLog.value += chunk
  if (execSessionLog.value.length > 200000) {
    execSessionLog.value = execSessionLog.value.slice(-200000)
  }
}

function appendExecSystemLine(message) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}\n`
  appendExecSessionLog(line)
}

function sendExecInput(data) {
  if (!execSocket || execSocket.readyState !== WebSocket.OPEN) {
  ElMessage.warning('终端未连接')
    return false
  }
  execSocket.send(JSON.stringify({ type: 'input', data }))
  return true
}

function runExecPreset(command) {
  if (sendExecInput(`${command}\r`) && execTerminal) {
    execTerminal.focus()
  }
}

function downloadExecSessionLog() {
  if (!execSessionLog.value) return
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const filename = `k8s-exec-${execForm.value.pod_name || 'session'}-${stamp}.log`
  const blob = new Blob([execSessionLog.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function openExecDialog(row) {
  const containers = normalizeContainerNames(row.containers)
  execContainers.value = containers
  execForm.value = {
    pod_name: row.name,
    namespace: row.namespace || 'default',
    container: containers[0] || '',
  }
  execSessionLog.value = ''
  execDialogVisible.value = true
}

function initExecTerminal() {
  disposeExecTerminal()
  if (!execTerminalRef.value) return

  execTerminal = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
    theme: {
      background: '#0f172a',
      foreground: '#e2e8f0',
      cursor: '#22c55e',
      selectionBackground: '#22c55e33',
    },
    scrollback: 5000,
  })
  execFitAddon = new FitAddon()
  execTerminal.loadAddon(execFitAddon)
  execTerminal.open(execTerminalRef.value)
  execFitAddon.fit()
  execTerminal.writeln('\x1b[1;36mAI Ops Pod Terminal\x1b[0m')
  execTerminal.writeln('\x1b[2mConnecting to pod...\x1b[0m')
  execTerminal.writeln('')

  execTerminal.onData((data) => {
    if (execSocket && execSocket.readyState === WebSocket.OPEN) {
      execSocket.send(JSON.stringify({ type: 'input', data }))
    }
  })

  execResizeObserver = new ResizeObserver(() => {
    if (execFitAddon) {
      execFitAddon.fit()
      sendExecResize()
    }
  })
  execResizeObserver.observe(execTerminalRef.value)
}

function sendExecResize() {
  if (!execTerminal || !execSocket || execSocket.readyState !== WebSocket.OPEN) return
  execSocket.send(JSON.stringify({
    type: 'resize',
    cols: execTerminal.cols,
    rows: execTerminal.rows,
  }))
}

function connectExecTerminal() {
  if (!selectedClusterId.value || !execForm.value.pod_name || !execTerminal) return
  disconnectExecSocket()
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = localStorage.getItem('sxdevops_token') || ''
  const params = new URLSearchParams({
    token,
    pod_name: execForm.value.pod_name,
    namespace: execForm.value.namespace || 'default',
  })
  if (execForm.value.container) {
    params.set('container', execForm.value.container)
  }

  execClosingByClient = false
  execWsStatus.value = 'connecting'
  appendExecSystemLine(`connecting to ${execForm.value.pod_name}`)
  execSocket = new WebSocket(`${protocol}//${window.location.host}/ws/k8s/exec/${selectedClusterId.value}/?${params.toString()}`)

  execSocket.onopen = () => {
    execWsStatus.value = 'connected'
    appendExecSystemLine(`connected to ${execForm.value.pod_name}`)
    sendExecResize()
  }

  execSocket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'output') {
        if (execTerminal) execTerminal.write(payload.data || '')
        appendExecSessionLog(payload.data || '')
      } else if (payload.type === 'connected') {
        if (execTerminal) execTerminal.writeln(`\x1b[1;32m${payload.message}\x1b[0m`)
        appendExecSystemLine(payload.message || 'terminal connected')
      } else if (payload.type === 'error') {
        execWsStatus.value = 'error'
        if (execTerminal) execTerminal.writeln(`\x1b[1;31m${payload.message}\x1b[0m`)
        appendExecSystemLine(payload.message || 'terminal error')
      }
    } catch {
      if (execTerminal) execTerminal.write(event.data)
      appendExecSessionLog(event.data || '')
    }
  }

  execSocket.onclose = () => {
    if (execClosingByClient) {
      execClosingByClient = false
      return
    }
    if (execWsStatus.value !== 'error') {
      execWsStatus.value = 'disconnected'
    }
    appendExecSystemLine('terminal disconnected')
  }

  execSocket.onerror = () => {
    execWsStatus.value = 'error'
    appendExecSystemLine('terminal websocket error')
  }
}

function disconnectExecSocket() {
  if (execSocket) {
    execClosingByClient = true
    execSocket.close()
    execSocket = null
  }
}

function disposeExecTerminal() {
  disconnectExecSocket()
  if (execResizeObserver) {
    execResizeObserver.disconnect()
    execResizeObserver = null
  }
  if (execTerminal) {
    execTerminal.dispose()
    execTerminal = null
  }
  execFitAddon = null
  execWsStatus.value = 'disconnected'
}

function reconnectExecTerminal() {
  if (!execDialogVisible.value) return
  nextTick(() => {
    initExecTerminal()
    connectExecTerminal()
  })
}

const scaleDialogVisible = ref(false)
const scaleLoading = ref(false)
const scaleForm = ref({ workload_type: 'deployment', name: '', namespace: 'default', replicas: 1 })

function openScaleDialog(workloadType, row) {
  scaleForm.value = {
    workload_type: workloadType,
    name: row.name,
    namespace: row.namespace || 'default',
    replicas: Number(row.replicas || 0),
  }
  scaleDialogVisible.value = true
}

async function submitScale() {
  if (!selectedClusterId.value) return
  scaleLoading.value = true
  try {
    const res = await scaleK8sWorkload(selectedClusterId.value, { ...scaleForm.value })
    ElMessage.success(res.message || 'Scale submitted')
    scaleDialogVisible.value = false
    await fetchSummary()
    await fetchCurrentTab()
  } catch (e) {
    ElMessage.error('Scale failed')
  }
  scaleLoading.value = false
}

const configEditorVisible = ref(false)
const configPreviewLoading = ref(false)
const configSaving = ref(false)
const configRevisionLoading = ref(false)
const configRevisions = ref([])
const diffDialogVisible = ref(false)
const diffDialogTitle = ref('差异预览')
const diffDialogContent = ref('')
const configForm = ref({
  type: 'configmap',
  name: '',
  namespace: 'default',
  content: '',
  rollback_available: false,
  revision_count: 0,
})
const configDialogTitle = computed(() => `${configForm.value.type} 配置 - ${configForm.value.name}`)

function syncConfigRevisionState(detail = {}) {
  if (typeof detail.rollback_available === 'boolean') {
    configForm.value.rollback_available = detail.rollback_available
  }
  if (typeof detail.revision_count === 'number') {
    configForm.value.revision_count = detail.revision_count
  } else {
    configForm.value.revision_count = configRevisions.value.length
  }
}

async function fetchConfigRevisions() {
  if (!selectedClusterId.value || !configForm.value.name) return
  configRevisionLoading.value = true
  try {
    const res = await getK8sConfigRevisions(
      selectedClusterId.value,
      configForm.value.type,
      configForm.value.name,
      configForm.value.namespace,
    )
    configRevisions.value = res.items || []
    syncConfigRevisionState({ revision_count: configRevisions.value.length, rollback_available: configRevisions.value.length > 0 })
  } catch (e) {
    configRevisions.value = []
    ElMessage.error('加载配置历史失败')
  }
  configRevisionLoading.value = false
}

async function openConfigEditor(type, row) {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const detail = await getK8sConfigResourceDetail(selectedClusterId.value, type, row.name, row.namespace)
    configForm.value = {
      type,
      name: row.name,
      namespace: row.namespace || 'default',
      content: detail.text || '',
      rollback_available: detail.rollback_available || false,
      revision_count: detail.revision_count || 0,
    }
    configRevisions.value = []
    configEditorVisible.value = true
    await fetchConfigRevisions()
  } catch (e) {
    ElMessage.error('加载配置详情失败')
  }
  configPreviewLoading.value = false
}

async function previewConfigChange() {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const res = await previewK8sConfigResource(selectedClusterId.value, { ...configForm.value })
    diffDialogTitle.value = `保存前预览 - ${configForm.value.name}`
    diffDialogContent.value = res.diff || '暂无差异'
    diffDialogVisible.value = true
  } catch (e) {
    ElMessage.error('配置预览失败')
  }
  configPreviewLoading.value = false
}

async function saveConfigResource() {
  if (!selectedClusterId.value) return
  configSaving.value = true
  try {
    const res = await updateK8sConfigResource(selectedClusterId.value, { ...configForm.value })
    configForm.value.content = res.resource?.text || configForm.value.content
    syncConfigRevisionState(res.resource)
      ElMessage.success(res.message || '配置已更新')
    await fetchConfigRevisions()
    await fetchCurrentTab()
    await fetchSummary()
  } catch (e) {
    ElMessage.error('保存配置失败')
  }
  configSaving.value = false
}

async function previewConfigRollback() {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const res = await getK8sConfigRollbackPreview(selectedClusterId.value, configForm.value.type, configForm.value.name, configForm.value.namespace)
    diffDialogTitle.value = `最近回滚预览 - ${configForm.value.name}`
    diffDialogContent.value = res.diff || '当前版本与最近一次回滚没有差异'
    diffDialogVisible.value = true
  } catch (e) {
    ElMessage.error('回滚预览失败')
  }
  configPreviewLoading.value = false
}

async function applyConfigRollback() {
  if (!selectedClusterId.value) return
  configSaving.value = true
  try {
    const res = await rollbackK8sConfigResource(selectedClusterId.value, {
      type: configForm.value.type,
      name: configForm.value.name,
      namespace: configForm.value.namespace,
    })
    configForm.value.content = res.resource?.text || configForm.value.content
    syncConfigRevisionState(res.resource)
    ElMessage.success(res.message || '配置已回滚')
    await fetchConfigRevisions()
    await fetchCurrentTab()
    await fetchSummary()
  } catch (e) {
    ElMessage.error('回滚失败')
  }
  configSaving.value = false
}

async function previewConfigRevision(row) {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const res = await getK8sConfigRevisionPreview(
      selectedClusterId.value,
      configForm.value.type,
      configForm.value.name,
      configForm.value.namespace,
      row.id,
    )
    diffDialogTitle.value = `历史版本预览 - #${row.id}`
    diffDialogContent.value = res.diff || '暂无差异'
    diffDialogVisible.value = true
  } catch (e) {
    ElMessage.error('加载历史版本预览失败')
  }
  configPreviewLoading.value = false
}

async function applyConfigRevisionRollback(row) {
  if (!selectedClusterId.value) return
  configSaving.value = true
  try {
    const res = await rollbackK8sConfigResourceToRevision(selectedClusterId.value, {
      type: configForm.value.type,
      name: configForm.value.name,
      namespace: configForm.value.namespace,
      revision_id: row.id,
    })
    configForm.value.content = res.resource?.text || configForm.value.content
    syncConfigRevisionState(res.resource)
    ElMessage.success(res.message || '已回滚到指定历史版本')
    await fetchConfigRevisions()
    await fetchCurrentTab()
    await fetchSummary()
  } catch (e) {
    ElMessage.error('回滚到指定历史版本失败')
  }
  configSaving.value = false
}

const eventsDialogVisible = ref(false)
const eventsResourceName = ref('')
const eventsList = ref([])
const eventsLoading = ref(false)

async function showEvents(type, name, namespace) {
  if (!selectedClusterId.value) return ElMessage.warning('请先选择集群')
  eventsResourceName.value = `${type}/${name}`
  eventsList.value = []
  eventsDialogVisible.value = true
  eventsLoading.value = true
  try {
    const ns = namespace || selectedNamespace.value || 'default'
    eventsList.value = await getK8sResourceEvents(selectedClusterId.value, type, name, ns)
  } catch (e) {
    ElMessage.error('获取事件失败')
  }
  eventsLoading.value = false
}

function formatEventTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const now = new Date()
    const diff = Math.floor((now - d) / 1000)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch {
    return iso
  }
}

// ====== 初始化 ======
watch(activeTab, (tab, prev) => {
  if (!tab || tab === prev) return
  if (tab === 'clusters') {
    fetchClusters()
  } else if (selectedClusterId.value) {
    refreshClusterContext({ forceSummary: false, forceNamespaces: false })
  }
})

watch(workloadSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'workloads' && selectedClusterId.value) fetchCurrentTab()
})
watch(networkSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'network' && selectedClusterId.value) fetchCurrentTab()
})
watch(storageSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'storage' && selectedClusterId.value) fetchCurrentTab()
})
watch(configSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'config' && selectedClusterId.value) fetchCurrentTab()
})

watch(execDialogVisible, (visible) => {
  if (visible) {
    reconnectExecTerminal()
  } else {
    disposeExecTerminal()
  }
})

onMounted(() => { fetchClusters() })
onBeforeUnmount(() => { disposeExecTerminal() })
</script>

<style scoped>
.k8s-page-shell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.k8s-page-shell :deep(.panel) {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(250, 252, 255, 0.96) 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  padding: 14px 16px;
}

.k8s-hero {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
}

.k8s-hero-desc {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
}

.k8s-page-shell :deep(.release-hero-title-row) {
  display: flex;
  align-items: center;
  gap: 12px;
}

.k8s-page-shell :deep(.release-hero-title-inline) {
  flex-wrap: wrap;
}

.k8s-page-shell :deep(.hero h2) {
  margin: 0;
  font-size: 23px;
  color: #0f172a;
}

.k8s-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  border: 1px solid rgba(36, 91, 219, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.k8s-main-tabs {
  margin-top: 0;
  margin-bottom: 0;
}

.k8s-resource-sub-tabs {
  margin: 0;
  padding-top: 0;
  padding-bottom: 0;
  margin-top: -8px;
  margin-bottom: 6px;
}

.k8s-page-shell :deep(.neo-tab-btn),
.k8s-page-shell :deep(.neo-sub-tab-btn) {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 13px;
}

.k8s-page-shell :deep(.neo-tabs) {
  padding: 3px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.k8s-page-shell :deep(.neo-tab-btn.active) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.14), 0 8px 16px rgba(59, 130, 246, 0.12);
}

.k8s-page-shell :deep(.k8s-main-tabs .neo-tab-btn) {
  min-height: 38px;
  padding: 0 20px;
  border-radius: 8px;
}

.k8s-page-shell :deep(.k8s-main-tabs .neo-tab-btn.active) {
  color: #245bdb;
  font-weight: 600;
  background: rgba(36, 91, 219, 0.12);
  box-shadow: inset 0 0 0 1px rgba(36, 91, 219, 0.12), 0 8px 16px rgba(36, 91, 219, 0.08);
}

.k8s-page-shell :deep(.k8s-main-tabs .neo-tab-btn:hover) {
  background: rgba(36, 91, 219, 0.06);
}

.k8s-page-shell .workbench-card,
.k8s-page-shell .tab-content {
  min-width: 0;
}

.k8s-page-shell .tab-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.k8s-page-shell .k8s-summary-grid,
.k8s-page-shell .audit-grid {
  gap: 8px;
}

.k8s-summary-card {
  justify-content: space-between;
  height: 68px;
  min-height: 68px;
  padding: 14px 16px;
  overflow: hidden;
}

.k8s-summary-card .stat-label {
  flex: 0 1 auto;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k8s-summary-card .stat-value {
  flex: 1 1 auto;
  min-width: 0;
  font-size: clamp(18px, 2.8vw, 24px);
  line-height: 1;
  color: #1f2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k8s-summary-card.audit-card--warning {
  background: linear-gradient(180deg, #fffdfa 0%, #ffffff 100%);
}

.k8s-summary-card.audit-card--success {
  background: linear-gradient(180deg, #fbfffd 0%, #ffffff 100%);
}

.k8s-summary-card.audit-card--danger {
  background: linear-gradient(180deg, #fffafb 0%, #ffffff 100%);
}

.k8s-summary-card.audit-card--action:hover {
  border-color: rgba(36, 91, 219, 0.16);
  box-shadow: 0 10px 20px rgba(36, 91, 219, 0.06);
}

.k8s-summary-card.audit-card--action.is-active {
  border-color: rgba(36, 91, 219, 0.24);
  background: linear-gradient(180deg, #f4f7ff 0%, #ffffff 100%);
  box-shadow: 0 0 0 1px rgba(36, 91, 219, 0.05), 0 12px 22px rgba(36, 91, 219, 0.08);
}

.k8s-page-shell .k8s-context-card {
  padding: 12px;
}

.k8s-page-shell .stats-grid.k8s-summary-grid {
  margin-bottom: 0 !important;
}

.k8s-page-shell .workbench-toolbar--history {
  margin-top: 0;
}

.k8s-page-shell :deep(.section-toolbar) {
  padding-bottom: 2px;
}

.k8s-page-shell :deep(.toolbar-title) {
  color: #0f172a;
}

.k8s-page-shell :deep(.toolbar-desc) {
  color: #64748b;
}

.filter-bar--context {
  align-items: center;
}

.k8s-context-toolbar-right {
  justify-content: flex-end;
  flex-wrap: nowrap;
  gap: 10px;
}

.filter-inline-group {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.filter-inline-group--nowrap {
  flex-wrap: nowrap;
}

.filter-inline-context {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.filter-inline-label {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  line-height: 1;
  white-space: nowrap;
}

.filter-inline-select {
  width: 220px;
  min-width: 220px;
  flex: 0 0 220px;
}

.filter-inline-select--namespace {
  width: 220px;
  min-width: 220px;
  flex-basis: 220px;
}

.context-option-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}

.context-option-row--all .context-option-title {
  color: #1d4ed8;
}

.context-option-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  gap: 2px;
}

.context-option-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.context-option-main--cluster {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.context-option-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.context-option-subtitle {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #64748b;
}

.context-status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  min-width: 40px;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  border: 1px solid transparent;
  box-sizing: border-box;
}

.context-status-pill--success {
  color: #65a30d;
  background: #f0fdf4;
  border-color: #d9f99d;
}

.context-status-pill--warning {
  color: #b45309;
  background: #fffbeb;
  border-color: #fde68a;
}

.context-status-pill--info {
  color: #64748b;
  background: #f8fafc;
  border-color: #cbd5e1;
}

.context-dropdown-empty {
  padding: 16px 10px;
  text-align: center;
  font-size: 12px;
  color: #64748b;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(255, 255, 255, 0.98));
}

:deep(.k8s-context-popper.el-select-dropdown),
:deep(.k8s-context-popper.el-popper) {
  box-sizing: border-box;
  background: #ffffff !important;
  border-radius: 16px;
  border: 1px solid rgba(203, 213, 225, 0.72) !important;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12) !important;
  overflow: hidden;
  backdrop-filter: blur(12px);
}

:deep(.k8s-context-popper--cluster.el-select-dropdown),
:deep(.k8s-context-popper--cluster.el-popper) {
  width: 220px !important;
  min-width: 220px !important;
  max-width: 220px !important;
}

:deep(.k8s-context-popper--namespace.el-select-dropdown),
:deep(.k8s-context-popper--namespace.el-popper) {
  width: 220px !important;
  min-width: 220px !important;
  max-width: 220px !important;
}

:deep(.k8s-context-popper--namespace .el-select-dropdown) {
  width: 220px !important;
  min-width: 220px !important;
  max-width: 220px !important;
}

:deep(.k8s-context-popper .el-popper__arrow::before) {
  border-color: rgba(203, 213, 225, 0.72) !important;
  background: #fff !important;
}

:deep(.k8s-context-popper .el-select-dropdown__wrap),
:deep(.k8s-context-popper .el-scrollbar),
:deep(.k8s-context-popper .el-select-dropdown__list) {
  background: #ffffff !important;
}

:deep(.k8s-context-popper .el-scrollbar__view) {
  padding: 4px;
  background: #ffffff;
}

:deep(.k8s-context-popper .el-select-dropdown__item) {
  min-height: 52px;
  height: auto;
  padding: 8px 10px;
  border-radius: 12px;
  color: #0f172a !important;
  font-family: inherit !important;
  white-space: normal !important;
  margin-bottom: 2px;
  background: transparent !important;
  transition: background-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
  box-sizing: border-box;
}

:deep(.k8s-context-popper .el-select-dropdown__item.hover),
:deep(.k8s-context-popper .el-select-dropdown__item:hover) {
  background: rgba(241, 245, 249, 0.92) !important;
  transform: translateY(-1px);
}

:deep(.k8s-context-popper .el-select-dropdown__item.selected),
:deep(.k8s-context-popper .el-select-dropdown__item.is-selected) {
  background: rgba(219, 234, 254, 0.92) !important;
  color: #1d4ed8 !important;
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.3);
}

:deep(.k8s-context-popper .el-select-dropdown__item.is-disabled) {
  opacity: 0.55;
}

.k8s-resource-card {
  padding-top: 12px;
  gap: 8px;
}

.k8s-cluster-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 12px;
}

.k8s-cluster-card :deep(.section-toolbar) {
  margin-bottom: 4px;
}

.k8s-cluster-toolbar {
  margin-top: -6px;
  margin-bottom: 2px;
}

.k8s-cluster-table :deep(.el-table__header-wrapper th) {
  background: #f8fafc;
}

.k8s-page-shell :deep(.el-table) {
  --el-table-border-color: rgba(15, 23, 42, 0.08);
  --el-table-header-bg-color: #f8fafc;
  --el-table-row-hover-bg-color: #f8fbff;
  border-radius: 14px;
  overflow: hidden;
}

.k8s-page-shell :deep(.el-table th.el-table__cell) {
  height: 42px;
  padding: 0;
}

.k8s-page-shell :deep(.el-table th.el-table__cell > .cell) {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.k8s-page-shell :deep(.el-table .el-table__cell) {
  padding: 10px 0;
}

.k8s-page-shell :deep(.el-table .cell) {
  line-height: 1.5;
}

.k8s-page-shell :deep(.el-table .el-button.is-link) {
  font-size: 12px;
}

.k8s-page-shell :deep(.el-table__fixed-right::before) {
  left: 72px;
  right: auto;
  width: 8px;
  background: linear-gradient(90deg, rgba(15, 23, 42, 0.1), rgba(15, 23, 42, 0));
}

@media (max-width: 1200px) {
  .filter-bar--context .workbench-toolbar-left {
    flex-wrap: wrap;
  }

  .filter-inline-group--nowrap {
    flex-wrap: wrap;
  }
}

@media (max-width: 980px) {
  .k8s-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-inline-context {
    width: 100%;
  }

  .filter-inline-select {
    flex: 1 1 auto;
    width: auto;
    min-width: 0;
  }
}
</style>




