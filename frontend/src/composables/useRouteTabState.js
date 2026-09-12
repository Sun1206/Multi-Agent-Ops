import { ref, unref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useRouteTabState(options = {}) {
  const {
    tabs,
    defaultTab = '',
    queryKey = 'tab',
  } = options

  const route = useRoute()
  const router = useRouter()
  const activeTab = ref('')

  function resolveTabs() {
    const value = typeof tabs === 'function' ? tabs() : unref(tabs)
    return Array.isArray(value) ? value.filter(Boolean) : []
  }

  function resolveDefaultTab() {
    return typeof defaultTab === 'function' ? defaultTab() : defaultTab
  }

  function normalizeTab(tab) {
    const availableTabs = resolveTabs()
    if (availableTabs.includes(tab)) return tab
    return availableTabs[0] || resolveDefaultTab() || ''
  }

  function updateRouteQuery(tab) {
    const current = typeof route.query[queryKey] === 'string' ? route.query[queryKey] : ''
    if (current === tab) return
    router.replace({
      query: {
        ...route.query,
        [queryKey]: tab,
      },
    })
  }

  function switchTab(tab) {
    const nextTab = normalizeTab(tab)
    if (activeTab.value === nextTab) return
    activeTab.value = nextTab
  }

  watch(
    () => resolveTabs().join('|'),
    () => {
      const routeTab = typeof route.query[queryKey] === 'string' ? route.query[queryKey] : ''
      const nextTab = normalizeTab(routeTab || activeTab.value)
      if (activeTab.value !== nextTab) {
        activeTab.value = nextTab
        return
      }
      if (routeTab !== nextTab) {
        updateRouteQuery(nextTab)
      }
    },
    { immediate: true }
  )

  watch(
    () => route.query[queryKey],
    (tab) => {
      const nextTab = normalizeTab(typeof tab === 'string' ? tab : '')
      if (activeTab.value !== nextTab) {
        activeTab.value = nextTab
      }
    }
  )

  watch(
    activeTab,
    (tab) => {
      if (!tab) return
      updateRouteQuery(tab)
    },
    { immediate: true }
  )

  return {
    activeTab,
    normalizeTab,
    switchTab,
  }
}
