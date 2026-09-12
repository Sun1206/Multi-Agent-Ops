import request from '../request'

// CI 类型
export const getCITypes = () => request.get('/cmdb/ci-types/')
export const createCIType = (data) => request.post('/cmdb/ci-types/', data)
export const updateCIType = (id, data) => request.put(`/cmdb/ci-types/${id}/`, data)
export const deleteCIType = (id) => request.delete(`/cmdb/ci-types/${id}/`)

// 资源节点树
export const getResourceNodeTree = () => request.get('/cmdb/resource-nodes/tree/')
export const createResourceNode = (data) => request.post('/cmdb/resource-nodes/', data)
export const updateResourceNode = (id, data) => request.put(`/cmdb/resource-nodes/${id}/`, data)
export const deleteResourceNode = (id) => request.delete(`/cmdb/resource-nodes/${id}/`)

// 配置项
export const getConfigItems = (params) => request.get('/cmdb/config-items/', { params })
export const createConfigItem = (data) => request.post('/cmdb/config-items/', data)
export const updateConfigItem = (id, data) => request.put(`/cmdb/config-items/${id}/`, data)
export const deleteConfigItem = (id) => request.delete(`/cmdb/config-items/${id}/`)
export const getConfigItemStats = (params) => request.get('/cmdb/config-items/stats/', { params })

// CI 关系
// CI 关系
export const getCIRelations = (params) => request.get('/cmdb/ci-relations/', { params })
export const createCIRelation = (data) => request.post('/cmdb/ci-relations/', data)
export const updateCIRelation = (id, data) => request.put(`/cmdb/ci-relations/${id}/`, data)
export const deleteCIRelation = (id) => request.delete(`/cmdb/ci-relations/${id}/`)

// 成本记录
export const getCostRecords = (params) => request.get('/cmdb/cost-records/', { params })
export const createCostRecord = (data) => request.post('/cmdb/cost-records/', data)

// 资源申请
export const getResourceRequests = (params) => request.get('/cmdb/resource-requests/', { params })
export const createResourceRequest = (data) => request.post('/cmdb/resource-requests/', data)
export const approveRequest = (id, data = {}) => request.post(`/cmdb/resource-requests/${id}/approve/`, data)
export const rejectRequest = (id, data = {}) => request.post(`/cmdb/resource-requests/${id}/reject/`, data)
export const completeRequest = (id, data = {}) => request.post(`/cmdb/resource-requests/${id}/complete/`, data)

// 聚合 API
export const getCmdbDashboard = () => request.get('/cmdb/dashboard/stats/')
export const getCmdbTopology = (params) => request.get('/cmdb/topology/data/', { params })
export const getCmdbCostReport = (params) => request.get('/cmdb/cost/report/', { params })
export const getCmdbOptimization = (params) => request.get('/cmdb/optimization/suggestions/', { params })
