import { defineConfig, devices } from '@playwright/test'

/**
 * CI 专用 Playwright 配置（用于 GitHub Actions e2e-frontend job）
 *
 * 与 playwright.config.ts（本地开发版）的区别：
 *   1. 通过 webServer 自动启动 vite dev server（无需手动 npm run dev &）
 *   2. 不依赖 setup project（无真实后端登录）；通过 E2E_STORAGE_STATE 环境变量
 *      指向 CI 生成的 mock auth JSON（预填 localStorage access_token，让路由守卫放行）
 *   3. chromium project 无 dependencies（不跑 auth.setup.ts）
 *
 * 触发方式（ci.yml e2e-frontend job）：
 *   npx playwright test --config=playwright.config.ci.ts
 */
export default defineConfig({
  // 仅匹配已完整 mock 后端 API 的 spec。CI 环境只有前端 vite + mock storageState，
  // 其他 e2e spec 依赖真实后端，在 CI 中会等 API 响应直至超时。新增 spec 需先完成
  // API mock 才能加入此列表。
  testMatch: ['**/e2e/llm_selection.spec.ts'],
  timeout: 30_000,
  retries: 2,
  workers: 1,

  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['github'],
  ],

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
    // CI 中通过 E2E_STORAGE_STATE 指向 mock auth JSON（预填 access_token）
    // 若未设置则不使用 storageState（会被路由守卫重定向到 /login，测试按需处理）
    storageState: process.env.E2E_STORAGE_STATE || undefined,
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // 通过 storageState 让前端 isAuthenticated=true，路由守卫放行
        storageState: process.env.E2E_STORAGE_STATE || undefined,
      },
      // 不依赖 setup project（CI 无真实后端，login 端点不可用）
    },
  ],

  // CI 中自动启动 vite dev server
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
