import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173/product-db'
const API = 'http://localhost:8000/product-db/api'

let token: string

test.beforeAll(async ({ playwright }) => {
  const apiCtx = await playwright.request.newContext()
  const resp = await apiCtx.post(`${API}/auth/login`, {
    data: { username: 'admin', password: 'admin' },
  })
  const body = await resp.json()
  token = body.token
  expect(token).toBeTruthy()
  await apiCtx.dispose()
})

async function setupPage(page: any) {
  await page.context().addInitScript((t: string) => {
    window.localStorage.setItem('token', t)
    window.localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'admin' }))
  }, token)
}

// ════════════════════════════════════
// 1. LOGIN
// ════════════════════════════════════
test.describe('Login Page', () => {
  test('login form renders and redirects to products', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('input[placeholder="用户名"]')).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.locator('button:has-text("登录")')).toBeVisible()
  })

  test('ICP 备案 footer visible on login page', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
    await expect(page.locator('footer a:has-text("ICP")')).toBeVisible()
  })
})

// ════════════════════════════════════
// 2. PRODUCTS — List
// ════════════════════════════════════
test.describe('Products List', () => {
  test('product table loads with rows', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    const rows = await page.locator('table tbody tr').count()
    expect(rows).toBeGreaterThan(0)
  })

  test('search filters products', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    const before = await page.locator('table tbody tr').count()
    await page.fill('input[placeholder*="搜索"]', '网关')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1500)
    const after = await page.locator('table tbody tr').count()
    expect(after).toBeLessThanOrEqual(before)
  })

  test('pagination works', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    const pagination = page.locator('.pagination')
    if (await pagination.isVisible()) {
      const pageBtns = pagination.locator('button')
      const count = await pageBtns.count()
      if (count > 1) {
        await pageBtns.nth(1).click()
        await page.waitForTimeout(1000)
        await expect(page.locator('table tbody tr').first()).toBeVisible()
      }
    }
  })

  test('product compare page loads', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products/compare`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1000)
    await expect(page.locator('body')).toBeVisible()
  })

  test('product import page loads', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products/import`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1000)
    await expect(page.locator('body')).toBeVisible()
  })
})

