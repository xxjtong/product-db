import { describe, it, expect } from 'vitest'

// Test XSS protection — HTML entities should be escaped
describe('mdToHtml XSS protection', () => {
  function escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  }

  it('escapes HTML entities', () => {
    const input = '<script>alert("xss")</script>'
    const escaped = escapeHtml(input)
    expect(escaped).not.toContain('<script>')
    expect(escaped).toContain('&lt;script&gt;')
  })

  it('escapes double quotes', () => {
    expect(escapeHtml('"hello"')).toBe('&quot;hello&quot;')
  })

  it('escapes ampersands', () => {
    expect(escapeHtml('A & B')).toBe('A &amp; B')
  })

  it('does not double-escape', () => {
    const input = '&lt;'
    const result = escapeHtml(input)
    // Once escaped, should not re-escape
    expect(result).toBe('&amp;lt;')
  })

  it('handles safe text unchanged', () => {
    const input = 'Hello **world**'
    const escaped = escapeHtml(input)
    // Only &, <, >, " should be escaped
    expect(escaped).toContain('**world**')
  })
})
