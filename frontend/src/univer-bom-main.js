/**
 * Univer BOM Editor — standalone full-screen spreadsheet for solution BOM editing
 * 完全独立于 Vue，Vite 多页面构建
 */
import {
  Univer, LocaleType, UserManagerService, UniverInstanceType,
  ICommandService, CommandType, Plugin,
} from '@univerjs/core'
import { defaultTheme } from '@univerjs/themes'
import { UniverRenderEnginePlugin } from '@univerjs/engine-render'
import { UniverFormulaEnginePlugin } from '@univerjs/engine-formula'
import { UniverUIPlugin, IMenuManagerService, MenuItemType, RibbonPosition, RibbonStartGroup, ComponentManager } from '@univerjs/ui'
import { DownloadIcon, ShapeFlowChartMagneticDiskIcon as SaveIcon } from '@univerjs/icons'
import { UniverDocsPlugin } from '@univerjs/docs'
import { UniverDocsUIPlugin } from '@univerjs/docs-ui'
import { UniverSheetsPlugin } from '@univerjs/sheets'
import { UniverSheetsUIPlugin } from '@univerjs/sheets-ui'
import { UniverSheetsFormulaPlugin } from '@univerjs/sheets-formula'
import { UniverSheetsFormulaUIPlugin } from '@univerjs/sheets-formula-ui'
import { UniverSheetsFilterPlugin } from '@univerjs/sheets-filter'
import { UniverSheetsFilterUIPlugin } from '@univerjs/sheets-filter-ui'
import { UniverSheetsSortPlugin } from '@univerjs/sheets-sort'
import { UniverSheetsNumfmtPlugin } from '@univerjs/sheets-numfmt'
import { UniverSheetsNumfmtUIPlugin } from '@univerjs/sheets-numfmt-ui'
import { FUniver } from '@univerjs/core/facade'
import ExcelJS from 'exceljs'
import JSZip from 'jszip'

// Facade 侧注册
import '@univerjs/sheets/facade'
import '@univerjs/sheets-ui/facade'
import '@univerjs/ui/facade'
import '@univerjs/docs-ui/facade'
import '@univerjs/sheets-filter/facade'
import '@univerjs/sheets-formula/facade'
import '@univerjs/sheets-numfmt/facade'
import '@univerjs/sheets-sort/facade'
import '@univerjs/engine-formula/facade'
import '@univerjs/sheets-formula-ui/facade'

// CSS
import '@univerjs/design/lib/index.css'
import '@univerjs/ui/lib/index.css'
import '@univerjs/docs-ui/lib/index.css'
import '@univerjs/sheets-ui/lib/index.css'
import '@univerjs/sheets-filter-ui/lib/index.css'

// 完整中文翻译
import uiZhCN from '@univerjs/ui/lib/es/locale/zh-CN'
import sheetsZhCN from '@univerjs/sheets/lib/es/locale/zh-CN'
import sheetsUiZhCN from '@univerjs/sheets-ui/lib/es/locale/zh-CN'
import docsUiZhCN from '@univerjs/docs-ui/lib/es/locale/zh-CN'
import formulaZhCN from '@univerjs/sheets-formula/lib/es/locale/zh-CN'
import formulaUiZhCN from '@univerjs/sheets-formula-ui/lib/es/locale/zh-CN'
import filterUiZhCN from '@univerjs/sheets-filter-ui/lib/es/locale/zh-CN'
import numfmtUiZhCN from '@univerjs/sheets-numfmt-ui/lib/es/locale/zh-CN'

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

const zhCN = deepMerge({}, uiZhCN, sheetsZhCN, sheetsUiZhCN, docsUiZhCN,
  formulaZhCN, formulaUiZhCN, filterUiZhCN, numfmtUiZhCN)

const BASE_URL = import.meta.env.BASE_URL.replace(/\/$/, '')
const API_BASE = BASE_URL + '/api'

const params = new URLSearchParams(window.location.search)
const solutionId = params.get('solutionId')
const token = params.get('token')
if (!solutionId || !token) {
  document.getElementById('univer-app').innerHTML = '<p style="color:red;padding:20px">缺少参数，请从方案详情页打开</p>'
  throw new Error('Missing params')
}

let univerInstance = null
let univerAPI = null
let bomTitle = ''

// ─── 保存到服务器 ───
const SAVE_COMMAND_ID = 'bom.command.save-to-server'

function rowColToCellRef(row, col) {
  let c = ''
  let n = col
  while (n >= 0) { c = String.fromCharCode(65 + (n % 26)) + c; n = Math.floor(n / 26) - 1 }
  return c + (row + 1)
}