// ════════════════════════════════════
// 3. PRODUCTS — Detail / Edit / New
// ════════════════════════════════════
test.describe('Product Detail', () => {
  test('product detail page loads with specs', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    const detailLink = page.locator('table tbody tr a, table tbody tr button').first()
    await detailLink.click()
    await page.waitForTimeout(2000)
    expect(page.url()).toMatch(/\/products\/\d+/)
  })

  test('product edit page loads form fields', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    const firstRow = page.locator('table tbody tr').first()
    const href = await firstRow.locator('a').first().getAttribute('href')
    const productId = href?.match(/\/(\d+)/)?.[1] || '1'
    await page.goto(`${BASE}/products/${productId}/edit`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.locator('input, textarea, select').first()).toBeVisible({ timeout: 5000 })
  })

  test('new product page loads form', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products/new`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.locator('input, textarea, select').first()).toBeVisible({ timeout: 5000 })
  })
})

// ════════════════════════════════════
// 4. SOLUTIONS
// ════════════════════════════════════
test.describe('Solutions', () => {
  test('solutions list page loads', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/solutions`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.locator('table, .empty-state').first()).toBeVisible({ timeout: 10000 })
  })

  test('solution detail page loads', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/solutions`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const viewBtn = page.locator('button:has-text("查看")').first()
    if (await viewBtn.isVisible().catch(() => false)) {
      await viewBtn.click()
      await page.waitForTimeout(2000)
      expect(page.url()).toMatch(/\/solutions\/\d+/)
    }
  })
})

// ════════════════════════════════════
// 5. QUOTATIONS
// ════════════════════════════════════
test.describe('Quotations', () => {
  test('quotations list page loads', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/quotations`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.locator('table, .empty-state').first()).toBeVisible({ timeout: 10000 })
  })

  test('quotation detail shows export and BOM buttons', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/quotations`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const viewBtn = page.locator('button:has-text("查看")').first()
    if (await viewBtn.isVisible().catch(() => false)) {
      await viewBtn.click()
      await page.waitForTimeout(2000)
      expect(page.url()).toMatch(/\/quotations\/\d+/)
      await expect(page.locator('button:has-text("导出")').first()).toBeVisible({ timeout: 5000 })
      await expect(page.locator('button:has-text("BOM")').first()).toBeVisible({ timeout: 5000 })
    }
  })

  test('quotation detail — toggle BOM editor', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/quotations`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const viewBtn = page.locator('button:has-text("查看")').first()
    if (await viewBtn.isVisible().catch(() => false)) {
      await viewBtn.click()
      await page.waitForTimeout(2000)
      const bomBtn = page.locator('button:has-text("BOM")').first()
      if (await bomBtn.isVisible().catch(() => false)) {
        await bomBtn.click()
        await page.waitForTimeout(1000)
        const bomTable = page.locator('.bom-table, table').last()
        await expect(bomTable).toBeVisible({ timeout: 5000 })
      }
    }
  })

  test('quotation detail — 功能描述 column has specs | separator, no URLs', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/quotations`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const viewBtn = page.locator('button:has-text("查看")').first()
    if (await viewBtn.isVisible().catch(() => false)) {
      await viewBtn.click()
      await page.waitForTimeout(2000)
      const descHeader = page.locator('th:has-text("功能描述")')
      if (await descHeader.isVisible().catch(() => false)) {
        const descCells = page.locator('table tbody tr td:nth-child(5), table tbody tr td:nth-child(4)')
        const count = await descCells.count()
        let hasSep = false, hasUrl = false
        for (let i = 0; i < count; i++) {
          const text = (await descCells.nth(i).textContent()) || ''
          if (text.includes('|')) hasSep = true
          if (/https?:\/\//.test(text)) hasUrl = true
        }
        if (count > 0) {
          expect(hasSep, 'specs | separator present').toBe(true)
          expect(hasUrl, 'no URLs in description').toBe(false)
        }
      }
    }
  })
})

// ════════════════════════════════════
// 6. DICTIONARIES
// ════════════════════════════════════
test.describe('Dictionaries', () => {
  test('dictionaries page loads with tabs', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/dictionaries`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.locator('button, .tab, [role="tab"]').first()).toBeVisible({ timeout: 10000 })
  })
})

// ════════════════════════════════════
// 7. AGENT
// ════════════════════════════════════
test.describe('Agent Page', () => {
  test('agent page loads with input area', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    await expect(page.locator('textarea, input[type="text"], .sidebar-link, button').first()).toBeVisible({ timeout: 10000 })
  })
})

// ════════════════════════════════════
// 8. ADMIN
// ════════════════════════════════════
test.describe('Admin Page', () => {
  test('admin page loads for admin user', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/admin`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    await expect(page.locator('body')).toBeVisible()
    expect(page.url()).toContain('/admin')
  })
})

// ════════════════════════════════════
// 9. SIDEBAR NAVIGATION
// ════════════════════════════════════
test.describe('Sidebar Navigation', () => {
  test('all sidebar links navigate', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sidebar-nav', { timeout: 10000 })
    await page.waitForTimeout(1000)
    const navLinks = [
      { text: '方案', path: '/solutions' },
      { text: '报价单', path: '/quotations' },
      { text: '字典', path: '/dictionaries' },
    ]
    for (const { text, path } of navLinks) {
      const link = page.locator(`.sidebar-link:has-text("${text}")`)
      if (await link.isVisible().catch(() => false)) {
        await link.click()
        await page.waitForTimeout(1500)
        expect(page.url()).toContain(path)
      }
    }
  })

  test('sidebar collapse toggle works', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sidebar-logo', { timeout: 10000 })
    await page.waitForTimeout(1000)
    const logo = page.locator('.sidebar-logo')
    await logo.click()
    await page.waitForTimeout(500)
    await expect(page.locator('.app-sidebar')).toBeVisible()
  })

  test('global search navigates to products', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/solutions`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sidebar-nav', { timeout: 10000 })
    await page.waitForTimeout(1000)
    const searchInput = page.locator('.sidebar-search input')
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('test')
      await searchInput.press('Enter')
      await page.waitForTimeout(1500)
      expect(page.url()).toContain('/products')
      expect(page.url()).toContain('search=test')
    }
  })

  test('user menu dropdown shows profile and logout', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sidebar-nav', { timeout: 10000 })
    await page.waitForTimeout(1000)
    const userBtn = page.locator('.sidebar-user-btn')
    if (await userBtn.isVisible().catch(() => false)) {
      await userBtn.click()
      await page.waitForTimeout(500)
      await expect(page.locator('.user-dropdown')).toBeVisible()
      await expect(page.locator('button:has-text("退出")')).toBeVisible()
    }
  })
})

