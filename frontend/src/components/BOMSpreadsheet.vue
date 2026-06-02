<template>
  <div class="bom-spreadsheet">
    <div class="flex gap-8 items-center mb-12">
      <button class="btn-secondary btn-sm" @click="loadSnapshot"><RefreshCwIcon style="width:14px;height:14px" />重新加载</button>
      <button class="btn-primary btn-sm" @click="save"><SaveIcon style="width:14px;height:14px" />保存</button>
      <button class="btn-secondary btn-sm" @click="exportXlsx"><DownloadIcon style="width:14px;height:14px" />导出 xlsx</button>
      <button class="btn-secondary btn-sm" @click="saveAsTemplate"><CopyIcon style="width:14px;height:14px" />另存为模板</button>
      <span v-if="dirty" class="text-sm" style="color:var(--color-danger)">未保存</span>
    </div>
    <div ref="container" class="univer-container"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, inject } from 'vue'
import { RefreshCwIcon, SaveIcon, DownloadIcon, CopyIcon } from 'lucide-vue-next'
import { fetchBomSnapshot, saveBomSnapshot, bomExportUrl, saveBomAsTemplate } from '../api'

const props = defineProps<{ solutionId: number }>()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const container = ref<HTMLElement | null>(null)
const dirty = ref(false)
// Use `any` for Univer instances to avoid tight type coupling across versions
let univer: any = null
let workbookId: string | null = null
let currentSnapshot: any = null

async function loadSnapshot() {
  try {
    const res = await fetchBomSnapshot(props.solutionId)
    currentSnapshot = res.bom_snapshot.snapshot
    renderSheet(currentSnapshot)
    dirty.value = false
  } catch (e: any) {
    showToast('加载BOM失败: ' + (e.detail || e.message), 'error')
  }
}

async function renderSheet(snapshot: any) {
  if (!container.value) return

  // Cleanup existing instance
  if (univer) {
    univer.dispose()
    univer = null
    workbookId = null
  }

  const { Univer, UniverInstanceType, LocaleType } = await import('@univerjs/core')
  const themesModule = await import('@univerjs/themes')
  const defaultTheme = (themesModule as any).default || (themesModule as any).defaultTheme
  const { UniverSheetsPlugin } = await import('@univerjs/sheets')
  const { UniverSheetsFormulaPlugin } = await import('@univerjs/sheets-formula')
  const { UniverUIPlugin } = await import('@univerjs/ui')
  const { UniverRenderEnginePlugin } = await import('@univerjs/engine-render')

  // Load locale data for all plugins
  const sheetsZh = (await import('@univerjs/sheets/locale/zh-CN')).default
  const sheetsUiZh = (await import('@univerjs/sheets-ui/locale/zh-CN')).default
  const uiZh = (await import('@univerjs/ui/locale/zh-CN')).default
  const designZh = (await import('@univerjs/design/locale/zh-CN')).default

  univer = new Univer({
    theme: defaultTheme,
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: {
        ...designZh,
        ...uiZh,
        ...sheetsZh,
        ...sheetsUiZh,
      },
    },
  })

  univer.registerPlugin(UniverRenderEnginePlugin)
  univer.registerPlugin(UniverUIPlugin, { container: container.value })
  univer.registerPlugin(UniverSheetsPlugin)
  univer.registerPlugin(UniverSheetsFormulaPlugin)

  const sheetData = snapshotToUniverData(snapshot)

  const unit = univer.createUnit(UniverInstanceType.UNIVER_SHEET, {
    name: 'BOM',
    sheetOrder: ['sheet1'],
    sheets: { sheet1: sheetData },
  })
  workbookId = unit.getUnitId()
}

function _univerStyleToInline(s: any): Record<string, any> | null {
  if (!s) return null
  const style: Record<string, any> = {}
  if (s.bg) style.bg = typeof s.bg === 'string' ? s.bg : (s.bg?.rgb || '')
  if (s.cl) style.cl = typeof s.cl === 'string' ? s.cl : (s.cl?.rgb || '')
  if (s.ff) style.ff = s.ff
  if (s.fs) style.fs = s.fs
  if (s.bl) style.bl = s.bl
  if (s.it) style.it = s.it
  if (s.ul) style.ul = s.ul
  if (s.ht) style.ht = s.ht
  if (s.vt) style.vt = s.vt
  if (s.tb) style.tb = s.tb
  if (s.bd) style.bd = s.bd
  return Object.keys(style).length > 0 ? style : null
}

