const GENERIC_TASK_TITLE_KEYS = new Set([
  '',
  'ansibleplaybook执行',
  'playbook执行',
  'ansibleplaybook执行任务',
  'playbook执行任务',
  '执行playbook',
  '执行ansibleplaybook',
  'playbook任务',
  'aiopsplaybook任务',
  'aiops智能任务',
  '智能巡检任务',
  'aiopsplaybook任务',
])

function compactTaskTitle(value, maxLength = 48) {
  const text = String(value || '').replace(/\s+/g, ' ').trim().replace(/^[ ，,。；;：:]+|[ ，,。；;：:]+$/g, '')
  return text ? text.slice(0, maxLength).replace(/[ ，,。；;：:]+$/g, '') : ''
}

function stripTaskTitleEnvironmentContext(value) {
  let text = compactTaskTitle(value, 120)
  if (!text) return ''
  text = text
    .replace(/^(?:在|为|给|对)?[^，,。；;：:\s]{1,24}环境(?:下|里|中|上|的)?\s*/, '')
    .replace(/(^|[\s，,。；;：:])(?:在|为|给|对)?[^，,。；;：:\s]{1,24}环境(?:下|里|中|上|的)?\s*/g, ' ')
    .replace(/^(?:在|为|给|对)\s*/, '')
  return compactTaskTitle(text)
}

function taskTitleKey(value) {
  return compactTaskTitle(value).replace(/[\s\-_/：:，,。；;（）()]/g, '').toLowerCase()
}

export function isGenericTaskTitle(value) {
  const key = taskTitleKey(value)
  if (GENERIC_TASK_TITLE_KEYS.has(key)) return true
  return /^(aiops)?(ansible)?playbook(执行|任务|执行任务)?$/.test(key)
}

function requestSummaryTitle(value) {
  let summary = compactTaskTitle(value)
  if (!summary) return ''
  summary = summary
    .replace(/^(请|帮我|麻烦|安排|创建|新建|建个|建一|建立|生成|发起|准备|构建|配置|执行)\s*/, '')
  summary = stripTaskTitleEnvironmentContext(summary)
  summary = summary
    .replace(/^(请|帮我|麻烦|安排|创建|新建|建个|建一|建立|生成|发起|准备|构建|配置|执行)\s*/, '')
  summary = stripTaskTitleEnvironmentContext(summary)
  summary = summary
    .replace(/(任务草稿|草稿|待执行动作|待执行任务)$/, '')
    .replace(/[ ，,。；;：:]+$/g, '')
  return summary && !isGenericTaskTitle(summary) ? compactTaskTitle(summary) : ''
}

function targetNameForTaskTitle(targets = []) {
  const names = []
  targets.forEach((target) => {
    const name = target?.hostname || target?.target_name || target?.name || target?.ip_address || ''
    if (name && !names.includes(name)) names.push(String(name))
  })
  if (!names.length) return ''
  return names.length === 1 ? names[0] : `${names[0]} 等 ${names.length} 台`
}

function localizeTaskPhrase(value) {
  const text = compactTaskTitle(value)
  if (!text) return ''
  const [verb, ...rest] = text.split(/\s+/)
  const target = rest.join(' ')
  const lowered = String(verb || '').toLowerCase()
  if (target && ['restart', 'restarted'].includes(lowered)) return compactTaskTitle(`重启 ${target}`)
  if (target && ['reload', 'reloaded'].includes(lowered)) return compactTaskTitle(`重载 ${target}`)
  if (target && ['start', 'started'].includes(lowered)) return compactTaskTitle(`启动 ${target}`)
  if (target && ['stop', 'stopped'].includes(lowered)) return compactTaskTitle(`停止 ${target}`)
  return text
}

function playbookContentTitle(content) {
  const text = String(content || '')
  if (!text.trim()) return ''
  const nameMatch = text.match(/^\s*-\s*name:\s*["']?(.+?)["']?\s*$/im)
  if (nameMatch) {
    const title = localizeTaskPhrase(nameMatch[1])
    if (title && !['ping', 'debug', 'setup'].includes(title.toLowerCase()) && !isGenericTaskTitle(title)) return title
  }
  const systemctlMatch = text.match(/systemctl\s+(restart|reload|start|stop)\s+([\w@_.-]+)/i)
  if (systemctlMatch) {
    const verbMap = { restart: '重启', reload: '重载', start: '启动', stop: '停止' }
    return compactTaskTitle(`${verbMap[systemctlMatch[1].toLowerCase()] || '执行'} ${systemctlMatch[2]}`)
  }
  const serviceName = text.match(/^\s*name:\s*["']?([\w@_.-]+)["']?\s*$/im)?.[1] || ''
  const serviceState = text.match(/^\s*state:\s*["']?([\w@_.-]+)["']?\s*$/im)?.[1]?.toLowerCase() || ''
  if (serviceName && serviceState) {
    const verbMap = { restarted: '重启', reloaded: '重载', started: '启动', stopped: '停止' }
    return compactTaskTitle(`${verbMap[serviceState] || '处理'} ${serviceName}`)
  }
  return ''
}

export function normalizeTaskDraftTitle(draft = {}) {
  let title = compactTaskTitle(draft?.name || draft?.title || draft?.task_name)
  title = stripTaskTitleEnvironmentContext(title) || title
  if (title && !isGenericTaskTitle(title)) return title
  const payload = draft?.payload || {}
  const summary = requestSummaryTitle(draft?.request_summary || draft?.source_context?.request_summary || draft?.description)
  if (summary) return summary
  const targetName = targetNameForTaskTitle(draft?.target_hosts || [])
  if (draft?.task_type === 'run_playbook') {
    const contentTitle = playbookContentTitle(payload.playbook_content)
    if (contentTitle && targetName) return compactTaskTitle(`${targetName} ${contentTitle}`)
    if (contentTitle) return contentTitle
    const playbookName = compactTaskTitle(payload.playbook_name)
    if (playbookName && !['aiops_generated', 'generated', 'playbook'].includes(playbookName) && !isGenericTaskTitle(playbookName)) {
      return compactTaskTitle(`${playbookName} Playbook 执行`)
    }
    if (targetName) return compactTaskTitle(`${targetName} Playbook 执行`)
  }
  if (draft?.task_type === 'service_status' && payload.service_name) return compactTaskTitle(`${payload.service_name} 服务状态巡检`)
  if (draft?.task_type === 'run_command' && payload.command) return compactTaskTitle(`批量命令执行：${payload.command}`, 48)
  if (targetName) return compactTaskTitle(`${targetName} 智能巡检任务`)
  return title || ''
}

export function normalizePendingActionTitle(action = {}) {
  const payloadTitle = normalizeTaskDraftTitle(action?.action_payload || {})
  if (payloadTitle) return payloadTitle
  const title = compactTaskTitle(action?.title)
  return title || '待执行动作'
}