async function doSaveToServer() {
  try {
    if (!univerAPI) return
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) return
    const snapshot = workbook.save()
    const fSheet = workbook.getActiveSheet()
    const sheetId = fSheet.getSheetId()
    const sheetSnap = snapshot.sheets[sheetId]
    if (!sheetSnap) return

    const cd = sheetSnap.cellData || {}
    const mg = sheetSnap.mergeData || []
    const colD = sheetSnap.columnData || {}
    const rowD = sheetSnap.rowData || {}
    const styles = snapshot.styles || {}
    const rowCount = sheetSnap.rowCount || 0
    const colCount = sheetSnap.columnCount || 0

    // Convert to server snapshot format: cells = {ref: {v, f?, s?}}
    const cells = {}
    for (let r = 0; r < rowCount; r++) {
      for (let c = 0; c < colCount; c++) {
        const cell = cd[r] && cd[r][c]
        if (!cell) continue
        const ref = rowColToCellRef(r, c)
        const scell = {}
        if (cell.v !== undefined && cell.v !== null && cell.v !== '') {
          scell.v = cell.v
        }
        if (cell.f) {
          scell.f = cell.f
          if (scell.v === undefined || scell.v === '') scell.v = ''
        }
        if (cell.s !== undefined && cell.s !== null) {
          scell.s = styles[cell.s] || cell.s
        }
        if (Object.keys(scell).length > 0) {
          cells[ref] = scell
        }
      }
    }

    // Column widths
    const colWidths = {}
    for (const [k, d] of Object.entries(colD)) {
      if (d && d.w) colWidths[rowColToCellRef(0, +k)] = d.w
    }

    // Row heights
    const rowHeights = {}
    for (const [k, d] of Object.entries(rowD)) {
      if (d && d.h) rowHeights[+k + 1] = d.h
    }

    // Merges as ref strings (e.g. "A3:C3")
    const merges = mg.map(m =>
      rowColToCellRef(m.startRow, m.startColumn) + ':' + rowColToCellRef(m.endRow, m.endColumn)
    )

    const serverSnapshot = {
      cells, colWidths, rowHeights, merges, sheet_name: bomTitle || 'BOM',
    }

    const resp = await fetch(`${API_BASE}/solutions/${solutionId}/bom-snapshot`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ snapshot: serverSnapshot }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }

    // Show success toast
    const el = document.createElement('div')
    el.textContent = '已保存到方案'
    el.style.cssText = 'position:fixed;top:10px;right:10px;background:#10b981;color:#fff;padding:8px 16px;border-radius:6px;z-index:9999;font-size:14px'
    document.body.appendChild(el)
    setTimeout(() => el.remove(), 2000)
    return true
  } catch (e) {
    alert('保存失败: ' + e.message)
    return false
  }
}

// ─── 下载 xlsx 逻辑 ───
const DOWNLOAD_COMMAND_ID = 'bom.command.download-xlsx'

