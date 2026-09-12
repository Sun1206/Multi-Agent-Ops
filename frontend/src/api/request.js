import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'sxdevops_token'
const USER_KEY = 'sxdevops_user'
let isHandlingSessionExpired = false

const request = axios.create({
    baseURL: '/api',
    timeout: 15000,
})

function flattenErrorPayload(payload, parentKey = '') {
    if (payload == null) return []
    if (typeof payload === 'string') return [payload]
    if (Array.isArray(payload)) {
        return payload.flatMap(item => flattenErrorPayload(item, parentKey))
    }
    if (typeof payload !== 'object') {
        return [String(payload)]
    }

    return Object.entries(payload).flatMap(([key, value]) => {
        const label = ['detail', 'non_field_errors'].includes(key)
            ? parentKey
            : parentKey
                ? `${parentKey}.${key}`
                : key
        return flattenErrorPayload(value, label).map((item) => {
            if (!label) return item
            return `${label}: ${item}`
        })
    })
}

async function extractErrorMessage(error) {
    if (error.code === 'ECONNABORTED' || String(error.message || '').toLowerCase().includes('timeout')) {
        return '请求超时，请稍后重试'
    }

    const response = error.response
    const data = response?.data

    if (typeof Blob !== 'undefined' && data instanceof Blob) {
        try {
            const text = await data.text()
            if (!text) return error.message || '请求失败'
            try {
                const parsed = JSON.parse(text)
                const messages = flattenErrorPayload(parsed)
                return messages.join('；') || text
            } catch {
                return text
            }
        } catch {
            return error.message || '请求失败'
        }
    }

    const messages = flattenErrorPayload(data)
    if (messages.length) {
        return messages.join('；')
    }

    return error.message || '请求失败'
}

function redirectToLogin() {
    if (window.location.pathname.startsWith('/login')) return
    const redirect = encodeURIComponent(window.location.pathname + window.location.search)
    window.location.href = `/login?redirect=${redirect}`
}

function handleSessionExpired() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)

    if (isHandlingSessionExpired) return
    isHandlingSessionExpired = true
    ElMessage.error('登录状态已过期，请重新登录')
    window.setTimeout(() => {
        redirectToLogin()
        isHandlingSessionExpired = false
    }, 700)
}

request.interceptors.request.use((config) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
        config.headers = config.headers || {}
        config.headers.Authorization = `Token ${token}`
    }
    return config
})

request.interceptors.response.use(
    (response) => response.data,
    async (error) => {
        const status = error.response?.status
        const requestUrl = String(error.config?.url || '')
        const isProfileRequest = requestUrl.includes('/auth/me/')
        const skipErrorMessage = Boolean(error.config?.skipErrorMessage)
        const msg = await extractErrorMessage(error)

        if (status === 401 && !isProfileRequest) {
            handleSessionExpired()
        } else if (!(status === 401 && isProfileRequest) && !skipErrorMessage) {
            ElMessage.error(msg)
        }

        return Promise.reject(error)
    }
)

export default request