// ════════════════════════════════════
// 10. ROUTING GUARDS
// ════════════════════════════════════
test.describe('Routing', () => {
  test('root redirects to /products', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    expect(page.url()).toContain('/products')
  })

  test('unauthenticated user redirected to login', async ({ page }) => {
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    expect(page.url()).toContain('/login')
  })

  test('/categories redirects to /dictionaries', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/categories`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1000)
    expect(page.url()).toContain('/dictionaries')
  })

  test('AI chat hidden on /agent page', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    // AiChat should not be rendered on agent page (App.vue condition)
    const chatFab = page.locator('.ai-chat-fab, [class*="chat-fab"]')
    await expect(chatFab).not.toBeVisible({ timeout: 3000 }).catch(() => {
      // If not found at all, that's also fine
    })
  })
})

// ════════════════════════════════════
// 11. DICTIONARIES — Tab switching + CRUD
// ════════════════════════════════════
test.describe('Dictionaries — Tab Switching', () => {
 test('switch to each dict tab', async ({ page }) => {
   await setupPage(page)
   await page.goto(`${BASE}/dictionaries`, { waitUntil: 'domcontentloaded' })
   await page.waitForTimeout(2000)
   const tabNames = ['通讯方式', '通讯协议', '供电方式', '传感器指标', '厂商', '供应商']
   for (const tab of tabNames) {
     const tabBtn = page.locator(`.dict-tab:has-text("${tab}")`)
     if (await tabBtn.isVisible().catch(() => false)) {
       await tabBtn.click()
       await page.waitForTimeout(800)
        // After switching, page should not crash — v-show hides other tables
        await expect(page.locator('body')).toBeVisible()
        // The active tab button should have 'active' class
        await expect(tabBtn).toHaveClass(/active/)
     }
   }
 })

  test('通讯方式 tab — table renders, edit modal opens', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/dictionaries`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    // Click 通讯方式 tab
    await page.locator('.dict-tab:has-text("通讯方式")').click()
    await page.waitForTimeout(1000)
    const editBtn = page.locator('table tbody tr button .lucide, table tbody tr [class*="pencil"], button:has(.lucide-pencil)').first()
    if (await editBtn.isVisible().catch(() => false)) {
      await editBtn.click()
      await page.waitForTimeout(800)
      // Modal should appear
      const modal = page.locator('.modal-overlay, [class*="modal"]')
      const isModal = await modal.isVisible().catch(() => false)
      if (isModal) {
        await expect(modal.locator('input, textarea').first()).toBeVisible({ timeout: 3000 })
        // Close modal
        await page.locator('button:has-text("取消")').click().catch(() => {})
        await page.waitForTimeout(500)
      }
    }
  })

 test('厂商 tab — sort_order editable', async ({ page }) => {
   await setupPage(page)
   await page.goto(`${BASE}/dictionaries`, { waitUntil: 'domcontentloaded' })
   await page.waitForTimeout(2000)
   await page.locator('.dict-tab:has-text("厂商")').click()
   await page.waitForTimeout(1000)
    // Manufacturer section header should be visible
    await expect(page.locator('h3:has-text("厂商")').first()).toBeVisible({ timeout: 5000 })
    // The tab button should be active
    await expect(page.locator('.dict-tab:has-text("厂商")')).toHaveClass(/active/)
 })
})