async function doExportXlsx() {
  try {
    if (!univerAPI) return
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) return
    const snapshot = workbook.save()
    const fSheet = workbook.getActiveSheet()
    const sheetId = fSheet.getSheetId()
    const sheetSnap = snapshot.sheets[sheetId]
    if (!sheetSnap) return

    const cd = sheetSnap.cellData || {}
    const mg = sheetSnap.mergeData || []
    const colD = sheetSnap.columnData || {}
    const rowD = sheetSnap.rowData || {}
    const styles = snapshot.styles || {}
    const rowCount = sheetSnap.rowCount || 0
    const colCount = sheetSnap.columnCount || 0

    // 构建共享公式主单元格映射
    const siMaster = {}
    for (const r in cd) {
      for (const c in cd[r]) {
        const cell = cd[r][c]
        if (cell && cell.f && cell.si !== undefined && cell.si !== null) {
          siMaster[cell.si] = { row: +r, col: +c, f: cell.f }
        }
      }
    }

    function offsetFormula(formula, dr, dc) {
      if (dr === 0 && dc === 0) return formula
      return formula.replace(/\$?([A-Z]+)\$?(\d+)/g, (match, colStr, rowStr) => {
        const absCol = match.includes('$' + colStr)
        const absRow = match.lastIndexOf('$') > (absCol ? colStr.length : 0)
        const colIdx = colStr.split('').reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1
        const rowIdx = +rowStr - 1
        const newColIdx = colIdx + dc
        const newCol = absCol ? colStr : newColIdx >= 0 ? String.fromCharCode(65 + newColIdx) : colStr
        const newRow = absRow ? rowStr : String(rowIdx + dr + 1)
        return (absCol ? '$' : '') + (absCol ? colStr : newCol) + (absRow ? '$' : '') + newRow
      })
    }

    const hAlignMap = { 0: 'left', 1: 'left', 2: 'center', 3: 'right' }
    const vAlignMap = { 0: 'top', 1: 'top', 2: 'middle', 3: 'bottom' }

    const DEFAULT_FONTS = new Set(['Microsoft YaHei', '微软雅黑'])
    const DEFAULT_FONT_SIZE = 10

    function applyStyle(cell, styleId) {
      const s = styles[styleId]
      if (!s) return
      const hasBold = s.bl === 1
      const hasItalic = s.it === 1
      const hasUnderline = s.ul && s.ul.s === 1
      const hasStrike = s.st && s.st.s === 1
      const hasColor = s.cl && s.cl.rgb
      const fontName = s.ff
      const fontSize = s.fs
      const isDefaultFont = (!fontName || DEFAULT_FONTS.has(fontName)) && (!fontSize || fontSize === DEFAULT_FONT_SIZE) && !hasBold && !hasItalic && !hasUnderline && !hasStrike && !hasColor
      if (!isDefaultFont) {
        cell.font = {}
        if (fontName) cell.font.name = fontName
        if (fontSize) cell.font.size = fontSize
        if (hasBold) cell.font.bold = true
        if (hasItalic) cell.font.italic = true
        if (hasUnderline) cell.font.underline = 'single'
        if (hasStrike) cell.font.strike = true
        if (hasColor) cell.font.color = { argb: 'FF' + s.cl.rgb.replace('#', '') }
      }
      if (s.ht !== undefined || s.vt !== undefined || s.tb !== undefined) {
        cell.alignment = {}
        if (s.ht !== undefined) cell.alignment.horizontal = hAlignMap[s.ht] || 'left'
        if (s.vt !== undefined) cell.alignment.vertical = vAlignMap[s.vt] || 'top'
        if (s.tb === 3 || s.tb === 2) cell.alignment.wrapText = true
        if (s.tr !== undefined && s.tr !== 0) cell.alignment.textRotation = s.tr
      }
      if (s.bg && s.bg.rgb) {
        cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF' + s.bg.rgb.replace('#', '') } }
      }
      const bd = s.bd
      if (bd) {
        cell.border = {}
        const dirMap = { t: 'top', b: 'bottom', l: 'left', r: 'right' }
        const styleMap = { 1: 'thin', 2: 'medium', 3: 'thick', 4: 'dotted', 5: 'hair', 6: 'dashed' }
        for (const [dk, dv] of Object.entries(dirMap)) {
          const b = bd[dk]
          if (b && b.s) {
            cell.border[dv] = {
              style: styleMap[b.s] || 'thin',
              color: b.cl && b.cl.rgb ? { argb: 'FF' + b.cl.rgb.replace('#', '') } : { argb: 'FFCCCCCC' },
            }
          }
        }
      }
    }

    // 用 ExcelJS 创建工作簿
    const wb = new ExcelJS.Workbook()
    const ws = wb.addWorksheet(bomTitle || 'BOM')

    // 列宽
    for (let c = 0; c < colCount; c++) {
      const d = colD[c]
      const wch = d ? Math.round((d.w || 80) / 7.5) : 12
      ws.getColumn(c + 1).width = wch
    }

    // 行高 + 单元格数据
    const imageCells = []
    for (let r = 0; r < rowCount; r++) {
      const row = ws.getRow(r + 1)
      // 数据行（第4行起）不设固定行高
      if (r < 3) {
        const d = rowD[r]
        row.height = d ? (d.h || 27) * 0.75 : 20
      }

      for (let c = 0; c < colCount; c++) {
        const cell = cd[r] && cd[r][c]
        if (!cell) continue
        const xcell = row.getCell(c + 1)

        if (cell.v !== undefined && cell.v !== null && cell.v !== '') {
          xcell.value = cell.v
        }

        if (cell.f) {
          const imgMatch = cell.f.match(/^=IMAGE\("(data:image\/(\w+);base64,[^"]+)",\s*"[^"]*",\s*\d+(?:,\s*(\d+)(?:,\s*(\d+))?)?\)$/)
          if (imgMatch) {
            imageCells.push({ row: r, col: c, dataUrl: imgMatch[1], ext: imgMatch[2], h: parseInt(imgMatch[3]) || 48, w: parseInt(imgMatch[4]) || 80 })
          } else {
            xcell.value = { formula: cell.f.replace(/^=/, ''), result: cell.v }
          }
        } else if (cell.si !== undefined && cell.si !== null && siMaster[cell.si]) {
          const master = siMaster[cell.si]
          const dr = r - master.row
          const dc = c - master.col
          const f = offsetFormula(master.f, dr, dc)
          xcell.value = { formula: f.replace(/^=/, ''), result: cell.v }
        }

        if (cell.s !== undefined && cell.s !== null) {
          applyStyle(xcell, cell.s)
        }
      }
    }

    // 嵌入图片
    for (const img of imageCells) {
      try {
        const base64 = img.dataUrl.split(',')[1]
        const imageId = wb.addImage({ base64, extension: img.ext })
        const colWidthPx = (colD[img.col] && colD[img.col].w) || 93
        const rowHeightPx = (rowD[img.row] && rowD[img.row].h) || 27
        let w = img.w, h = img.h
        if (h > rowHeightPx) {
          const ratio = rowHeightPx / h
          h = rowHeightPx
          w = Math.round(w * ratio)
        }
        if (w > colWidthPx) {
          const ratio = colWidthPx / w
          w = colWidthPx
          h = Math.round(h * ratio)
        }
        const xOffEmu = Math.round(Math.max(0, (colWidthPx - w) / 2) * 9525)
        const yOffEmu = Math.round(Math.max(0, (rowHeightPx - h) / 2) * 9525)
        ws.addImage(imageId, {
          tl: { nativeCol: img.col, nativeColOff: xOffEmu, nativeRow: img.row, nativeRowOff: yOffEmu },
          ext: { width: w, height: h },
        })
        const minRowH = Math.ceil(h * 72 / 96)
        const imgRow = ws.getRow(img.row + 1)
        if (!imgRow.height || imgRow.height < minRowH) imgRow.height = minRowH
      } catch (e) { /* skip broken images */ }
    }

    // 合并单元格
    for (const m of mg) {
      ws.mergeCells(m.startRow + 1, m.startColumn + 1, m.endRow + 1, m.endColumn + 1)
    }

    // 生成下载
    const buffer = await wb.xlsx.writeBuffer()
    window.__univerLastBuffer = buffer
    const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (bomTitle || 'BOM') + '.xlsx'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    return true
  } catch (e) {
    console.error('[Export] failed:', e)
  }
}

