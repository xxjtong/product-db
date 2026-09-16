/**
 * E2E 目标环境与凭据 —— 全部从环境变量读取，使同一套测试既能跑本地、也能跑生产。
 *
 * 本地（默认值，DEV_MODE 免登录的 admin/admin + 本地端口）:
 *   npx playwright test
 *
 * 生产:
 *   E2E_BASE_URL=https://product-db.cn/product-db \
 *   E2E_API_URL=https://product-db.cn/product-db/api \
 *   E2E_USERNAME=tong E2E_PASSWORD=... E2E_USER_ID=2 E2E_ROLE=admin \
 *   npx playwright test --config=playwright.prod.config.ts
 *
 * 注意：E2E_ROLE / E2E_USER_ID 必须与凭据真实身份一致。前端路由守卫读 localStorage
 * 里的 role，后端按 token 里的 user 判权限 —— 两者不一致会产生"前端放行、后端 403"
 * 的假失败。
 */
import type { APIRequestContext, Page } from '@playwright/test'

export const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:5173/product-db'
export const API = process.env.E2E_API_URL ?? 'http://localhost:8000/product-db/api'

/** 是否指向远端（生产）环境 —— 用于跳过会写入生产或依赖开放注册的用例 */
export const IS_REMOTE = !!process.env.E2E_API_URL

export const CRED = {
  username: process.env.E2E_USERNAME ?? 'admin',
  password: process.env.E2E_PASSWORD ?? 'admin',
  id: Number(process.env.E2E_USER_ID ?? 1),
  role: process.env.E2E_ROLE ?? 'admin',
}

/** 用配置的凭据登录，返回 JWT */
export async function login(ctx: { request: { newContext(): Promise<APIRequestContext> } }): Promise<string> {
  const api = await ctx.request.newContext()
  try {
    const resp = await api.post(`${API}/auth/login`, {
      data: { username: CRED.username, password: CRED.password },
    })
    const body = await resp.json()
    return body.token ?? ''
  } finally {
    await api.dispose()
  }
}

/**
 * 在 SPA 脚本加载前注入 token + 与之一致的用户身份。
 * 传 customToken 可注入无效/过期 token（用于错误场景用例）。
 */
export async function injectAuth(page: Page, token: string): Promise<void> {
  const user = { id: CRED.id, username: CRED.username, role: CRED.role }
  await page.context().addInitScript(
    (payload: { token: string; user: { id: number; username: string; role: string } }) => {
      window.localStorage.setItem('token', payload.token)
      window.localStorage.setItem('user', JSON.stringify(payload.user))
    },
    { token, user },
  )
}
