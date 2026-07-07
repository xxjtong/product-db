import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173/product-db'
const API = 'http://localhost:8000/product-db/api'

// ════════════════════════════════════
// Agent history user isolation (R21.1)
// ════════════════════════════════════

test.describe('Agent History Isolation', () => {

  test('localStorage keys include user ID prefix', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input[placeholder="用户名"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.click('button:has-text("登录")')
    await page.waitForURL('**/products', { timeout: 10000 })

    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1000)

    const keys: string[] = await page.evaluate(() => {
      const ks: string[] = []
      for (let i = 0; i < localStorage.length; i++) ks.push(localStorage.key(i)!)
      return ks
    })

    // No old-style "agent_chats" or "agent_msgs_*" keys without user ID
    const oldKeys = keys.filter(k => k.startsWith('agent_') && !k.match(/^agent_\d+_/))
    expect(oldKeys).toHaveLength(0)

    // All agent keys scoped "agent_{userId}_..."
    const agentKeys = keys.filter(k => k.startsWith('agent_'))
    for (const k of agentKeys) {
      expect(k).toMatch(/^agent_\d+_/)
    }
  })

  test('localStorage isolation: user B does not see user A agent keys', async ({ browser }) => {
    // ── User A: admin (id=1) ──
    const ctxA = await browser.newContext()
    const pageA = await ctxA.newPage()
    await pageA.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await pageA.fill('input[placeholder="用户名"]', 'admin')
    await pageA.fill('input[type="password"]', 'admin')
    await pageA.click('button:has-text("登录")')
    await pageA.waitForURL('**/products', { timeout: 10000 })

    await pageA.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await pageA.waitForTimeout(1000)

    // Inject a fake chat for admin
    await pageA.evaluate(() => {
      localStorage.setItem('agent_1_chats', JSON.stringify([{ id: 'c_test', title: 'Admin chat', updatedAt: Date.now() }]))
    })

    // Verify admin sees agent_1_chats
    const hasAdminChat = await pageA.evaluate(() => localStorage.getItem('agent_1_chats') !== null)
    expect(hasAdminChat).toBe(true)

    // ── User B: register via API, then login in browser ──
    const apiCtx = await browser.newContext()
    const apiReq = await apiCtx.request.post(`${API}/auth/register`, {
      data: { username: 'agenttest2', password: 'test123456', email: 'agenttest2@test.com' },
    })
    // 200 = created, 400 = already exists — both fine
    expect([200, 400]).toContain(apiReq.status())

    const ctxB = await browser.newContext()
    const pageB = await ctxB.newPage()
    await pageB.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await pageB.fill('input[placeholder="用户名"]', 'agenttest2')
    await pageB.fill('input[type="password"]', 'test123456')
    await pageB.click('button:has-text("登录")')
    await pageB.waitForURL('**/products', { timeout: 10000 })

    await pageB.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await pageB.waitForTimeout(1000)

    // User B must NOT see admin's agent_1_chats
    const seesAdminChat = await pageB.evaluate(() => localStorage.getItem('agent_1_chats') !== null)
    expect(seesAdminChat).toBe(false)

    // User B's agent keys must use their own user ID (not "agent_1_")
    const keysB: string[] = await pageB.evaluate(() => {
      const ks: string[] = []
      for (let i = 0; i < localStorage.length; i++) ks.push(localStorage.key(i)!)
      return ks
    })
    const bAgentKeys = keysB.filter(k => k.startsWith('agent_'))
    for (const k of bAgentKeys) {
      expect(k).not.toMatch(/^agent_1_/)
      expect(k).toMatch(/^agent_\d+_/)
    }

    await ctxA.close()
    await ctxB.close()
    await apiCtx.close()
  })
})
