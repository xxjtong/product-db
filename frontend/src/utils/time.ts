/** Format ISO 8601 timestamp (or unix ms) to local timezone. */
export function formatTime(ts: string | number): string {
  const d = new Date(ts)
  const now = new Date()
  if (isNaN(d.getTime())) return String(ts)
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  const y = d.getFullYear()
  if (y === now.getFullYear()) {
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
}
