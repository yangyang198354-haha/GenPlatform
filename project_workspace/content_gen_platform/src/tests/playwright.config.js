// @ts-check
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  // Include both the legacy e2e/ directory (JS specs) and the newer
  // playwright/ directory (TypeScript specs such as kb.spec.ts).
  // Previously only './e2e' was listed, so kb.spec.ts was never executed.
  testDir: '.',
  testMatch: ['e2e/**/*.spec.{js,ts}', 'playwright/**/*.spec.{js,ts}'],
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['json', { outputFile: 'playwright-results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost',
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