// 暴露给 E2E 测试
window.__univerDownload = () => doExportXlsx()

// ─── Ctrl+S / Cmd+S → 保存到服务器 ───
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    e.stopPropagation()
    doSaveToServer()
  }
}, true)

// ─── 自定义插件：工具栏保存 + 下载按钮 ───
const SaveXlsxCommand = {
  id: SAVE_COMMAND_ID,
  type: CommandType.COMMAND,
  handler: () => doSaveToServer(),
}

function SaveXlsxMenuItemFactory() {
  return {
    id: SAVE_COMMAND_ID,
    type: MenuItemType.BUTTON,
    icon: 'SaveIcon',
    title: '保存',
    tooltip: '保存到方案 (Ctrl+S)',
  }
}

const DownloadXlsxCommand = {
  id: DOWNLOAD_COMMAND_ID,
  type: CommandType.COMMAND,
  handler: () => doExportXlsx(),
}

function DownloadXlsxMenuItemFactory() {
  return {
    id: DOWNLOAD_COMMAND_ID,
    type: MenuItemType.BUTTON,
    icon: 'DownloadIcon',
    title: '下载 xlsx',
    tooltip: '导出 Excel 文件',
  }
}

const downloadMenuSchema = {
  [RibbonPosition.START]: {
    [RibbonStartGroup.HISTORY]: {
      [SAVE_COMMAND_ID]: {
        order: -2,
        menuItemFactory: SaveXlsxMenuItemFactory,
      },
      [DOWNLOAD_COMMAND_ID]: {
        order: -1,
        menuItemFactory: DownloadXlsxMenuItemFactory,
      },
    },
  },
}

class CustomDownloadPlugin extends Plugin {
  static pluginName = 'CUSTOM_DOWNLOAD_PLUGIN'
}