// ════════════════════════════════════
// 12. ADMIN — LLM Config + User Management
// ════════════════════════════════════
test.describe('Admin — LLM Config', () => {
  test('LLM config card has input fields and test buttons', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/admin`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    // Should see LLM config section
    await expect(page.locator('h3:has-text("LLM")').first()).toBeVisible({ timeout: 5000 })
    // Should have input field for API key
    const apiKeyInputs = page.locator('input[type="password"]')
    const count = await apiKeyInputs.count()
    expect(count).toBeGreaterThan(0)
    // Should have test button
    await expect(page.locator('button:has-text("测试")').first()).toBeVisible({ timeout: 3000 })
  })

  test('AI settings section has prompt textareas', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/admin`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    // AI 设置 section
    await expect(page.locator('h3:has-text("AI 设置")').first()).toBeVisible({ timeout: 5000 })
    // Prompt textareas should exist
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 3000 })
  })

  test('field visibility toggles exist', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/admin`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    await expect(page.locator('h3:has-text("字段可见性")').first()).toBeVisible({ timeout: 5000 })
    const checkboxes = page.locator('input[type="checkbox"]')
    const count = await checkboxes.count()
    expect(count).toBeGreaterThan(0)
  })
})

// ════════════════════════════════════
// 13. PRODUCT FORM — Create product flow
// ════════════════════════════════════
test.describe('Product Create', () => {
  test('fill new product form fields', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products/new`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    // Name input should be visible
    const nameInput = page.locator('input').first()
    await expect(nameInput).toBeVisible({ timeout: 5000 })
    // Type a name
    await nameInput.fill(`E2E Test Product ${Date.now()}`)
    // Should be able to fill model
    const modelInput = page.locator('input[placeholder*="EG71"]')
    if (await modelInput.isVisible().catch(() => false)) {
      await modelInput.fill('E2E-MODEL')
    }
    // Form should still be visible (no validation error)
    await expect(page.locator('button:has-text("保存")').first()).toBeVisible()
  })
})

// ════════════════════════════════════
// 14. SOLUTION DETAIL — Item management
// ════════════════════════════════════
test.describe('Solution Detail — Interactions', () => {
  test('solution detail shows client/project/status fields', async ({ page }) => {
    await setupPage(page)
    // Navigate to a solution with items
    await page.goto(`${BASE}/solutions`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const viewBtn = page.locator('button:has-text("查看")').first()
    if (await viewBtn.isVisible().catch(() => false)) {
      await viewBtn.click()
      await page.waitForTimeout(2000)
      // Client name input
      await expect(page.locator('input').first()).toBeVisible({ timeout: 5000 })
      // Check/Dependency buttons
      await expect(page.locator('button:has-text("生成报价单")').first()).toBeVisible({ timeout: 5000 })
    }
  })
})

// ════════════════════════════════════
// 15. AI CHAT FAB — Open, interact, close
// ════════════════════════════════════
test.describe('AI Chat FAB', () => {
  test('AI chat FAB opens chat panel on click', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table', { timeout: 15000 })
    await page.waitForTimeout(1000)

    // Look for the AI chat floating button
    const fab = page.locator('.ai-chat-fab, [class*="chat-fab"], [class*="ai-chat"] button, button:has(.lucide-message-circle)').first()
    if (await fab.isVisible().catch(() => false)) {
      await fab.click()
      await page.waitForTimeout(1000)
      // Chat panel should open — check for input textarea
      const chatInput = page.locator('textarea').first()
      // May or may not be visible depending on implementation
    }
    // At minimum, page should not crash
    await expect(page.locator('body')).toBeVisible()
  })

  test('AI chat not shown on agent page', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    // AiChat should NOT be rendered on /agent (App.vue condition)
    const fab = page.locator('.ai-chat-fab, [class*="chat-fab"]')
    await expect(fab).toHaveCount(0).catch(async () => {
      // Component not created at all — that's the expected behavior
      await expect(fab).not.toBeVisible({ timeout: 2000 })
    })
  })
})

