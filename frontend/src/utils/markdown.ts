/** Shared HTML/markdown formatting utilities for AI chat components. */

export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/** Strip tool call XML blocks from AI response. */
export function stripToolCalls(text: string): string {
  return text.replace(/<｜｜DSML｜｜tool_calls>[\s\S]*?<\/｜｜DSML｜｜tool_calls>/g, '')
    .replace(/<.DSML.[\s\S]*?<.\/.DSML.[^>]*>/g, '')
}

/** Convert basic markdown to safe HTML (input already escaped). */
export function mdToHtml(text: string): string {
  let html = escapeHtml(stripToolCalls(text))
    .replace(/^#### (.+)$/gm, '<h5>$1</h5>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/\*(.+?)\*/g, '<i>$1</i>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '<br><br>')
  return html
}

/** Format AI tool response content into HTML for display. */
export function formatAiContent(text: string, role: string): string {
  if (!text) return ''
  if (role === 'tool') {
    try {
      const d = JSON.parse(text)
      if (d.products) {
        return d.products.map((p: any) =>
          `<b>${escapeHtml(p.name || '')}</b> <span class="font-mono">${escapeHtml(p.model || '')}</span> — ¥${p.price || 0}<br><span class="text-muted" style="font-size:11px">${[p.category, p.manufacturer].filter(Boolean).map(escapeHtml).join(' | ')}</span>`
        ).join('<br>')
      }
      if (d.found !== undefined) return `<b>找到 ${d.found} 个产品</b>`
      if (d.categories) return d.categories.map((c: any) => escapeHtml(c.name)).join('、')
      return `<pre style="font-size:11px;margin:0">${escapeHtml(JSON.stringify(d, null, 2))}</pre>`
    } catch { /* ignore */ }
  }
  return mdToHtml(text)
}

/** Extract product objects from tool response JSON. */
export function extractProducts(text: string, role: string): any[] {
  if (role !== 'tool') return []
  try {
    const d = JSON.parse(text)
    if (d.products) return d.products
  } catch { /* ignore */ }
  return []
}
