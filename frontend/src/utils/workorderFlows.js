const STORAGE_KEY = 'sxdevops_workorder_flow_types'

export const WORK_ORDER_TYPE_OPTIONS = [
  { label: '应用发布', value: 'deployment' },
  { label: 'SQL 审计', value: 'sql' },
  { label: '事务工单', value: 'transaction' },
]

const DEFAULT_TYPES = ['deployment']

function readBindings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    localStorage.removeItem(STORAGE_KEY)
    return {}
  }
}

function writeBindings(value) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
}

export function getFlowTicketTypes(flow) {
  if (Array.isArray(flow?.ticket_types) && flow.ticket_types.length) {
    return flow.ticket_types
  }
  const bindings = readBindings()
  const flowId = String(flow?.id || '')
  return Array.isArray(bindings[flowId]) && bindings[flowId].length ? bindings[flowId] : DEFAULT_TYPES
}

export function saveFlowTicketTypes(flowId, ticketTypes = DEFAULT_TYPES) {
  if (!flowId) return
  const bindings = readBindings()
  bindings[String(flowId)] = Array.from(new Set(ticketTypes.filter(Boolean)))
  writeBindings(bindings)
}

export function enrichWorkOrderFlows(flows = []) {
  return flows.map((flow) => {
    const ticketTypes = getFlowTicketTypes(flow)
    return {
      ...flow,
      ticket_types: ticketTypes,
      ticket_type_labels: WORK_ORDER_TYPE_OPTIONS
        .filter(option => ticketTypes.includes(option.value))
        .map(option => option.label),
    }
  })
}