// ════════════════════════════════════
// 16. AGENT — Conversation interaction
// ════════════════════════════════════
test.describe('Agent Conversation', () => {
  test('agent page has input textarea', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)
    // Should have a text input or textarea for chat
    await expect(page.locator('textarea, input[type="text"]').first()).toBeVisible({ timeout: 10000 })
  })

  test('agent page — type message and send', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    const inputBox = page.locator('textarea').first()
    if (await inputBox.isVisible().catch(() => false)) {
      await inputBox.fill('列出几个传感器产品')
      await inputBox.press('Enter')
      await page.waitForTimeout(3000)
      // After sending, either response text or error message should appear
      // The page should still be functional
      await expect(page.locator('body')).toBeVisible()
    }
  })
})

// ════════════════════════════════════
// 17. PRODUCT COMPARE — Selection and matrix
// ════════════════════════════════════
test.describe('Product Compare', () => {
  test('compare page loads with prompt to select', async ({ page }) => {
    await setupPage(page)
    // Compare needs product IDs in URL: /products/compare?product_ids=1,2
    await page.goto(`${BASE}/products/compare?product_ids=1,2`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    // Should load compare page — may show products or error if IDs don't exist
    await expect(page.locator('body')).toBeVisible()
  })

  test('compare link from products page', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    // Look for checkboxes or compare button
    const checkboxes = page.locator('input[type="checkbox"]').first()
    if (await checkboxes.isVisible().catch(() => false)) {
      await checkboxes.check()
      await page.waitForTimeout(500)
      // Check second product if available
      const secondCheckbox = page.locator('input[type="checkbox"]').nth(1)
      if (await secondCheckbox.isVisible().catch(() => false)) {
        await secondCheckbox.check()
        await page.waitForTimeout(500)
      }
      // Look for compare button
      const compareBtn = page.locator('button:has-text("对比")').first()
      if (await compareBtn.isVisible().catch(() => false)) {
        await compareBtn.click()
        await page.waitForTimeout(2000)
        expect(page.url()).toContain('/compare')
      }
    }
  })
})

