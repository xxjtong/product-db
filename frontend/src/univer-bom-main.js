/**
 * Univer BOM Editor — standalone full-screen spreadsheet for BOM editing
 */
import {
  Univer, LocaleType, UniverInstanceType,
  ICommandService, CommandType,
} from '@univerjs/core'
import { defaultTheme } from '@univerjs/themes'
import { UniverRenderEnginePlugin } from '@univerjs/engine-render'
import { UniverFormulaEnginePlugin } from '@univerjs/engine-formula'
import { UniverUIPlugin } from '@univerjs/ui'
import { UniverDocsPlugin } from '@univerjs/docs'
import { UniverDocsUIPlugin } from '@univerjs/docs-ui'
import { UniverSheetsPlugin } from '@univerjs/sheets'
import { UniverSheetsUIPlugin } from '@univerjs/sheets-ui'
import { UniverSheetsFormulaPlugin } from '@univerjs/sheets-formula'
import { FUniver } from '@univerjs/core/facade'

// Facade side-effect registrations
import '@univerjs/sheets/facade'
import '@univerjs/sheets-ui/facade'
import '@univerjs/ui/facade'
import '@univerjs/docs-ui/facade'
import '@univerjs/sheets-formula/facade'
import '@univerjs/engine-formula/facade'

// CSS
import '@univerjs/design/lib/index.css'
import '@univerjs/ui/lib/index.css'
import '@univerjs/docs-ui/lib/index.css'
import '@univerjs/sheets-ui/lib/index.css'

// Locales
import uiZhCN from '@univerjs/ui/lib/es/locale/zh-CN'
import sheetsZhCN from '@univerjs/sheets/lib/es/locale/zh-CN'
import sheetsUiZhCN from '@univerjs/sheets-ui/lib/es/locale/zh-CN'
import docsUiZhCN from '@univerjs/docs-ui/lib/es/locale/zh-CN'
import formulaZhCN from '@univerjs/sheets-formula/lib/es/locale/zh-CN'

function deepMerge(target, ...sources) {
  for (const src of sources) {
    for (const key of Object.keys(src)) {
      if (src[key] && typeof src[key] === 'object' && !Array.isArray(src[key]) &&
          target[key] && typeof target[key] === 'object' && !Array.isArray(target[key])) {
        deepMerge(target[key], src[key])
      } else {
        target[key] = src[key]
      }
    }
  }
  return target
}

const zhCN = deepMerge({}, uiZhCN, sheetsZhCN, sheetsUiZhCN, docsUiZhCN, formulaZhCN)

// --- Init ---
const params = new URLSearchParams(window.location.search)
const solutionId = params.get('solutionId')
const token = params.get('token')
if (!solutionId || !token) {
  document.body.innerHTML = '<div style="padding:20px;color:red">缺少 solutionId 或 token 参数</div>'
  throw new Error('Missing params')
}

const API_BASE = '/api'

