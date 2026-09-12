const DEFAULT_ENV_ORDER = ['prod', 'test', 'dev']
const UNASSIGNED_BUSINESS = '\u672a\u5206\u914d'

export const EDGE_COLORS = {
  depends_on: '#8b5cf6',
  runs_on: '#0ea5e9',
  connects_to: '#94a3b8',
}

export function envLabel(env) {
  return {
    prod: '\u751f\u4ea7',
    test: '\u6d4b\u8bd5',
    dev: '\u5f00\u53d1',
    production: '\u751f\u4ea7',
    staging: '\u9884\u53d1',
    testing: '\u6d4b\u8bd5',
    development: '\u5f00\u53d1',
  }[env] || env || UNASSIGNED_BUSINESS
}

function uniqueValues(values = []) {
  const seen = new Set()
  const result = []
  values.forEach(value => {
    if (!value || seen.has(value)) return
    seen.add(value)
    result.push(value)
  })
  return result
}

function sortBusinessLines(values = []) {
  return values.slice().sort((left, right) => {
    if (left === right) return 0
    if (left === UNASSIGNED_BUSINESS) return 1
    if (right === UNASSIGNED_BUSINESS) return -1
    return String(left).localeCompare(String(right), 'zh-CN')
  })
}

export function buildBusinessOptions(resourceTree = [], nodes = [], options = {}) {
  const { includeEmpty = true } = options
  const treeOrder = sortBusinessLines(uniqueValues(
    resourceTree
      .filter(node => node.node_type === 'biz')
      .map(node => node.name)
  ))
  const nodeOrder = sortBusinessLines(uniqueValues(nodes.map(node => node.business_line || UNASSIGNED_BUSINESS)))

  if (includeEmpty) {
    return sortBusinessLines(uniqueValues([...treeOrder, ...nodeOrder]))
  }

  const ordered = treeOrder.filter(name => nodeOrder.includes(name))
  const extras = nodeOrder.filter(name => !ordered.includes(name))
  return sortBusinessLines(uniqueValues([...ordered, ...extras]))
}

export function buildEnvironmentOptions(resourceTree = [], businessLine = null, nodes = [], options = {}) {
  const { includeEmpty = true } = options
  const scopedBusinesses = businessLine
    ? resourceTree.filter(node => node.node_type === 'biz' && node.name === businessLine)
    : resourceTree.filter(node => node.node_type === 'biz')

  const treeOrder = uniqueValues(
    scopedBusinesses.flatMap(node => (node.children || []).map(child => child.name))
  )
  const nodeOrder = uniqueValues(nodes.map(node => node.env).filter(Boolean))

  if (includeEmpty) {
    return uniqueValues([...treeOrder, ...DEFAULT_ENV_ORDER, ...nodeOrder])
  }

  const preferred = uniqueValues([...treeOrder, ...DEFAULT_ENV_ORDER])
  const ordered = preferred.filter(name => nodeOrder.includes(name))
  const extras = nodeOrder.filter(name => !ordered.includes(name))
  return uniqueValues([...ordered, ...extras])
}

function sortWithOrder(valueA, valueB, order) {
  const indexA = order.indexOf(valueA)
  const indexB = order.indexOf(valueB)
  if (indexA === -1 && indexB === -1) return String(valueA).localeCompare(String(valueB))
  if (indexA === -1) return 1
  if (indexB === -1) return -1
  return indexA - indexB
}

function collectTypeOrder(nodes = []) {
  return uniqueValues(nodes.map(node => node.type))
}

export function buildGraphLookup(nodes = [], edges = []) {
  const nodeMap = new Map(nodes.map(node => [node.id, node]))
  const neighborsById = new Map()
  const edgesByNodeId = new Map()

  nodes.forEach(node => {
    neighborsById.set(node.id, new Set())
    edgesByNodeId.set(node.id, [])
  })

  edges.forEach(edge => {
    const sourceId = edge.source
    const targetId = edge.target
    if (!neighborsById.has(sourceId)) neighborsById.set(sourceId, new Set())
    if (!neighborsById.has(targetId)) neighborsById.set(targetId, new Set())
    if (!edgesByNodeId.has(sourceId)) edgesByNodeId.set(sourceId, [])
    if (!edgesByNodeId.has(targetId)) edgesByNodeId.set(targetId, [])
    neighborsById.get(sourceId).add(targetId)
    neighborsById.get(targetId).add(sourceId)
    edgesByNodeId.get(sourceId).push(edge)
    edgesByNodeId.get(targetId).push(edge)
  })

  return { nodeMap, neighborsById, edgesByNodeId }
}

