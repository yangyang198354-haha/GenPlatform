/**
 * E2E-04: System settings
 * Covers US-004 (LLM config), US-013 (Jimeng config).
 */
import { test, expect } from '@playwright/test';
import { uniqueEmail, registerAndLogin } from './helpers.js';

test.describe('System Settings', () => {

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/settings');
  });

  test('E2E-004a: Settings page shows LLM and Jimeng tabs', async ({ page }) => {
    // Use h1 to avoid strict-mode collision with nav sidebar text
    await expect(page.locator('h1').filter({ hasText: '系统设置' })).toBeVisible();
    await expect(page.getByText('大语言模型')).toBeVisible();
    await expect(page.getByText('即梦 API')).toBeVisible();
    await expect(page.getByText('存储设置')).toBeVisible();
  });

  test('E2E-004b: LLM provider radio buttons work (no deprecation warning)', async ({ page }) => {
    // Listen for console errors (deprecation warnings would appear here)
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        consoleErrors.push(msg.text());
      }
    });

    await page.getByText('大语言模型').click();
    // Both radio options should be visible and selectable
    await expect(page.getByText('DeepSeek')).toBeVisible();
    await expect(page.getByText('火山引擎')).toBeVisible();

    // Click Volcano radio
    await page.getByText('火山引擎（豆包）').click();
    // Model ID field should appear
    await expect(page.getByPlaceholder(/ep-/)).toBeVisible();

    // No el-radio deprecation error
    const radioError = consoleErrors.find(e => e.includes('el-radio') && e.includes('deprecated'));
    expect(radioError).toBeUndefined();
  });

  test('E2E-004c: Save LLM config with missing fields shows error', async ({ page }) => {
    await page.getByText('大语言模型').click();
    // Clear API key and try to save
    const apiKeyInput = page.getByPlaceholder('sk-...');
    await apiKeyInput.fill('');
    await page.getByRole('button', { name: '保存' }).first().click();
    // ElementPlus shows inline form validation errors (.el-form-item__error) or toast
    await expect(
      page.locator('.el-form-item__error, .el-message--error').first()
    ).toBeVisible({ timeout: 5000 });
  });

  test('E2E-004d: Save valid DeepSeek config', async ({ page }) => {
    await page.getByText('大语言模型').click();
    await page.getByText('DeepSeek').click();
    await page.getByPlaceholder('sk-...').fill('sk-test-e2e-key-12345');
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });
  });

});