async function fetchSnapshot() {
  const res = await fetch(`${API_BASE}/solutions/${solutionId}/bom-snapshot`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.bom_snapshot?.snapshot || { cells: {}, sheet_name: 'BOM' }
}

async function saveSnapshot(snapshot) {
  const res = await fetch(`${API_BASE}/solutions/${solutionId}/bom-snapshot`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({ snapshot })
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// Cell ref parsing
function cellRefToRowCol(ref) {
  const m = ref.match(/^([A-Z]+)(\d+)$/)
  if (!m) return { row: 0, col: 0 }
  let col = 0
  for (let i = 0; i < m[1].length; i++) col = col * 26 + (m[1].charCodeAt(i) - 64)
  return { row: parseInt(m[2], 10) - 1, col: col - 1 }
}

function rowColToCellRef(row, col) {
  let c = ''
  let n = col
  while (n >= 0) { c = String.fromCharCode(65 + (n % 26)) + c; n = Math.floor(n / 26) - 1 }
  return c + (row + 1)
}

function snapshotToSheetData(snapshot) {
  const cellData = {}
  const cells = snapshot?.cells || {}
  let maxRow = 0, maxCol = 0

  for (const [ref, cell] of Object.entries(cells)) {
    const { row, col } = cellRefToRowCol(ref)
    if (row > maxRow) maxRow = row
    if (col > maxCol) maxCol = col
    if (!cellData[row]) cellData[row] = {}
    const c = cell
    const obj = { v: c.v ?? '' }
    if (c.f) obj.f = c.f
    if (c.s) obj.s = c.s
    cellData[row][col] = obj
  }

  const colWidths = snapshot?.colWidths || {}
  const columnData = {}
  for (const [k, w] of Object.entries(colWidths)) {
    const col = cellRefToRowCol(k + '1').col
    if (col >= 0) columnData[col] = { w }
  }

  return {
    name: snapshot?.sheet_name || 'BOM',
    cellData,
    columnData,
    rowCount: Math.max(maxRow + 20, 200),
    columnCount: Math.max(maxCol + 5, 26),
    defaultColumnWidth: 93,
    defaultRowHeight: 27,
  }
}

function univerToSnapshot(univer, workbookId) {
  const api = FUniver.newAPI(univer)
  const sheet = api.getActiveWorkbook()?.getActiveSheet()
  if (!sheet) return {}

  const cells = {}
  const rowCount = sheet.getRowCount?.() || 200
  const colCount = sheet.getColumnCount?.() || 26

  for (let r = 0; r < Math.min(rowCount, 200); r++) {
    for (let c = 0; c < Math.min(colCount, 50); c++) {
      try {
        const ref = rowColToCellRef(r, c)
        const v = sheet.getRange(ref).getValue?.()
        if (v != null && v !== '') {
          cells[ref] = { v }
        }
      } catch { /* skip */ }
    }
  }

  return { cells, sheet_name: 'BOM' }
}

// --- Main ---
async function main() {
  let snapshot
  try {
    snapshot = await fetchSnapshot()
  } catch (e) {
    document.body.innerHTML = `<div style="padding:20px;color:red">加载 BOM 失败: ${e.message}</div>`
    return
  }

  const univer = new Univer({
    theme: defaultTheme,
    locale: LocaleType.ZH_CN,
    locales: { [LocaleType.ZH_CN]: zhCN },
  })

  univer.registerPlugin(UniverRenderEnginePlugin)
  univer.registerPlugin(UniverFormulaEnginePlugin)
  univer.registerPlugin(UniverDocsPlugin)
  univer.registerPlugin(UniverSheetsPlugin)
  univer.registerPlugin(UniverUIPlugin, {
    container: document.getElementById('univer-app')
  })
  univer.registerPlugin(UniverDocsUIPlugin)
  univer.registerPlugin(UniverSheetsUIPlugin)
  univer.registerPlugin(UniverSheetsFormulaPlugin)

  // Create empty sheet, populate via Facade
  univer.createUnit(UniverInstanceType.UNIVER_SHEET, {
    name: 'BOM',
    sheetOrder: ['sheet1'],
    sheets: { sheet1: { name: 'BOM', rowCount: 200, columnCount: 26 } },
  })

  // Populate cells via Facade
  const api = FUniver.newAPI(univer)
  const sheet = api.getActiveWorkbook()?.getActiveSheet()
  if (sheet) {
    const cells = snapshot?.cells || {}
    for (const [ref, cellData] of Object.entries(cells)) {
      const c = cellData
      try {
        if (c.v != null && c.v !== '') {
          sheet.getRange(ref).setValue(c.v)
        }
      } catch { /* skip */ }
    }
  }

  // Register download command
  const injector = univer.__getInjector()
  const commandService = injector.get(ICommandService)
  commandService.registerCommand({
    id: 'bom.command.download-xlsx',
    type: CommandType.COMMAND,
    handler: async () => {
      try {
        const snap = univerToSnapshot(univer, null)
        await saveSnapshot(snap)
        window.open(`${API_BASE}/solutions/${solutionId}/bom-snapshot/export-xlsx?token=${encodeURIComponent(token)}`, '_blank')
      } catch (e) {
        alert('导出失败: ' + e.message)
      }
      return true
    },
  })

  // Ctrl+S to save
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      const snap = univerToSnapshot(univer, null)
      saveSnapshot(snap).then(() => {
        const el = document.createElement('div')
        el.textContent = '已保存'
        el.style.cssText = 'position:fixed;top:10px;right:10px;background:#10b981;color:#fff;padding:8px 16px;border-radius:6px;z-index:9999;font-size:14px'
        document.body.appendChild(el)
        setTimeout(() => el.remove(), 2000)
      }).catch(e => alert('保存失败: ' + e.message))
    }
  })

  // Toolbar: add download button via menu service
  try {
    const { IMenuManagerService, MenuItemType, RibbonPosition, RibbonStartGroup } = await import('@univerjs/ui')
    const menuService = injector.get(IMenuManagerService)
    menuService.addMenuItem({
      id: 'bom.toolbar.download-xlsx',
      type: MenuItemType.BUTTON,
      title: { zhCN: '下载 xlsx' },
      icon: 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'),
      positions: [RibbonPosition.START],
      group: RibbonStartGroup.FILE,
      command: { id: 'bom.command.download-xlsx' },
    })
  } catch { /* toolbar button optional */ }
}

main()
