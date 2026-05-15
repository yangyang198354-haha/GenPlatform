import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 配置
 *
 * 前置条件：
 *   1. 后端 API Server 运行在 http://localhost:8000
 *   2. 前端 dev server 运行在 http://localhost:5173
 *   3. 环境变量：E2E_BASE_URL（可覆盖，默认 http://localhost:5173）
 *
 * 运行命令：
 *   npx playwright test                      # 全量跑
 *   npx playwright test --grep "@smoke"      # 仅冒烟
 *   npx playwright test e2e/test_settings_cleanup.spec.ts  # 单文件
 *
 * 注意事项（既往 E2E 陷阱，参见 memory feedback_e2e_playwright_patterns.md）：
 *   - h1 重复：使用 page.locator('h2') + 精确文本，避免 getByRole('heading', {level:1})
 *   - getByText 多匹配：改用 page.locator('text=xxx').first() 或更精确的选择器
 *   - el-input-number 延迟：输入后等待 page.waitForTimeout(300) 再断言
 *   - el-upload 定位器：通过 input[type=file] 而非上层 .el-upload
 *   - el-image preview：Lightbox 弹层挂载在 body，需 page.locator('body')...
 */
export default defineConfig({
  // Scan both e2e/ (JS-spec tests) and playwright/ (TS-spec tests, e.g. kb.spec.ts).
  // Using testDir: './e2e' alone creates a scan blind-spot for tests under playwright/,
  // which means KB upload regressions can reach production undetected.
  // See: memory/feedback_e2e_playwright_patterns.md — Rule 4
  testMatch: ['**/e2e/**/*.{js,ts}', '**/playwright/**/*.{js,ts}'],
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 2,

  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
    // 测试账号（需在 E2E 环境预先创建）
    storageState: process.env.E2E_STORAGE_STATE || undefined,
  },

  projects: [
    // 认证前置步骤：生成 storage state（登录态），仅执行一次
    {
      name: 'setup',
      testMatch: '**/e2e/auth.setup.ts',
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],

  // 本地开发时自动启动 dev server（CI 中通常已独立启动）
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:5173',
  //   reuseExistingServer: !process.env.CI,
  // },
})
