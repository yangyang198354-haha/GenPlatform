import { defineConfig, devices } from '@playwright/test';

/**
 * Root-level Playwright configuration for TypeScript E2E tests.
 * Test files live under:
 *   project_workspace/content_gen_platform/src/tests/playwright/
 *
 * Run with:
 *   npx playwright test --config=playwright.config.ts
 */
export default defineConfig({
  testDir: './project_workspace/content_gen_platform/src/tests/playwright',
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['json', { outputFile: 'playwright-results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