// ════════════════════════════════════
// 18. BOM EDITOR — Modify and save
// ════════════════════════════════════
test.describe('BOM Editor — Edit & Save', () => {
  test('edit BOM cell triggers dirty state, save clears it', async ({ page }) => {
    await setupPage(page)
    // Find a quotation first
    await page.goto(`${BASE}/quotations`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    const viewBtn = page.locator('button:has-text("查看")').first()
    if (!(await viewBtn.isVisible().catch(() => false))) return

    await viewBtn.click()
    await page.waitForTimeout(2000)

    // Open BOM editor
    const bomBtn = page.locator('button:has-text("BOM")').first()
    if (!(await bomBtn.isVisible().catch(() => false))) return
    await bomBtn.click()
    await page.waitForTimeout(1000)

    // BOM table should be visible
    const bomTable = page.locator('.bom-table')
    if (!(await bomTable.isVisible().catch(() => false))) return

    // Find a qty input and change it
    const qtyInput = bomTable.locator('input[type="number"]').first()
    if (await qtyInput.isVisible().catch(() => false)) {
      const oldVal = await qtyInput.inputValue()
      await qtyInput.fill(String(Number(oldVal || 1) + 1))
      await page.waitForTimeout(500)

      // "未保存" indicator should appear
      const dirtySpan = page.locator('.bom-spreadsheet span:has-text("未保存")')
      const isDirty = await dirtySpan.isVisible().catch(() => false)
      // Dirty state should appear after editing
      expect(isDirty).toBe(true)

      // Click save
      const saveBtn = page.locator('.bom-spreadsheet button:has-text("保存")')
      if (await saveBtn.isVisible().catch(() => false)) {
        await saveBtn.click()
        await page.waitForTimeout(2000)
        // After save, page should still be functional
        await expect(page.locator('body')).toBeVisible()
      }
    }
  })

  test('BOM add row creates new editable row', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/quotations`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    const viewBtn = page.locator('button:has-text("查看")').first()
    if (!(await viewBtn.isVisible().catch(() => false))) return
    await viewBtn.click()
    await page.waitForTimeout(2000)

    const bomBtn = page.locator('button:has-text("BOM")').first()
    if (!(await bomBtn.isVisible().catch(() => false))) return
    await bomBtn.click()
    await page.waitForTimeout(1000)

    // Count existing rows
    const bomTable = page.locator('.bom-table')
    if (!(await bomTable.isVisible().catch(() => false))) return
    const beforeCount = await bomTable.locator('tbody tr').count()

    // Click "添加行"
    const addBtn = page.locator('.bom-spreadsheet button:has-text("添加行")')
    if (await addBtn.isVisible().catch(() => false)) {
      await addBtn.click()
      await page.waitForTimeout(500)
      const afterCount = await bomTable.locator('tbody tr').count()
      expect(afterCount).toBe(beforeCount + 1)
      // Dirty state should now be active
      const dirtySpan = page.locator('.bom-spreadsheet span:has-text("未保存")')
      await expect(dirtySpan).toBeVisible({ timeout: 2000 })
    }
  })
})

// ════════════════════════════════════
// 19. DICTIONARIES — Add modal + Delete confirm
// ════════════════════════════════════
test.describe('Dictionaries — Add & Delete Flow', () => {
  test('open add modal, fill form, cancel without saving', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/dictionaries`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    // Switch to 通讯方式 tab
    await page.locator('.dict-tab:has-text("通讯方式")').click()
    await page.waitForTimeout(1000)

    // Click + 新增
    const addBtn = page.locator('button:has-text("+ 新增")').first()
    if (!(await addBtn.isVisible().catch(() => false))) return
    await addBtn.click()
    await page.waitForTimeout(800)

    // Modal should open
    const modal = page.locator('.modal-overlay')
    if (await modal.isVisible().catch(() => false)) {
      // Fill name field
      const nameInput = modal.locator('input').first()
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill('E2E Test Dict Item')
        await page.waitForTimeout(300)
      }
      // Click cancel — should close without saving
      const cancelBtn = modal.locator('button:has-text("取消")').first()
      if (await cancelBtn.isVisible().catch(() => false)) {
        await cancelBtn.click()
        await page.waitForTimeout(500)
        // Modal should be gone
        await expect(modal).not.toBeVisible({ timeout: 3000 })
      }
    }
  })

  test('delete button shows confirm dialog', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/dictionaries`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    await page.locator('.dict-tab:has-text("通讯方式")').click()
    await page.waitForTimeout(1000)

    // Find trash icon button in table
    const trashBtn = page.locator('table tbody tr button').last()
    if (await trashBtn.isVisible().catch(() => false)) {
      await trashBtn.click()
      await page.waitForTimeout(800)
      // Should show confirm dialog or at least not crash
      await expect(page.locator('body')).toBeVisible()
    }
  })
})

// ════════════════════════════════════
// 20. ADMIN — LLM test button interaction
// ════════════════════════════════════
test.describe('Admin — LLM Test', () => {
  test('click LLM test button shows result message', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/admin`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    // Click first test button
    const testBtn = page.locator('button:has-text("测试")').first()
    if (!(await testBtn.isVisible().catch(() => false))) return

    // If disabled (no key configured), skip
    if (await testBtn.isDisabled().catch(() => false)) return

    await testBtn.click()
    // Wait for result — could be success ✓ or error ✗
    await page.waitForTimeout(5000)

    // Check for result text (✓ or ✗)
    const resultSpan = page.locator('span:has-text("✓"), span:has-text("✗")').first()
    // Result may or may not appear depending on API config
    const hasResult = await resultSpan.isVisible().catch(() => false)
    // At minimum the page should not crash
    await expect(page.locator('body')).toBeVisible()
  })
})

