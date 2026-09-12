import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getCurrentUser, login as loginApi, logout as logoutApi } from '@/api/modules/rbac'

const TOKEN_KEY = 'sxdevops_token'
const USER_KEY = 'sxdevops_user'

function loadStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const currentUser = ref(loadStoredUser())
  const initialized = ref(false)

  const isAuthenticated = computed(() => !!token.value && !!currentUser.value)
  const permissions = computed(() => currentUser.value?.effective_permissions || [])
  const displayName = computed(() => {
    if (!currentUser.value) return ''
    return currentUser.value.display_name || currentUser.value.username || ''
  })

  function persistToken(value) {
    token.value = value || ''
    if (token.value) {
      localStorage.setItem(TOKEN_KEY, token.value)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  }

  function persistUser(user) {
    currentUser.value = user || null
    if (currentUser.value) {
      localStorage.setItem(USER_KEY, JSON.stringify(currentUser.value))
    } else {
      localStorage.removeItem(USER_KEY)
    }
  }

  function setUser(user) {
    persistUser(user)
  }

  function clearSession() {
    persistToken('')
    persistUser(null)
  }

  async function bootstrap() {
    if (initialized.value) return currentUser.value
    initialized.value = true

    if (!token.value) {
      persistUser(null)
      return null
    }

    return reloadProfile({ silent: true, clearOnUnauthorized: true })
  }

  async function reloadProfile(options = {}) {
    const { silent = false, clearOnUnauthorized = true } = options
    initialized.value = true
    if (!token.value) return null
    try {
      const user = await getCurrentUser()
      setUser(user)
      return user
    } catch (error) {
      if (error?.response?.status === 401 && clearOnUnauthorized) {
        clearSession()
        return null
      }
      return silent ? currentUser.value : null
    }
  }

  async function login(payload) {
    const response = await loginApi(payload)
    persistToken(response.token)
    setUser(response.user)
    initialized.value = true
    return response.user
  }

  async function logout() {
    try {
      if (token.value) {
        await logoutApi()
      }
    } finally {
      clearSession()
      initialized.value = true
    }
  }

  function hasPermission(code) {
    if (!code) return true
    if (currentUser.value?.is_superuser) return true
    return permissions.value.includes(code)
  }

  function hasAnyPermission(codes = []) {
    if (!codes.length) return true
    return codes.some(code => hasPermission(code))
  }

  function hasAllPermissions(codes = []) {
    if (!codes.length) return true
    return codes.every(code => hasPermission(code))
  }

  return {
    token,
    currentUser,
    initialized,
    isAuthenticated,
    permissions,
    displayName,
    bootstrap,
    login,
    logout,
    clearSession,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    reloadProfile,
  }
})
