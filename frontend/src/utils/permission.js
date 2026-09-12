import { useAuthStore } from '@/stores/auth'
import { pinia } from '@/stores'

export function can(permission) {
  return useAuthStore(pinia).hasPermission(permission)
}

export function canAny(permissions) {
  return useAuthStore(pinia).hasAnyPermission(permissions)
}

export function canAll(permissions) {
  return useAuthStore(pinia).hasAllPermissions(permissions)
}