// ─── 从 xlsx 提取图片 ───
async function extractImages(arrayBuf) {
  const zip = await JSZip.loadAsync(arrayBuf)
  const result = []
  const drawingRe = /^\/?xl\/drawings\/(drawing\d+)\.xml$/
  const drawingRelsRe = /^\/?xl\/drawings\/_rels\/(drawing\d+)\.xml\.rels$/

  const drawingRelMap = {}
  for (const [name, entry] of Object.entries(zip.files)) {
    const m = name.match(drawingRelsRe)
    if (!m) continue
    const xml = await entry.async('string')
    const relMap = {}
    const relRe = /<Relationship[^>]*\/>/g
    let rm
    while ((rm = relRe.exec(xml)) !== null) {
      const relXml = rm[0]
      const idMatch = relXml.match(/\bId="(rId\d+)"/)
      const targetMatch = relXml.match(/\bTarget="(?:\/xl\/)?media\/([^"]+)"/)
      if (idMatch && targetMatch) relMap[idMatch[1]] = targetMatch[1]
    }
    drawingRelMap[m[1]] = relMap
  }

  for (const [name, entry] of Object.entries(zip.files)) {
    const m = name.match(drawingRe)
    if (!m) continue
    const drawingName = m[1]
    const xml = await entry.async('string')
    const relMap = drawingRelMap[drawingName] || {}

    const anchorRe = /<(?:xdr:)?(twoCellAnchor|oneCellAnchor)[^>]*>[\s\S]*?<\/(?:xdr:)?\1>/g
    let am
    while ((am = anchorRe.exec(xml)) !== null) {
      const anchorXml = am[0]
      const fromMatch = anchorXml.match(/<(?:xdr:)?from>[\s\S]*?<\/(?:xdr:)?from>/)
      if (!fromMatch) continue
      const colMatch = fromMatch[0].match(/<(?:xdr:)?col>(\d+)<\/(?:xdr:)?col>/)
      const rowMatch = fromMatch[0].match(/<(?:xdr:)?row>(\d+)<\/(?:xdr:)?row>/)
      if (!colMatch || !rowMatch) continue
      const col = parseInt(colMatch[1])
      const row = parseInt(rowMatch[1])
      const embedRe = /r:embed="(rId\d+)"/g
      let em
      while ((em = embedRe.exec(anchorXml)) !== null) {
        const rId = em[1]
        const mediaFile = relMap[rId]
        if (mediaFile) {
          result.push({ row, col, mediaFile })
        }
      }
    }
  }

  for (const img of result) {
    const mediaPath = 'xl/media/' + img.mediaFile
    if (!zip.files[mediaPath]) continue
    const ext = img.mediaFile.split('.').pop().toLowerCase()
    const mime = ext === 'png' ? 'image/png' : ext === 'gif' ? 'image/gif' : ext === 'webp' ? 'image/webp' : 'image/jpeg'
    const raw = await zip.files[mediaPath].async('uint8array')
    let binary = ''
    const chunkSize = 8192
    for (let i = 0; i < raw.length; i += chunkSize) {
      binary += String.fromCharCode(...raw.subarray(i, Math.min(i + chunkSize, raw.length)))
    }
    img.dataUrl = 'data:' + mime + ';base64,' + btoa(binary)

    if (ext === 'png' && raw.length > 24) {
      const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength)
      img.imgWidth = view.getUint32(16)
      img.imgHeight = view.getUint32(20)
    } else if (ext === 'jpeg' || ext === 'jpg') {
      for (let i = 0; i < raw.length - 9; i++) {
        if (raw[i] === 0xFF && (raw[i + 1] === 0xC0 || raw[i + 1] === 0xC2)) {
          img.imgHeight = (raw[i + 5] << 8) | raw[i + 6]
          img.imgWidth = (raw[i + 7] << 8) | raw[i + 8]
          break
        }
      }
    }
  }

  return result.filter(img => img.dataUrl)
}

// ─── 清理 xlsx drawing 节点 ───
async function stripDrawings(arrayBuf) {
  const zip = await JSZip.loadAsync(arrayBuf)
  const drawingRe = /^\/?xl\/drawings\/.*\.xml$/
  const drawingRelsRe = /^\/?xl\/drawings\/_rels\/.*\.rels$/
  const mediaRe = /^\/?xl\/media\//
  const sheetRe = /^xl\/worksheets\/sheet(\d+)\.xml$/
  const sheetRelsRe = /^xl\/worksheets\/_rels\/sheet(\d+)\.xml\.rels$/

  for (const [name, entry] of Object.entries(zip.files)) {
    if (sheetRelsRe.test(name)) {
      let xml = await entry.async('string')
      xml = xml.replace(/<Relationship[^>]*Type="http:\/\/schemas\.openxmlformats\.org\/officeDocument\/2006\/relationships\/drawing"[^>]*\/>/g, '')
      zip.file(name, xml)
    }
    if (sheetRe.test(name)) {
      let xml = await entry.async('string')
      xml = xml.replace(/<drawing[^>]*\/>/g, '')
      zip.file(name, xml)
    }
  }

  const ctName = '[Content_Types].xml'
  if (zip.files[ctName]) {
    let xml = await zip.files[ctName].async('string')
    xml = xml.replace(/<Override[^>]*PartName="\/xl\/drawings\/[^"]*"[^>]*\/>/g, '')
    xml = xml.replace(/<Default[^>]*Extension="(png|jpeg|jpg|gif|bmp)"[^>]*\/>/g, '')
    zip.file(ctName, xml)
  }

  for (const name of Object.keys(zip.files)) {
    if (drawingRe.test(name) || drawingRelsRe.test(name) || mediaRe.test(name)) {
      zip.remove(name)
    }
  }

  return zip.generateAsync({ type: 'arraybuffer' })
}

