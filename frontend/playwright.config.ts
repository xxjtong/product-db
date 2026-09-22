import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: { timeout: 5000 },
  retries: process.env.CI ? 2 : 0,
  // CI 里没有 Hermes、也不开放自助注册，`agent-isolation.spec.ts` 的两条必然失败 ——
  // 它靠这两样东西（真实 AI 往返 + 建号）验证 agent 历史的用户隔离。
  // 其余 100 条都能在 CI 的临时库上跑通（数据由 backend/seed_e2e.py 提供）。
  testIgnore: process.env.CI ? ['**/agent-isolation.spec.ts'] : [],
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173/product-db',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npx vite --host 0.0.0.0 --port 5173',
    url: 'http://localhost:5173/product-db/',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
})
