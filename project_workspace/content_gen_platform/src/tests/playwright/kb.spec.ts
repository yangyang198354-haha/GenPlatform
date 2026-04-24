/**
 * Playwright E2E — Knowledge Base extension
 *
 * Covers:
 *   1. Page visibility after login
 *   2. "上传目录" button presence
 *   3. Single-file upload flow (via file input mock)
 *   4. Document rename flow
 *   5. User isolation — documents uploaded by user_a are invisible to user_b
 *
 * Prerequisites:
 *   - Dev server running at BASE_URL (default http://localhost:5173)
 *   - Django backend running at http://localhost:8000
 */

import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _counter = 0;

/**
 * Include process.pid so that when workers=2 in CI each Playwright worker
 * process (different pids) generates distinct emails even at the same timestamp.
 */
function uniqueEmail(): string {
  return `kb_e2e_${process.pid}_${Date.now()}_${++_counter}@test.internal`;
}

async function registerAndLogin(
  page: Page,
  email: string,
  password = 'E2eTest123!',
): Promise<void> {
  await page.goto('/register');
  // Username field
  await page.getByPlaceholder(/至少 2 个字符/).fill(email.split('@')[0]);
  await page.getByPlaceholder(/your@email\.com/).fill(email);
  await page.getByPlaceholder(/至少 8 位/).fill(password);
  await page.getByPlaceholder(/再次输入/).fill(password);
  await page.getByRole('button', { name: /创建账号/ }).click();
  // Registration redirects to login
  await page.waitForURL(/\/login/);
  await page.getByPlaceholder(/your@email\.com/).fill(email);
  await page.getByPlaceholder(/输入密码/).fill(password);
  await page.getByRole('button', { name: /登录/ }).click();
  await page.waitForURL(/\/(workspace|knowledge)/);
}

async function loginExisting(
  page: Page,
  email: string,
  password = 'E2eTest123!',
): Promise<void> {
  await page.goto('/login');
  await page.getByPlaceholder(/your@email\.com/).fill(email);
  await page.getByPlaceholder(/输入密码/).fill(password);
  await page.getByRole('button', { name: /登录/ }).click();
  await page.waitForURL(/\/(workspace|knowledge)/);
}

async function logout(page: Page): Promise<void> {
  // Try a logout button / link; fall back to clearing storage
  const logoutBtn = page.getByRole('button', { name: /退出|注销|Logout/i });
  if (await logoutBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await logoutBtn.click();
    await page.waitForURL(/\/login/, { timeout: 5_000 });
  } else {
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.goto('/login');
  }
}

// ---------------------------------------------------------------------------
// Scenario 1 — Page visibility after login
// ---------------------------------------------------------------------------

