import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173/product-db'
const API = 'http://localhost:8000/product-db/api'

test('full E2E: product list → solution → quotation with 功能描述 specs verification', async ({ page }) => {
  // 1. Login and get token
  const resp = await page.request.post(`${API}/auth/login`, {
    data: { username: 'admin', password: 'admin' },
  })
  const { token } = await resp.json()
  expect(token).toBeTruthy()

  // 2. Set token BEFORE SPA scripts run via addInitScript
  await page.context().addInitScript((t) => {
    window.localStorage.setItem('token', t)
  }, token)

  // 3. Load SPA
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  // Wait for SPA to bootstrap and render
  await page.waitForSelector('table', { timeout: 15000 })
  await page.waitForTimeout(1000)

  // 4. Product list - verify loaded
  await expect(page.locator('table tbody tr').first()).toBeVisible()
  const productRows = await page.locator('table tbody tr').count()
  expect(productRows).toBeGreaterThan(0)

  // 5. Navigate to solutions
  await page.click('a:has-text("方案")')
  await page.waitForTimeout(2000)
  await expect(page.locator('table')).toBeVisible({ timeout: 10000 })

  // 6. Open first solution
  const viewBtns = page.locator('button:has-text("查看")')
  const viewCount = await viewBtns.count()
  if (viewCount > 0) {
    await viewBtns.first().click()
    await page.waitForTimeout(2000)
    await expect(page.locator('th:has-text("功能描述")')).toBeVisible({ timeout: 5000 })
  }

  // 7. Navigate to quotations
  await page.click('a:has-text("报价单")')
  await page.waitForTimeout(2000)
  await expect(page.locator('table')).toBeVisible({ timeout: 10000 })

  // 8. Open first quotation
  const qtViewBtns = page.locator('button:has-text("查看")')
  const qtViewCount = await qtViewBtns.count()
  if (qtViewCount > 0) {
    await qtViewBtns.first().click()
    await page.waitForTimeout(2000)

    // 9. Verify 功能描述 column shows specs, no URLs
    await expect(page.locator('th:has-text("功能描述")')).toBeVisible({ timeout: 5000 })
    const descCells = page.locator('table tbody tr td:nth-child(4)')
    const count = await descCells.count()
    let hasSep = false, hasUrl = false
    for (let i = 0; i < count; i++) {
      const text = (await descCells.nth(i).textContent()) || ''
      if (text.includes('|')) hasSep = true
      if (/https?:\/\//.test(text)) hasUrl = true
    }
    expect(hasSep, 'specs | separator present').toBe(true)
    expect(hasUrl, 'no URLs in description').toBe(false)

    // 10. Export button
    await expect(page.locator('button:has-text("导出 xlsx")')).toBeVisible()
  }
})
