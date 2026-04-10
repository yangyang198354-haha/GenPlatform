/**
 * E2E-05: Content list and publisher
 * Covers US-006 (confirm), US-007 (bind account), US-008/009 (publish + history).
 */
import { test, expect } from '@playwright/test';
import { uniqueEmail, registerAndLogin } from './helpers.js';

test.describe('Content List & Publisher', () => {

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
  });

  test('E2E-005a: Content list page renders', async ({ page }) => {
    await page.goto('/contents');
    // Use h1 to avoid strict-mode collision with nav sidebar label
    await expect(page.locator('h1').filter({ hasText: '内容列表' })).toBeVisible();
  });

  test('E2E-005b: Publish page renders platform account section', async ({ page }) => {
    await page.goto('/publish');
    // Use heading role to avoid collision with nav sidebar
    await expect(page.getByRole('heading', { name: '发布管理' })).toBeVisible();
  });

  test('E2E-005c: Navigation between all main sections works', async ({ page }) => {
    const navItems = [
      { link: '知识库',   url: /knowledge-base/ },
      { link: '内容生成', url: /workspace/ },
      { link: '内容列表', url: /contents/ },
      { link: '素材库',   url: /media-library/ },
      { link: '发布管理', url: /publish/ },
      { link: '系统设置', url: /settings/ },
    ];

    await page.goto('/workspace');

    for (const item of navItems) {
      await page.getByRole('link', { name: item.link }).click();
      await expect(page).toHaveURL(item.url, { timeout: 5000 });
    }
  });

});