test.describe('KB-01: 用户登录后可见知识库页面', () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
  });

  test('知识库页面标题/heading 可见', async ({ page }) => {
    await page.goto('/knowledge-base');
    // Allow both h1 and h2 since the view uses h2
    const heading = page.locator('h1, h2').filter({ hasText: /知识库/ });
    await expect(heading.first()).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 2 — "上传目录" button presence
// ---------------------------------------------------------------------------

test.describe('KB-02: 上传目录按钮存在', () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/knowledge-base');
  });

  test('"上传目录" 按钮出现在页面上', async ({ page }) => {
    const dirBtn = page.getByRole('button', { name: /上传目录/ });
    await expect(dirBtn).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 3 — Single-file upload flow
// ---------------------------------------------------------------------------

test.describe('KB-03: 单文件上传流程', () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/knowledge-base');
  });

  test('上传 TXT 文件后文档出现在列表中', async ({ page }) => {
    // Open upload dialog
    await page.getByRole('button', { name: /上传文档/ }).click();

    // The page has TWO input[type="file"] elements: one inside the el-upload
    // dialog and one hidden directory picker (webkitdirectory) outside the dialog.
    // Scope to [role="dialog"] to avoid accidentally targeting the directory picker,
    // which would fail silently (file never actually uploaded).
    const fileInput = page.locator('[role="dialog"] input[type="file"]').first();

    await fileInput.setInputFiles({
      name: 'e2e_test_upload.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from(
        'This is an E2E test document for the knowledge base upload feature.',
      ),
    });

    // Wait for success feedback
    await expect(
      page.getByText(/上传成功|处理中|已上传/),
    ).toBeVisible({ timeout: 15_000 });

    // Close dialog if still open
    const closeBtn = page.getByRole('button', { name: /关闭|取消/ }).last();
    if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await closeBtn.click();
    }

    // The document name must appear in the table
    await expect(
      page.getByRole('cell', { name: /e2e_test_upload/ }),
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 4 — Document rename
// ---------------------------------------------------------------------------

test.describe('KB-04: 文档重命名', () => {
  const originalName = 'rename_test_doc.txt';
  const newName = '已重命名文档';

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/knowledge-base');

    // Upload a document first so there is something to rename.
    // Scope to [role="dialog"] to avoid selecting the hidden directory picker
    // (webkitdirectory input) that also lives on the page.
    await page.getByRole('button', { name: /上传文档/ }).click();
    const fileInput = page.locator('[role="dialog"] input[type="file"]').first();
    await fileInput.setInputFiles({
      name: originalName,
      mimeType: 'text/plain',
      buffer: Buffer.from('Rename test content.'),
    });
    await expect(
      page.getByText(/上传成功|处理中|已上传/),
    ).toBeVisible({ timeout: 15_000 });

    // Close dialog
    const closeBtn = page.getByRole('button', { name: /关闭|取消/ }).last();
    if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await closeBtn.click();
    }
  });

  test('点击重命名按钮，输入新名称，列表中显示新名称', async ({ page }) => {
    // Find the rename (edit-pen) button in the row containing originalName
    const row = page.locator('.el-table__row').filter({ hasText: originalName });
    await expect(row).toBeVisible({ timeout: 10_000 });

    // The rename button has title="重命名"
    await row.getByTitle('重命名').click();

    // Rename dialog should open
    const renameDialog = page.getByRole('dialog', { name: /重命名/ });
    await expect(renameDialog).toBeVisible({ timeout: 5_000 });

    // Clear existing value and type new name
    const renameInput = renameDialog.getByRole('textbox');
    await renameInput.clear();
    await renameInput.fill(newName);

    // Confirm
    await renameDialog.getByRole('button', { name: /确认/ }).click();

    // Dialog closes and new name appears in table
    await expect(renameDialog).not.toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByRole('cell', { name: newName }),
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 5 — User isolation
// ---------------------------------------------------------------------------

test.describe('KB-05: 用户隔离验证', () => {
  test(
    'user_a 上传的文档在 user_b 的知识库列表中不可见',
    async ({ page }) => {
      const emailA = uniqueEmail();
      const emailB = uniqueEmail();
      const docName = `user_a_private_${Date.now()}.txt`;

      // --- user_a: register, login, upload ---
      await registerAndLogin(page, emailA);
      await page.goto('/knowledge-base');

      await page.getByRole('button', { name: /上传文档/ }).click();
      // Scope to dialog to avoid the hidden webkitdirectory picker
      const fileInput = page.locator('[role="dialog"] input[type="file"]').first();
      await fileInput.setInputFiles({
        name: docName,
        mimeType: 'text/plain',
        buffer: Buffer.from('User A private document content.'),
      });
      await expect(
        page.getByText(/上传成功|处理中|已上传/),
      ).toBeVisible({ timeout: 15_000 });

      // Confirm document appears for user_a
      const closeBtn = page.getByRole('button', { name: /关闭|取消/ }).last();
      if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await closeBtn.click();
      }
      await expect(
        page.getByRole('cell', { name: new RegExp(docName) }),
      ).toBeVisible({ timeout: 10_000 });

      // --- Logout user_a ---
      await logout(page);

      // --- user_b: register, login, check KB ---
      await registerAndLogin(page, emailB);
      await page.goto('/knowledge-base');

      // user_b should see an empty list (or at least NOT see user_a's document)
      await page.waitForTimeout(1_500); // Let the list load
      const cellA = page.getByRole('cell', { name: new RegExp(docName) });
      await expect(cellA).not.toBeVisible();
    },
  );
});
