/**
 * R68~R71 修复项的回归断言。
 *
 * 设计约束：这套用例要能**直接对着生产跑**，所以每一条都必须满足
 * 「零写入」或「失败也是安全的」：
 *  - 注册关闭语义：只发请求看状态码，不建号（关闭时本就建不了）
 *  - 导入幂等：构造一行与既有产品**完全相同**的数据，预期全部被跳过 → 不产生新数据
 *  - 报价单 404：用一个不存在的方案 ID，不会建单
 *  - 字典引用保护：**先确认该项确实被产品引用**才尝试删除；找不到就 skip，
 *    绝不冒险去删一个没被引用的字典项
 */
import { test, expect } from '@playwright/test'
import { API, IS_REMOTE, login } from './auth'

let token: string

test.beforeAll(async ({ playwright }) => {
  token = await login(playwright)
})

function authHeaders() {
  return { Authorization: `Bearer ${token}` }
}

async function productTotal(request: any): Promise<number> {
  const r = await request.get(`${API}/products?per_page=1`, { headers: authHeaders() })
  return (await r.json()).total
}

test.describe('Regression — 注册关闭语义（R68）', () => {
  test('注册关闭时反复请求稳定回 403，不会变成 429', async ({ request }) => {
    const st = await request.get(`${API}/auth/registration-status`)
    const open = (await st.json()).open
    test.skip(open, '本环境开放注册，跳过「关闭语义」断言')

    for (let i = 0; i < 3; i++) {
      const r = await request.post(`${API}/auth/register`, {
        data: { username: `e2e_probe_${i}`, password: 'probe12345' },
      })
      expect(r.status(), `第 ${i + 1} 次应为 403`).toBe(403)
    }
  })
})

test.describe('Regression — 导入幂等（R69）', () => {
  test('重复导入已存在的产品行不产生新数据', async ({ request }) => {
    const listResp = await request.get(`${API}/products?per_page=1`, { headers: authHeaders() })
    const p = (await listResp.json()).products?.[0]
    test.skip(!p?.name || !p?.category_name, '缺少可构造的行（需要 name + category_name）')

    const before = await productTotal(request)
    const r = await request.post(`${API}/products/import-confirm`, {
      headers: authHeaders(),
      data: {
        mapping: { '0': 'name', '1': 'model', '2': 'category', '3': 'manufacturer', '4': 'price' },
        rows: [[p.name, p.model || '', p.category_name, p.manufacturer_name || '', '1']],
      },
    })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.imported, '已存在的行必须被跳过').toBe(0)
    expect(body.skipped).toBeGreaterThanOrEqual(1)
    expect(await productTotal(request), '产品总数不得变化').toBe(before)
  })
})

test.describe('Regression — 品类树可见域（R70）', () => {
  test('树里的品类数与列表 total 一致', async ({ request }) => {
    const treeResp = await request.get(`${API}/categories/tree`, { headers: authHeaders() })
    expect(treeResp.status()).toBe(200)
    const listed = await request.get(`${API}/categories?per_page=500`, { headers: authHeaders() })
    expect(listed.status()).toBe(200)

    const walk = (nodes: any[]): number =>
      nodes.reduce((n, x) => n + 1 + walk(x.children || []), 0)
    const tree = (await treeResp.json()).tree as any[]
    expect(walk(tree)).toBe((await listed.json()).total)
  })
})

test.describe('Regression — 报价单创建（R71）', () => {
  test('方案不存在时回 404，不再静默给一张空白报价单', async ({ request }) => {
    const r = await request.post(`${API}/quotations`, {
      headers: authHeaders(),
      data: { solution_id: 99999999 },
    })
    expect(r.status()).toBe(404)
  })
})

test.describe('Regression — 字典引用保护（R68）', () => {
  test('删除被产品引用的厂商返回 409 且该项仍在', async ({ request }) => {
    const mfgResp = await request.get(`${API}/dicts/manufacturers?per_page=200`, { headers: authHeaders() })
    const mfgs = (await mfgResp.json()).manufacturers || []

    // 只挑**确实被引用**的厂商来尝试删除；一个都没找到就 skip（绝不误删）
    let target: any = null
    for (const m of mfgs.slice(0, 40)) {
      const used = await request.get(`${API}/products?manufacturer_id=${m.id}&per_page=1`,
        { headers: authHeaders() })
      if ((await used.json()).total > 0) { target = m; break }
    }
    test.skip(!target, '没有找到被引用的厂商，跳过（避免误删未引用的项）')

    const del = await request.delete(`${API}/dicts/manufacturers/${target.id}`, { headers: authHeaders() })
    expect(del.status(), '被引用的厂商必须回 409').toBe(409)
    expect((await del.json()).detail).toContain('引用')

    const still = await request.get(`${API}/dicts/manufacturers/${target.id}`, { headers: authHeaders() })
    expect(still.status(), '该厂商必须仍然存在').toBe(200)
  })
})

test.describe('Regression — 未授权访问', () => {
  test('不带 token 访问 admin 接口被拒', async ({ request }) => {
    test.skip(!IS_REMOTE, '本地 DEV_MODE 会自动登录，无法验证')
    const r = await request.get(`${API}/admin/users`)
    expect([401, 403]).toContain(r.status())
  })
})
