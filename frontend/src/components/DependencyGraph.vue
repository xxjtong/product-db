<template>
  <div class="dep-graph">
    <div class="flex gap-8 items-center mb-8">
      <h3 style="margin:0">依赖关系图</h3>
    </div>
    <canvas ref="canvas" :width="canvasW" :height="canvasH" class="dep-canvas"></canvas>
    <div v-if="hovered" class="dep-tooltip" :style="{ left: tipX + 'px', top: tipY + 'px' }">
      <strong>{{ hovered.name }}</strong>
      <div class="text-sm text-muted">{{ hovered.category }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { fetchSolution } from '../api'

const props = defineProps<{ solutionId: number }>()

const canvas = ref<HTMLCanvasElement | null>(null)
const canvasW = 800
const canvasH = 400
const hovered = ref<any>(null)
const tipX = ref(0)
const tipY = ref(0)

interface GraphNode {
  id: number
  name: string
  category: string
  x: number
  y: number
  isRoot?: boolean
}

interface GraphEdge {
  from: number
  to: number
  type: string
  label: string
}

let nodes: GraphNode[] = []
let edges: GraphEdge[] = []
let nodeMap: Record<number, GraphNode> = {}
let animFrame = 0

async function loadGraph() {
  const res = await fetchSolution(props.solutionId)
  const solution = res.solution

  // Fetch dependencies for each product in the solution
  const productIds = (solution.items || []).map((i: any) => i.product_id)
  const allDeps: any[] = []

  for (const pid of productIds) {
    try {
      const r = await fetch(`/api/products/${pid}/dependencies`)
      const data = await r.json()
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
    const catRes = await fetch('/api/categories')
    const catData = await catRes.json()
    for (const c of catData.categories || []) {
      catMap[c.id] = c.name
    }
  } catch { /* skip */ }

  // Add dependency target products/categories as nodes
  for (const d of allDeps) {
    if (d.depends_on_product_id && !prodMap[d.depends_on_product_id]) {
      try {
        const pr = await fetch(`/api/products/${d.depends_on_product_id}`)
        const pd = await pr.json()
        prodMap[d.depends_on_product_id] = pd.product?.name || `#${d.depends_on_product_id}`
        if (!productIds.includes(d.depends_on_product_id)) {
          productIds.push(d.depends_on_product_id)
        }
      } catch { /* skip */ }
    }
  }

  // Layout: simple layered layout
  // Products in solution at center, dependencies fan out
  const centerX = canvasW / 2
  const centerY = canvasH / 2
  const solutionNodes: GraphNode[] = []
  const depNodes: GraphNode[] = []

  for (const pid of productIds) {
    const isInSolution = (solution.items || []).some((i: any) => i.product_id === pid)
    const node: GraphNode = {
      id: pid,
      name: prodMap[pid] || `#${pid}`,
      category: '',
      x: 0, y: 0,
      isRoot: isInSolution,
    }
    if (isInSolution) {
      solutionNodes.push(node)
    } else {
      depNodes.push(node)
    }
    nodeMap[pid] = node
  }

  // Position solution nodes in a circle at center
  const radius = 120
  solutionNodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / solutionNodes.length - Math.PI / 2
    n.x = centerX + radius * Math.cos(angle)
    n.y = centerY + radius * Math.sin(angle)
  })

  // Position dep nodes in an outer ring
  const outerRadius = 180
  depNodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(depNodes.length, 1) - Math.PI / 2
    n.x = centerX + outerRadius * Math.cos(angle)
    n.y = centerY + outerRadius * Math.sin(angle)
  })

  nodes = [...solutionNodes, ...depNodes]

  // Build edges
  edges = allDeps.map(d => ({
    from: d.product_id,
    to: d.depends_on_product_id || d.depends_on_category_id,
    type: d.dependency_type,
    label: d.description || '',
  }))

  draw()
}

function draw() {
  const ctx = canvas.value?.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvasW, canvasH)

  // Draw edges
  for (const e of edges) {
    const from = nodeMap[e.from]
    const to = nodeMap[e.to]
    if (!from && e.from) {
      // Category dependency — draw to a label instead
      continue
    }
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
      const ax = to.x - ux * 22
      const ay = to.y - uy * 22
      ctx.beginPath()
      ctx.moveTo(to.x - ux * 22, to.y - uy * 22)
      ctx.lineTo(ax - uy * 6, ay + ux * 6)
      ctx.lineTo(ax + uy * 6, ay - ux * 6)
      ctx.closePath()
      ctx.fillStyle = e.type === 'required' ? '#e94560' : e.type === 'recommended' ? '#0f3460' : '#94a3b8'
      ctx.fill()
    }
  }

  // Draw nodes
  for (const n of nodes) {
    const r = n.isRoot ? 18 : 14
    ctx.beginPath()
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = n.isRoot ? '#0f3460' : '#f1f5f9'
    ctx.fill()
    ctx.strokeStyle = n.isRoot ? '#1a1a2e' : '#94a3b8'
    ctx.lineWidth = 2
    ctx.stroke()

    // Label
    ctx.font = '11px Inter, sans-serif'
    ctx.fillStyle = n.isRoot ? '#fff' : '#1e293b'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const label = n.name.length > 8 ? n.name.slice(0, 7) + '…' : n.name
    ctx.fillText(label, n.x, n.y)
  }
}

onMounted(loadGraph)
watch(() => props.solutionId, loadGraph)
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