function _inlineStyleToUniver(style: Record<string, any> | null): any {
  if (!style) return undefined
  const s: Record<string, any> = {}
  if (style.bg) s.bg = { rgb: style.bg }
  if (style.cl) s.cl = { rgb: style.cl }
  if (style.ff) s.ff = style.ff
  if (style.fs) s.fs = style.fs
  if (style.bl) s.bl = style.bl
  if (style.it) s.it = style.it
  if (style.ul) s.ul = style.ul
  if (style.ht) s.ht = style.ht
  if (style.vt) s.vt = style.vt
  if (style.tb) s.tb = style.tb
  if (style.bd) s.bd = style.bd
  return s
}

function snapshotToUniverData(snapshot: any): any {
  const cellData: Record<number, Record<number, any>> = {}

  const snapshotCells = snapshot?.cells || {}
  for (const [ref, cell] of Object.entries(snapshotCells)) {
    const c = cell as any
    const { row, col } = cellRefToRowCol(ref)
    if (!cellData[row]) cellData[row] = {}
    const cellObj: any = {
      v: c.v ?? '',
      m: c.v != null ? String(c.v) : '',
    }
    if (c.f) cellObj.f = c.f
    if (c.s) cellObj.s = _inlineStyleToUniver(c.s)
    cellData[row][col] = cellObj
  }

  // Build mergeData from snapshot merges (cell-ref strings → IRange[])
  const mergeRanges: any[] = []
  const merges = snapshot?.merges || []
  for (const ref of merges) {
    const parts = ref.split(':')
    const start = cellRefToRowCol(parts[0])
    const end = parts[1] ? cellRefToRowCol(parts[1]) : start
    mergeRanges.push({
      startRow: start.row, startColumn: start.col,
      endRow: end.row, endColumn: end.col,
    })
  }

  // Build rowData from snapshot rowHeights
  const rowData: Record<number, any> = {}
  const rowHeights = snapshot?.rowHeights || {}
  for (const [rowKey, height] of Object.entries(rowHeights)) {
    const row = parseInt(rowKey) - 1
    if (row >= 0) rowData[row] = { h: height as number }
  }

  // Build columnData from snapshot colWidths
  const columnData: Record<number, any> = {}
  const colWidths = snapshot?.colWidths || {}
  for (const [colKey, width] of Object.entries(colWidths)) {
    const col = letterToCol(colKey)
    if (col >= 0) columnData[col] = { w: width as number }
  }

  let maxRow = 0, maxCol = 0
  for (const ref of Object.keys(snapshotCells)) {
    const { row, col } = cellRefToRowCol(ref)
    if (row > maxRow) maxRow = row
    if (col > maxCol) maxCol = col
  }

  return {
    name: snapshot?.sheet_name || 'BOM',
    cellData,
    mergeData: mergeRanges,
    rowData,
    columnData,
    rowCount: Math.max(maxRow + 20, 200),
    columnCount: Math.max(maxCol + 5, 26),
    defaultColumnWidth: 93,
    defaultRowHeight: 27,
  }
}

function cellRefToRowCol(ref: string): { row: number; col: number } {
  const match = ref.match(/^([A-Z]+)(\d+)$/)
  if (!match) return { row: 0, col: 0 }
  const colStr = match[1]
  const row = parseInt(match[2], 10) - 1
  let col = 0
  for (let i = 0; i < colStr.length; i++) {
    col = col * 26 + (colStr.charCodeAt(i) - 64)
  }
  return { row, col: col - 1 }
}

function rowColToCellRef(row: number, col: number): string {
  return colToLetter(col) + (row + 1)
}

function colToLetter(col: number): string {
  let result = ''
  let n = col
  while (n >= 0) {
    result = String.fromCharCode(65 + (n % 26)) + result
    n = Math.floor(n / 26) - 1
  }
  return result
}