export function layoutTopology({ nodes = [], resourceTree = [], width = 1200, height = 720 }) {
  const padding = { top: 76, right: 32, bottom: 32, left: 32 }
  const innerWidth = Math.max(width - padding.left - padding.right, 320)
  const innerHeight = Math.max(height - padding.top - padding.bottom, 320)
  const businessOrder = buildBusinessOptions(resourceTree, nodes, { includeEmpty: false })
  const typeOrder = collectTypeOrder(nodes)

  if (!businessOrder.length || !nodes.length) {
    const bounds = {
      minX: padding.left,
      minY: padding.top,
      maxX: width - padding.right,
      maxY: height - padding.bottom,
    }
    return {
      nodes: [],
      sections: [],
      laneLabels: [],
      bounds: {
        ...bounds,
        width: bounds.maxX - bounds.minX,
        height: bounds.maxY - bounds.minY,
      },
    }
  }

  const businessGap = 18
  const businessCount = businessOrder.length
  const businessWidth = (innerWidth - businessGap * Math.max(businessCount - 1, 0)) / businessCount
  const positionedNodes = []
  const sections = []
  const laneLabels = []

  businessOrder.forEach((businessLine, businessIndex) => {
    const businessNodes = nodes.filter(node => (node.business_line || UNASSIGNED_BUSINESS) === businessLine)
    const envOrder = buildEnvironmentOptions(resourceTree, businessLine, businessNodes, { includeEmpty: false })
    const envGap = 14
    const envCount = Math.max(envOrder.length, 1)
    const envHeight = (innerHeight - envGap * Math.max(envCount - 1, 0)) / envCount
    const laneX = padding.left + businessIndex * (businessWidth + businessGap)

    laneLabels.push({
      type: 'business',
      text: businessLine,
      x: laneX,
      y: padding.top - 48,
      width: businessWidth,
      height: 34,
    })

    envOrder.forEach((env, envIndex) => {
      const envNodes = businessNodes
        .filter(node => (node.env || 'unknown') === env)
        .sort((left, right) => {
          const typeCompare = sortWithOrder(left.type, right.type, typeOrder)
          if (typeCompare !== 0) return typeCompare
          return left.name.localeCompare(right.name)
        })

      const laneY = padding.top + envIndex * (envHeight + envGap)
      sections.push({
        businessLine,
        env,
        x: laneX,
        y: laneY,
        width: businessWidth,
        height: envHeight,
      })

      laneLabels.push({
        type: 'environment',
        text: envLabel(env),
        x: laneX + 14,
        y: laneY + 14,
      })

      const groupMap = new Map()
      envNodes.forEach(node => {
        if (!groupMap.has(node.type)) groupMap.set(node.type, [])
        groupMap.get(node.type).push(node)
      })

      const groups = Array.from(groupMap.entries()).sort(([left], [right]) => sortWithOrder(left, right, typeOrder))
      const groupGap = 12
      const bodyTop = laneY + 40
      const bodyHeight = Math.max(envHeight - 50, 54)
      const groupCount = Math.max(groups.length, 1)
      const groupHeight = (bodyHeight - groupGap * Math.max(groupCount - 1, 0)) / groupCount

      groups.forEach(([typeName, groupedNodes], groupIndex) => {
        const groupY = bodyTop + groupIndex * (groupHeight + groupGap)
        laneLabels.push({
          type: 'group',
          text: typeName,
          x: laneX + 14,
          y: groupY + 4,
        })

        const contentTop = groupY + 26
        const contentHeight = Math.max(groupHeight - 34, 34)
        const maxColumns = Math.max(1, Math.floor((businessWidth - 40) / 94))
        const columns = Math.min(maxColumns, Math.max(1, groupedNodes.length))
        const rows = Math.max(1, Math.ceil(groupedNodes.length / columns))
        const columnSpacing = columns > 1 ? (businessWidth - 48) / (columns - 1) : 0
        const rowSpacing = rows > 1 ? Math.min(86, contentHeight / (rows - 1)) : 0

        groupedNodes.forEach((node, nodeIndex) => {
          const columnIndex = columns === 1 ? 0 : nodeIndex % columns
          const rowIndex = columns === 1 ? nodeIndex : Math.floor(nodeIndex / columns)
          const x = columns === 1
            ? laneX + businessWidth / 2
            : laneX + 24 + columnIndex * columnSpacing
          const y = rows === 1
            ? contentTop + contentHeight / 2
            : contentTop + rowIndex * rowSpacing

          positionedNodes.push({
            ...node,
            x,
            y,
            r: 24,
            laneKey: `${businessLine}::${env}`,
            groupKey: typeName,
          })
        })
      })
    })
  })

  const fallbackBounds = {
    minX: padding.left,
    minY: padding.top,
    maxX: width - padding.right,
    maxY: height - padding.bottom,
  }
  const bounds = positionedNodes.reduce((result, node) => ({
    minX: Math.min(result.minX, node.x - node.r - 16),
    minY: Math.min(result.minY, node.y - node.r - 18),
    maxX: Math.max(result.maxX, node.x + node.r + 16),
    maxY: Math.max(result.maxY, node.y + node.r + 42),
  }), fallbackBounds)

  return {
    nodes: positionedNodes,
    sections,
    laneLabels,
    bounds: {
      ...bounds,
      width: bounds.maxX - bounds.minX,
      height: bounds.maxY - bounds.minY,
    },
  }
}

export function pointToSegmentDistance(point, start, end) {
  const dx = end.x - start.x
  const dy = end.y - start.y
  if (dx === 0 && dy === 0) {
    const offsetX = point.x - start.x
    const offsetY = point.y - start.y
    return Math.sqrt(offsetX * offsetX + offsetY * offsetY)
  }

  const t = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)))
  const projectionX = start.x + t * dx
  const projectionY = start.y + t * dy
  const distanceX = point.x - projectionX
  const distanceY = point.y - projectionY
  return Math.sqrt(distanceX * distanceX + distanceY * distanceY)
}