// ─── 初始化 ───
async function init() {
  try {
    const downloadUrl = `${API_BASE}/solutions/${solutionId}/bom-snapshot/export-xlsx`
    const resp = await fetch(downloadUrl, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!resp.ok) {
      document.getElementById('univer-app').innerHTML = `<p style="color:red;padding:20px">下载 BOM 失败 (${resp.status})</p>`
      return
    }

    const cd = resp.headers.get('Content-Disposition') || ''
    let fname = 'bom_solution_' + solutionId + '.xlsx'
    const mStar = cd.match(/filename\*=UTF-8''(.+?)(?:;|$)/)
    if (mStar && mStar[1]) fname = decodeURIComponent(mStar[1])
    else {
      const m = cd.match(/filename="?([^";\n]+)"?/)
      if (m && m[1]) fname = m[1]
    }
    bomTitle = fname.replace(/\.xlsx$/i, '')

    let arrayBuf = await resp.arrayBuffer()
    const images = await extractImages(arrayBuf.slice(0))
    arrayBuf = await stripDrawings(arrayBuf)
    const wb = new ExcelJS.Workbook()
    await wb.xlsx.load(arrayBuf)
    const ws = wb.getWorksheet(1)
    if (!ws) {
      document.getElementById('univer-app').innerHTML = '<p style="color:red;padding:20px">工作簿中没有工作表</p>'
      return
    }
    const snapshot = xlsxToSnapshot(ws, bomTitle, images)

    initUniver(snapshot)
    document.title = bomTitle
    window.__univerReady = true
  } catch (e) {
    document.getElementById('univer-app').innerHTML = `<p style="color:red;padding:20px">加载失败：${e.message}</p>`
  }
}

