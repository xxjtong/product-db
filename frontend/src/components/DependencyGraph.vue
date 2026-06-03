<template>
  <div class="dep-graph" ref="container">
    <div class="flex gap-8 items-center mb-8">
      <h3 style="margin:0">依赖关系图</h3>
    </div>
    <canvas ref="canvas" class="dep-canvas"></canvas>
    <div v-if="hovered" class="dep-tooltip" :style="{ left: tipX + 'px', top: tipY + 'px' }">
      <strong>{{ hovered.name }}</strong>
      <div class="text-sm text-muted">{{ hovered.category }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { fetchSolution, fetchDependencies, fetchCategories, fetchProduct } from '../api'

const props = defineProps<{ solutionId: number }>()

const container = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const canvasW = ref(800)
const canvasH = ref(400)
const hovered = ref<any>(null)
const tipX = ref(0)
const tipY = ref(0)

interface GraphNode {
  id: number; name: string; category: string; x: number; y: number; angle: number; isRoot?: boolean
}
interface GraphEdge { from: number; to: number; type: string; label: string }

let resizeObserver: ResizeObserver | null = null
let nodes: GraphNode[] = []
let edges: GraphEdge[] = []
let nodeMap: Record<number, GraphNode> = {}

async function loadGraph() {
  const res = await fetchSolution(props.solutionId)
  const solution = res.solution

  // Fetch dependencies for each product in the solution
  const productIds = (solution.items || []).map((i: any) => i.product_id)
  const allDeps: any[] = []

  for (const pid of productIds) {
    try {
      const data = await fetchDependencies(pid)
      for (const d of data.dependencies || []) {
        allDeps.push(d)
      }
    } catch { /* skip */ }
  }

  // Build nodes from solution items
  const catMap: Record<number, string> = {}
  const prodMap: Record<number, string> = {}
  for (const item of solution.items || []) {
    prodMap[item.product_id] = item.product_name || `#${item.product_id}`
  }

  // Fetch category names for dependency targets
  try {
    const catData = await fetchCategories()
    for (const c of catData.categories || []) {
      catMap[c.id] = c.name
    }
  } catch { /* skip */ }

  // Add dependency target products/categories as nodes
  for (const d of allDeps) {
    if (d.depends_on_product_id && !prodMap[d.depends_on_product_id]) {
      try {
        const pd = await fetchProduct(d.depends_on_product_id)
        prodMap[d.depends_on_product_id] = pd.product?.name || `#${d.depends_on_product_id}`
        if (!productIds.includes(d.depends_on_product_id)) {
          productIds.push(d.depends_on_product_id)
        }
      } catch { /* skip */ }
    }
  }

  const solutionNodes: GraphNode[] = []
  const depNodes: GraphNode[] = []

  for (const pid of productIds) {
    const isInSolution = (solution.items || []).some((i: any) => i.product_id === pid)
    const node: GraphNode = {
      id: pid,
      name: prodMap[pid] || `#${pid}`,
      category: '',
      x: 0, y: 0, angle: 0,
      isRoot: isInSolution,
    }
    if (isInSolution) {
      solutionNodes.push(node)
    } else {
      depNodes.push(node)
    }
    nodeMap[pid] = node
  }

  // Assign angles based on position in the ring
  solutionNodes.forEach((n, i) => {
    n.angle = solutionNodes.length > 1 ? (2 * Math.PI * i) / solutionNodes.length - Math.PI / 2 : 0
  })
  depNodes.forEach((n, i) => {
    n.angle = depNodes.length > 1 ? (2 * Math.PI * i) / depNodes.length - Math.PI / 2 : 0
  })

  nodes = [...solutionNodes, ...depNodes]

  // Build edges
  edges = allDeps.map(d => ({
    from: d.product_id,
    to: d.depends_on_product_id || d.depends_on_category_id,
    type: d.dependency_type,
    label: d.description || '',
  }))

  relayout()
  draw()
}

function relayout() {
  const cw = canvasW.value
  const ch = canvasH.value
  const centerX = cw / 2
  const centerY = ch / 2
  const radius = Math.min(cw, ch) * 0.28
  const outerRadius = Math.min(cw, ch) * 0.42

  for (const n of nodes) {
    const r = n.isRoot ? radius : outerRadius
    n.x = centerX + r * Math.cos(n.angle)
    n.y = centerY + r * Math.sin(n.angle)
  }
}

function draw() {
  const ctx = canvas.value?.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvasW.value, canvasH.value)

  // Draw edges
  for (const e of edges) {
    const from = nodeMap[e.from]
    const to = nodeMap[e.to]
    if (!from && e.from) continue
    if (!from || !to) continue

    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.strokeStyle = e.type === 'required' ? '#e94560' : e.type === 'recommended' ? '#0f3460' : '#94a3b8'
    ctx.lineWidth = e.type === 'required' ? 2 : 1
    ctx.setLineDash(e.type === 'optional' ? [4, 4] : [])
    ctx.stroke()
    ctx.setLineDash([])

    // Arrow
    const dx = to.x - from.x
    const dy = to.y - from.y
    const len = Math.sqrt(dx * dx + dy * dy)
    if (len > 0) {
      const ux = dx / len
      const uy = dy / len
      ctx.beginPath()
      ctx.moveTo(to.x - ux * 22, to.y - uy * 22)
      ctx.lineTo(to.x - ux * 22 - uy * 6, to.y - uy * 22 + ux * 6)
      ctx.lineTo(to.x - ux * 22 + uy * 6, to.y - uy * 22 - ux * 6)
      ctx.closePath()
      ctx.fillStyle = e.type === 'required' ? '#e94560' : e.type === 'recommended' ? '#0f3460' : '#94a3b8'
      ctx.fill()

      // Edge label
      if (e.label) {
        const mx = (from.x + to.x) / 2
        const my = (from.y + to.y) / 2 - 6
        ctx.font = '10px Inter, sans-serif'
        ctx.fillStyle = '#64748b'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        ctx.fillText(e.label, mx, my)
      }
    }
  }

  // Draw nodes
  for (const n of nodes) {
    const r = n.isRoot ? 16 : 12
    ctx.beginPath()
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = n.isRoot ? '#0f3460' : '#f1f5f9'
    ctx.fill()
    ctx.strokeStyle = n.isRoot ? '#1a1a2e' : '#94a3b8'
    ctx.lineWidth = 2
    ctx.stroke()

    // Count badge inside circle for solution nodes
    if (n.isRoot) {
      ctx.font = 'bold 10px Inter, sans-serif'
      ctx.fillStyle = '#fff'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText('●', n.x, n.y)
    }

    // Label below node
    ctx.font = '11px Inter, Noto Sans SC, sans-serif'
    ctx.fillStyle = n.isRoot ? '#1e293b' : '#475569'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    const labelY = n.y + r + 4
    // Word-wrap long names
    const maxLabelW = 100
    const words = n.name
    ctx.fillText(words, n.x, labelY)
  }
}

function updateSize() {
  if (!container.value) return
  const rect = container.value.getBoundingClientRect()
  const w = Math.max(400, rect.width - 24)
  canvasW.value = w
  canvasH.value = Math.max(250, Math.round(w * 0.52))
  if (canvas.value) {
    canvas.value.width = canvasW.value
    canvas.value.height = canvasH.value
  }
  if (nodes.length > 0) relayout()
  draw()
}

onMounted(async () => {
  await loadGraph()
  await nextTick()
  updateSize()
  resizeObserver = new ResizeObserver(() => updateSize())
  if (container.value) resizeObserver.observe(container.value)
})

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
})

watch(() => props.solutionId, async () => {
  await loadGraph()
  await nextTick()
  updateSize()
})
</script>

<style scoped>
.dep-graph {
  position: relative;
}
.dep-canvas {
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: 6px;
  display: block;
}
.dep-tooltip {
  position: absolute;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,.1);
  pointer-events: none;
  z-index: 10;
}
</style>