function letterToCol(letter: string): number {
  let col = 0
  for (let i = 0; i < letter.length; i++) {
    col = col * 26 + (letter.charCodeAt(i) - 64)
  }
  return col - 1
}

function getWorkbook(): any {
  if (!univer || !workbookId) return null
  return univer.getUnit(workbookId)
}

async function save() {
  try {
    const wb = getWorkbook()
    if (!wb) return
    const snapshot = univerToSnapshot(wb)
    await saveBomSnapshot(props.solutionId, { snapshot })
    currentSnapshot = snapshot
    dirty.value = false
    showToast('BOM 已保存', 'success')
  } catch (e: any) {
    showToast('保存失败: ' + (e.detail || e.message), 'error')
  }
}

function univerToSnapshot(wb: any): any {
  const sheet = wb.getSheetByIndex(0)
  if (!sheet) return currentSnapshot || {}

  const cells: Record<string, any> = {}
  const rowCount = sheet.getRowCount()
  const columnCount = sheet.getColumnCount()

  // Access style sheet for cell style lookup
  let styles: any = null
  try { styles = wb.getStyles() } catch { console.warn('BOMSpreadsheet: parse failed') }

  for (let r = 0; r < rowCount; r++) {
    for (let c = 0; c < columnCount; c++) {
      const cell = sheet.getCell(r, c)
      if (!cell || (cell.v === undefined && !cell.f)) continue
      const ref = rowColToCellRef(r, c)
      const cellData: any = { v: cell.v ?? '' }
      if (cell.f) cellData.f = cell.f

      // Extract style
      if (cell.s && styles) {
        try {
          const style = typeof cell.s === 'string' ? styles.get(cell.s) : cell.s
          const inline = _univerStyleToInline(style)
          if (inline) cellData.s = inline
        } catch { console.warn('BOMSpreadsheet: parse failed') }
      }

      cells[ref] = cellData
    }
  }

  // Extract column widths
  const colWidths: Record<string, number> = {}
  for (let c = 0; c < columnCount; c++) {
    try {
      const w = sheet.getColumnWidth(c)
      if (w !== undefined && w !== null) {
        colWidths[colToLetter(c)] = w
      }
    } catch { console.warn('BOMSpreadsheet: parse failed') }
  }

  // Extract row heights
  const rowHeights: Record<string, number> = {}
  for (let r = 0; r < rowCount; r++) {
    try {
      const h = sheet.getRowHeight(r)
      if (h !== undefined && h !== null) {
        rowHeights[String(r + 1)] = h
      }
    } catch { console.warn('BOMSpreadsheet: parse failed') }
  }

  // Extract merged cells
  let merges: string[] = []
  try {
    const mergedRanges = sheet.getMergeData?.() || []
    merges = mergedRanges.map((range: any) => {
      const startRef = rowColToCellRef(range.startRow, range.startColumn)
      const endRef = rowColToCellRef(range.endRow, range.endColumn)
      return startRef === endRef ? startRef : `${startRef}:${endRef}`
    })
  } catch { console.warn('BOMSpreadsheet: parse failed') }

  return {
    cells,
    colWidths,
    rowHeights,
    merges,
    sheet_name: sheet.getName?.(),
  }
}

function exportXlsx() {
  window.open(bomExportUrl(props.solutionId), '_blank')
}

async function saveAsTemplate() {
  const name = prompt('模板名称:')
  if (!name) return
  try {
    const wb = getWorkbook()
    const snapshot = wb ? univerToSnapshot(wb) : currentSnapshot || {}
    await saveBomAsTemplate(props.solutionId, { name, snapshot })
    showToast('模板已保存', 'success')
  } catch (e: any) {
    showToast('保存模板失败', 'error')
  }
}

onMounted(loadSnapshot)

onBeforeUnmount(() => {
  if (univer) {
    univer.dispose()
    univer = null
  }
})
</script>

<style scoped>
.bom-spreadsheet {
  margin-top: 16px;
}
.univer-container {
  width: 100%;
  height: 500px;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 6px);
  overflow: hidden;
}
</style>