// ─── xlsx → Univer 快照 ───
function xlsxToSnapshot(ws, name, images = []) {
  const styles = {}, cellData = {}, rowData = {}, columnData = {}, mergeData = []
  const hAlignMap = { left: 1, center: 2, right: 3, fill: 3, justify: 3, centerContinuous: 3, distributed: 2 }
  const vAlignMap = { top: 1, middle: 2, bottom: 3, justify: 3, distributed: 2 }
  const borderStyleMap = { thin: 1, medium: 2, thick: 3, dotted: 4, hair: 5, dashed: 6, dashedDot: 4, dashDotDot: 4, slantDashDot: 4, double: 2, mediumDashed: 6, mediumDashDotDot: 4 }
  const styleKeyMap = new Map()
  let nextStyleId = 0

  function colorToHex(color) {
    if (!color) return null
    if (color.argb) return '#' + color.argb.slice(-6)
    if (color.rgb) return '#' + color.rgb.slice(-6)
    return null
  }

  function getStyleId(opts) {
    const key = JSON.stringify(opts, Object.keys(opts).sort())
    if (styleKeyMap.has(key)) return styleKeyMap.get(key)
    const id = String(nextStyleId++)
    const s = {
      vt: opts.vt !== undefined ? opts.vt : 2,
      ht: opts.ht !== undefined ? opts.ht : 1,
      tb: opts.wrap ? 3 : 0,
    }
    if (opts.fontColor) s.cl = { rgb: opts.fontColor }
    if (opts.bg) s.bg = { rgb: opts.bg }
    s.bd = {
      t: { s: 1, cl: { rgb: '#CCCCCC' } },
      b: { s: 1, cl: { rgb: '#CCCCCC' } },
      l: { s: 1, cl: { rgb: '#CCCCCC' } },
      r: { s: 1, cl: { rgb: '#CCCCCC' } },
    }
    if (opts.borderTop) s.bd.t = opts.borderTop
    if (opts.borderBottom) s.bd.b = opts.borderBottom
    if (opts.borderLeft) s.bd.l = opts.borderLeft
    if (opts.borderRight) s.bd.r = opts.borderRight

    styles[id] = s
    styleKeyMap.set(key, id)
    return id
  }

  function readCellStyle(cell) {
    const style = cell.style
    const opts = {}
    if (style.font) {
      const fc = colorToHex(style.font.color)
      if (fc) opts.fontColor = fc
    }
    if (style.alignment) {
      const a = style.alignment
      if (a.horizontal) opts.ht = hAlignMap[a.horizontal] || 1
      if (a.vertical) opts.vt = vAlignMap[a.vertical] || 2
      if (a.textRotation !== undefined) opts.textRotation = a.textRotation
    }
    if (style.fill && style.fill.type === 'pattern' && style.fill.fgColor) {
      const hex = colorToHex(style.fill.fgColor)
      if (hex) opts.bg = hex
    }
    if (style.border) {
      const b = style.border
      if (b.top && b.top.style) opts.borderTop = { s: borderStyleMap[b.top.style] || 1, cl: { rgb: colorToHex(b.top.color) || '#CCCCCC' } }
      if (b.bottom && b.bottom.style) opts.borderBottom = { s: borderStyleMap[b.bottom.style] || 1, cl: { rgb: colorToHex(b.bottom.color) || '#CCCCCC' } }
      if (b.left && b.left.style) opts.borderLeft = { s: borderStyleMap[b.left.style] || 1, cl: { rgb: colorToHex(b.left.color) || '#CCCCCC' } }
      if (b.right && b.right.style) opts.borderRight = { s: borderStyleMap[b.right.style] || 1, cl: { rgb: colorToHex(b.right.color) || '#CCCCCC' } }
    }
    if (!opts.ht && cell.value !== undefined && cell.value !== null && typeof cell.value === 'number') opts.ht = 2
    return opts
  }

  const rowCount = ws.rowCount || 0
  const colCount = ws.columnCount || 0

  for (let c = 1; c <= colCount; c++) {
    const col = ws.getColumn(c)
    const w = col && col.width ? col.width : 0
    columnData[c - 1] = { w: w ? Math.round(w * 7.5) : 93, hd: 0 }
  }

  for (let r = 1; r <= rowCount; r++) {
    const row = ws.getRow(r)
    const h = row && row.height ? row.height : 0
    rowData[r - 1] = { h: h ? Math.round(h / 0.75) : 27, hd: 0 }
    cellData[r - 1] = {}

    for (let c = 1; c <= colCount; c++) {
      const cell = row.getCell(c)
      const v = cell.value
      if (v === undefined || v === null || v === '') continue

      let cellValue
      let formulaStr = null
      if (v && typeof v === 'object') {
        if (v.formula !== undefined) {
          cellValue = v.result !== undefined ? v.result : ''
          formulaStr = '=' + v.formula
        } else if (v.richText) {
          cellValue = v.richText.map(rt => rt.text).join('')
        } else if (v.error) {
          cellValue = v.error
        } else {
          cellValue = v
        }
      } else {
        cellValue = v
      }

      const ucell = { v: cellValue }
      if (formulaStr) ucell.f = formulaStr
      const opts = readCellStyle(cell)
      ucell.s = getStyleId(opts)
      cellData[r - 1][c - 1] = ucell
    }
  }

  // 合并单元格
  const merges = (ws.model && ws.model.merges) ? ws.model.merges : []
  function colLettersToIndex(letters) {
    return letters.split('').reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1
  }
  const mergeSet = new Set()
  for (const m of merges) {
    const parts = m.split(':')
    if (parts.length !== 2) continue
    const mStart = parts[0].match(/^([A-Z]+)(\d+)$/)
    const mEnd = parts[1].match(/^([A-Z]+)(\d+)$/)
    if (!mStart || !mEnd) continue
    const startCol = colLettersToIndex(mStart[1])
    const startRow = parseInt(mStart[2]) - 1
    const endCol = colLettersToIndex(mEnd[1])
    const endRow = parseInt(mEnd[2]) - 1
    mergeData.push({ startRow, endRow, startColumn: startCol, endColumn: endCol })
    for (let rr = startRow; rr <= endRow; rr++) {
      for (let cc = startCol; cc <= endCol; cc++) {
        if (rr === startRow && cc === startCol) continue
        mergeSet.add(rr + ',' + cc)
      }
    }
  }
  for (const key of mergeSet) {
    const [rr, cc] = key.split(',').map(Number)
    if (cellData[rr]) delete cellData[rr][cc]
  }

  // 插入图片
  for (const img of images) {
    if (!img.dataUrl) continue
    const r = img.row
    const c = img.col
    if (!cellData[r]) cellData[r] = {}
    const existing = cellData[r][c]
    const maxW = ((columnData[c] && columnData[c].w) || 93) - 4
    const maxH = ((rowData[r] && rowData[r].h) || 27) - 4
    let w = 80, h = 48
    if (img.imgWidth && img.imgHeight) {
      w = img.imgWidth
      h = img.imgHeight
    }
    if (h > maxH) {
      const ratio = maxH / h
      h = maxH
      w = Math.round(w * ratio)
    }
    if (w > maxW) {
      const ratio = maxW / w
      w = maxW
      h = Math.round(h * ratio)
    }
    cellData[r][c] = { v: existing ? existing.v : '', f: '=IMAGE("' + img.dataUrl + '", "", 3, ' + h + ', ' + w + ')', s: { ht: 2, vt: 2 } }
  }

  return {
    id: 'bom-workbook',
    name: name || 'BOM',
    appVersion: '0.24.0',
    locale: LocaleType.ZH_CN,
    styles,
    sheetOrder: ['s1'],
    sheets: {
      s1: {
        id: 's1',
        name: name || 'BOM',
        tabColor: '',
        hidden: 0,
        freeze: { x: 0, y: 0, startRow: -1, startCol: -1 },
        rowCount,
        columnCount: colCount,
        zoomRatio: 1,
        scrollTop: 0,
        scrollLeft: 0,
        defaultColumnWidth: 93,
        defaultRowHeight: 27,
        mergeData,
        cellData,
        rowData,
        columnData,
        showGridlines: 1,
        rightToLeft: 0,
        rowHeader: { width: 46, hidden: 0 },
        columnHeader: { height: 20, hidden: 0 },
      },
    },
  }
}