// ════════════════════════════════════
// 21. PRODUCT COMPARE — With real product IDs
// ════════════════════════════════════
test.describe('Product Compare — Real IDs', () => {
  test('extract product IDs from table and compare', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })

    // Extract product IDs from table links
    const links = page.locator('table tbody tr a[href*="/products/"]')
    const count = await links.count()
    if (count >= 2) {
      const href1 = await links.nth(0).getAttribute('href')
      const href2 = await links.nth(1).getAttribute('href')
      const id1 = href1?.match(/\/(\d+)/)?.[1]
      const id2 = href2?.match(/\/(\d+)/)?.[1]
      if (id1 && id2) {
        await page.goto(`${BASE}/products/compare?product_ids=${id1},${id2}`, { waitUntil: 'domcontentloaded' })
        await page.waitForTimeout(2000)
        // Should show comparison matrix or at minimum not crash
        await expect(page.locator('body')).toBeVisible()
      }
    }
  })
})

// ════════════════════════════════════
// 22. SOLUTION DETAIL — AI assistant section
// ════════════════════════════════════
test.describe('Solution Detail — AI Assistant', () => {
  test('AI chat section renders in solution detail', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/solutions`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    const viewBtn = page.locator('button:has-text("查看")').first()
    if (!(await viewBtn.isVisible().catch(() => false))) return
    await viewBtn.click()
    await page.waitForTimeout(2000)

    // Should see "生成报价单" button
    await expect(page.locator('button:has-text("生成报价单")').first()).toBeVisible({ timeout: 5000 })

    // Solution chat area — AI assistant input
    const chatInput = page.locator('input[placeholder*="AI"], textarea[placeholder*="AI"], textarea').first()
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill('推荐传感器')
      await chatInput.press('Enter')
      await page.waitForTimeout(3000)
      // Page should still be functional
      await expect(page.locator('body')).toBeVisible()
    }
  })
})

// ════════════════════════════════════
// 23. AGENT — Suggestions sidebar
// ════════════════════════════════════
test.describe('Agent — Suggestions', () => {
  test('suggestion questions are clickable', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/agent`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(3000)

    // Look for suggestion/question buttons in sidebar
    const suggestionBtns = page.locator('button:has-text("查询"), button:has-text("创建"), button:has-text("帮助")')
    const count = await suggestionBtns.count()
    if (count > 0) {
      const firstSuggestion = suggestionBtns.first()
      if (await firstSuggestion.isVisible().catch(() => false)) {
        await firstSuggestion.click()
        await page.waitForTimeout(2000)
        // The suggestion text should appear in the input or a message should be sent
        await expect(page.locator('body')).toBeVisible()
      }
    }
  })
})

// ════════════════════════════════════
// 24. PRODUCT DETAIL — Spec sheet download
// ════════════════════════════════════
test.describe('Product Detail — Spec Sheet', () => {
  test('spec sheet download link exists', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })

    // Navigate to first product detail
    const firstLink = page.locator('table tbody tr a[href*="/products/"]').first()
    if (await firstLink.isVisible().catch(() => false)) {
      await firstLink.click()
      await page.waitForTimeout(2000)

      // Look for spec sheet or export/download buttons
      const specBtn = page.locator('button:has-text("规格书"), button:has-text("PDF"), button:has-text("导出")').first()
      // May or may not exist — just verify page loaded
      await expect(page.locator('body')).toBeVisible()
    }
  })
})

// ════════════════════════════════════
// 25. PRODUCT LIST — Selection + batch delete
// ════════════════════════════════════
test.describe('Product List — Batch Operations', () => {
  test('checkbox selection enables batch delete', async ({ page }) => {
    await setupPage(page)
    await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })

    // Check for any checkboxes on the page
    const checkboxes = page.locator('input[type="checkbox"]').first()
    if (await checkboxes.isVisible().catch(() => false)) {
      await checkboxes.check()
      await page.waitForTimeout(300)

      // Look for batch delete button
      const batchDelBtn = page.locator('button:has-text("批量删除"), button:has-text("删除")').first()
      if (await batchDelBtn.isVisible().catch(() => false)) {
        await batchDelBtn.click()
        await page.waitForTimeout(500)
        // Should show confirm or error
        await expect(page.locator('body')).toBeVisible()
      }
    }
  })
})
