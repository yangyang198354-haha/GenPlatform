/**
 * E2E-02: Knowledge base
 * Covers US-002 (upload), US-003 (list, search, delete).
 */
import { test, expect } from '@playwright/test';
import { uniqueEmail, registerAndLogin } from './helpers.js';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test.describe('Knowledge Base', () => {

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/knowledge-base');
  });

  test('E2E-002a: Knowledge base page loads with empty state', async ({ page }) => {
    await expect(page.getByText('知识库')).toBeVisible();
    await expect(page.getByRole('button', { name: /上传文档/ })).toBeVisible();
  });

  test('E2E-002b: Upload dialog opens on button click', async ({ page }) => {
    await page.getByRole('button', { name: /上传文档/ }).click();
    await expect(page.getByText('上传文档').nth(1)).toBeVisible();
    await expect(page.getByText(/拖拽文件|点击上传/)).toBeVisible();
  });

  test('E2E-002c: Upload a text document', async ({ page }) => {
    // Create a small temp txt file to upload
    await page.getByRole('button', { name: /上传文档/ }).click();

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test_doc.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('This is a test document for E2E testing of the knowledge base upload feature.'),
    });

    // Should show success message and close dialog
    await expect(page.getByText(/上传成功|处理/)).toBeVisible({ timeout: 10_000 });
    // Document should appear in table
    await expect(page.getByText('test_doc.txt')).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-002d: Search filters document list', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/搜索文档/);
    await searchInput.fill('nonexistent_document_xyz');
    await page.waitForTimeout(500);
    // Table should be empty or show no results
    const rows = page.locator('.el-table__row');
    await expect(rows).toHaveCount(0, { timeout: 5000 });
  });

});