// ─── Univer 引擎初始化 ───
function initUniver(snapshot) {
  univerInstance = new Univer({
    theme: defaultTheme,
    locale: LocaleType.ZH_CN,
    locales: { [LocaleType.ZH_CN]: zhCN },
  })

  univerInstance.registerPlugin(UniverDocsPlugin)
  univerInstance.registerPlugin(UniverRenderEnginePlugin)
  univerInstance.registerPlugin(UniverUIPlugin, { container: 'univer-app' })
  univerInstance.registerPlugin(UniverDocsUIPlugin)
  univerInstance.registerPlugin(UniverSheetsPlugin)
  univerInstance.registerPlugin(UniverSheetsUIPlugin)
  univerInstance.registerPlugin(UniverFormulaEnginePlugin)
  univerInstance.registerPlugin(UniverSheetsFormulaPlugin)
  univerInstance.registerPlugin(UniverSheetsFormulaUIPlugin)
  univerInstance.registerPlugin(UniverSheetsNumfmtPlugin)
  univerInstance.registerPlugin(UniverSheetsNumfmtUIPlugin)
  univerInstance.registerPlugin(UniverSheetsFilterPlugin)
  univerInstance.registerPlugin(UniverSheetsFilterUIPlugin)
  univerInstance.registerPlugin(UniverSheetsSortPlugin)
  univerInstance.registerPlugin(CustomDownloadPlugin)

  const injector = univerInstance.__getInjector()
  const userManagerService = injector.get(UserManagerService)
  userManagerService.setCurrentUser({
    userID: 'Owner_qxVnhPbQ',
    name: 'Owner',
    avatar: '',
    anonymous: false,
    canBindAnonymous: false,
  })

  univerAPI = FUniver.newAPI(univerInstance)
  univerInstance.createUnit(UniverInstanceType.UNIVER_SHEET, snapshot)

  // 注册自定义保存+下载命令、图标、工具栏按钮
  const commandService = injector.get(ICommandService)
  commandService.registerCommand(SaveXlsxCommand)
  commandService.registerCommand(DownloadXlsxCommand)
  injector.get(ComponentManager).register('SaveIcon', SaveIcon)
  injector.get(ComponentManager).register('DownloadIcon', DownloadIcon)
  injector.get(IMenuManagerService).mergeMenu(downloadMenuSchema)

  // 修复下拉填充后行高丢失
  let autoHeightFixRunning = false
  commandService.onCommandExecuted((info) => {
    if (info.id !== 'sheet.command.auto-fill' && info.id !== 'sheet.command.refill' && info.id !== 'sheet.command.copy-down' && info.id !== 'sheet.command.copy-right') return
    if (autoHeightFixRunning) return
    autoHeightFixRunning = true
    setTimeout(() => {
      try {
        const workbook = univerAPI.getActiveWorkbook()
        if (!workbook) return
        const fSheet = workbook.getActiveSheet()
        const sheet = fSheet.getSheet()
        commandService.executeCommand('sheet.command.set-row-is-auto-height', {
          unitId: workbook.getId(),
          subUnitId: fSheet.getSheetId(),
          ranges: [{ startRow: 0, endRow: sheet.getRowCount() - 1, startColumn: 0, endColumn: sheet.getColumnCount() - 1, rangeType: 1 }],
        })
      } catch (e) { /* ignore */ }
      autoHeightFixRunning = false
    }, 100)
  })
}

init()
