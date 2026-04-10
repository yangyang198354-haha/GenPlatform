/**
 * E2E-01: Authentication flows
 * Covers US-001 (register, login, logout).
 */
import { test, expect } from '@playwright/test';
import { uniqueEmail, registerAndLogin } from './helpers.js';

test.describe('Authentication', () => {

  test('E2E-001a: Register new user and reach workspace', async ({ page }) => {
    const email = uniqueEmail();
    await registerAndLogin(page, email);
    await expect(page).toHaveURL(/\/(workspace|knowledge)/);
    // Sidebar should be visible
    await expect(page.getByText('内容生成平台')).toBeVisible();
  });

  test('E2E-001b: Login redirects guest to login page', async ({ page }) => {
    await page.goto('/workspace');
    await expect(page).toHaveURL(/\/login/);
  });

  test('E2E-001c: Invalid credentials show error', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder(/your@email\.com/).fill('nobody@example.com');
    await page.getByPlaceholder(/输入密码/).fill('WrongPassword!');
    await page.getByRole('button', { name: /登录/ }).click();
    // Should stay on login and show error
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('.el-message--error, [class*="error"]').first()).toBeVisible({ timeout: 5000 });
  });

  test('E2E-001d: Logout clears session and redirects to login', async ({ page }) => {
    const email = uniqueEmail();
    await registerAndLogin(page, email);
    // Click the user avatar to open dropdown
    await page.locator('.avatar-trigger').click();
    await page.getByText('退出登录').click();
    await expect(page).toHaveURL(/\/login/);
    // Navigating to workspace should redirect back to login
    await page.goto('/workspace');
    await expect(page).toHaveURL(/\/login/);
  });

});
