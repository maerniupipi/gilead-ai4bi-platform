// Vue Flow adds selection, measurements and node references while rendering.
// Persist the graph contract, not those changing (and sometimes cyclic) objects.
const NODE_FIELDS = ['id', 'type', 'position', 'data', 'sourcePosition', 'targetPosition', 'parentNode', 'extent', 'expandParent', 'style', 'class', 'hidden', 'width', 'height', 'zIndex', 'draggable', 'connectable', 'selectable', 'deletable', 'focusable']
const EDGE_FIELDS = ['id', 'type', 'source', 'target', 'sourceHandle', 'targetHandle', 'data', 'label', 'labelStyle', 'labelShowBg', 'labelBgStyle', 'labelBgPadding', 'labelBgBorderRadius', 'style', 'class', 'animated', 'markerStart', 'markerEnd', 'updatable', 'selectable', 'deletable', 'focusable', 'hidden', 'zIndex', 'interactionWidth']

function pick(item, fields) {
  return Object.fromEntries(fields.filter(key => item[key] !== undefined).map(key => [key, item[key]]))
}

export function workflowSnapshot(graph) {
  return JSON.parse(JSON.stringify({
    nodes: (graph?.nodes || []).map(node => pick(node, NODE_FIELDS)),
    edges: (graph?.edges || []).map(edge => {
      const saved = pick(edge, EDGE_FIELDS)
      // These defaults are inserted by Vue Flow even before the first edit.
      if (saved.label === '') delete saved.label
      if (saved.data && !Object.keys(saved.data).length) delete saved.data
      return saved
    })
  }))
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
  }
  return value
}

const equal = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right))
export const sameWorkflow = (left, right) => equal(workflowSnapshot(left), workflowSnapshot(right))
const object = value => value != null && typeof value === 'object' && !Array.isArray(value)

/** Three-way merge: independent node/field changes are safe; arrays stay atomic. */
export function mergeWorkflows(base, local, remote) {
  const conflicts = []
  function merge(before, ours, theirs, path) {
    if (equal(ours, theirs) || equal(before, theirs)) return ours
    if (equal(before, ours)) return theirs
    if (object(before) && object(ours) && object(theirs)) {
      const entries = []
      for (const key of new Set([...Object.keys(before), ...Object.keys(ours), ...Object.keys(theirs)])) {
        const value = merge(before[key], ours[key], theirs[key], `${path}.${key}`)
        if (value !== undefined) entries.push([key, value])
      }
      return Object.fromEntries(entries)
    }
    conflicts.push(path)
    return ours
  }
  const snapshots = [base, local, remote].map(workflowSnapshot)
  const workflow = {}
  for (const field of ['nodes', 'edges']) {
    const [before, ours, theirs] = snapshots.map(snapshot => new Map(snapshot[field].map(item => [item.id, item])))
    workflow[field] = []
    for (const id of new Set([...theirs.keys(), ...ours.keys(), ...before.keys()])) {
      const value = merge(before.get(id), ours.get(id), theirs.get(id), `${field}.${id}`)
      if (value !== undefined) workflow[field].push(value)
    }
  }
  const nodeIds = new Set(workflow.nodes.map(node => node.id))
  const labels = new Set()
  for (const node of workflow.nodes) {
    const label = node.data?.label?.trim()
    if (!label) continue
    if (labels.has(label)) conflicts.push(`nodes.${node.id}.data.label`)
    labels.add(label)
  }
  for (const edge of workflow.edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) conflicts.push(`edges.${edge.id}`)
  }
  return { workflow, conflicts }
}
