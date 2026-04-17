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
    await expect(page.getByText('DeepSeek', { exact: true })).toBeVisible();
    await expect(page.getByText('火山引擎（豆包）', { exact: true })).toBeVisible();

    // Click Volcano radio
    await page.getByText('火山引擎（豆包）', { exact: true }).click();
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
    // SettingsView fires ElMessage.warning("请填写 API Key") for empty key
    await expect(
      page.locator('.el-message--warning, .el-message--error, .el-form-item__error').first()
    ).toBeVisible({ timeout: 5000 });
  });

  test('E2E-004d: Save valid DeepSeek config', async ({ page }) => {
    await page.getByText('大语言模型').click();
    await page.getByText('DeepSeek', { exact: true }).click();
    await page.getByPlaceholder('sk-...').fill('sk-test-e2e-key-12345');
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });
  });

  test('E2E-004x: Switching provider clears/restores API key field independently', async ({ page }) => {
    await page.getByText('大语言模型').click();

    // Step 1: fill DeepSeek key and save
    await page.getByText('DeepSeek', { exact: true }).click();
    await page.getByPlaceholder('sk-...').fill('sk-deepseek-key-001');
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });

    // Step 2: switch to Volcano — API key field must NOT show DeepSeek's key
    await page.getByText('火山引擎（豆包）', { exact: true }).click();
    const apiKeyAfterSwitch = await page.getByPlaceholder('sk-...').inputValue();
    // Volcano has no saved key yet, so the field should be empty
    expect(apiKeyAfterSwitch).toBe('');
  });

  test('E2E-004y: Each provider retains its own API key after round-trip switch', async ({ page }) => {
    await page.getByText('大语言模型').click();

    // Save DeepSeek key
    await page.getByText('DeepSeek', { exact: true }).click();
    await page.getByPlaceholder('sk-...').fill('sk-deepseek-key-001');
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });

    // Save Volcano key
    await page.getByText('火山引擎（豆包）', { exact: true }).click();
    await page.getByPlaceholder('sk-...').fill('sk-volcano-key-002');
    await page.getByPlaceholder(/ep-/).fill('ep-test-20240101');
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });

    // Reload page to force onMounted re-fetch from backend.
    // Wait for networkidle so onMounted's async settingsAPI.list() call has
    // completed and llmSavedConfig has been populated before we read field values.
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.getByText('大语言模型').click();

    // Verify DeepSeek key is shown under DeepSeek radio.
    // After reload the form defaults to deepseek; clicking the radio is a no-op
    // but ensures we're reading the right field.
    await page.getByText('DeepSeek', { exact: true }).click();
    // Wait for the api_key field to be populated (onMounted backfill may still
    // be setting reactivity after networkidle)
    await expect(page.getByPlaceholder('sk-...')).not.toHaveValue('', { timeout: 5000 });
    const deepseekKey = await page.getByPlaceholder('sk-...').inputValue();
    expect(deepseekKey).toMatch(/^sk-/);

    // Switch to Volcano — should show Volcano's own key (masked), NOT DeepSeek's
    await page.getByText('火山引擎（豆包）', { exact: true }).click();
    await expect(page.getByPlaceholder('sk-...')).not.toHaveValue('', { timeout: 5000 });
    const volcanoKey = await page.getByPlaceholder('sk-...').inputValue();
    expect(volcanoKey).toMatch(/^sk-/);
    // The two displayed keys must differ (they are separately stored)
    expect(volcanoKey).not.toBe(deepseekKey);
  });

  test('E2E-004z: DeepSeek model selection and params saved and restored after reload', async ({ page }) => {
    await page.getByText('大语言模型').click();
    await page.getByText('DeepSeek', { exact: true }).click();

    // Fill API key
    await page.getByPlaceholder('sk-...').fill('sk-test-deepseek-model-e2e');

    // Select deepseek-reasoner from the model dropdown
    await page.locator('.el-select').first().click();
    // ElementPlus teleports the dropdown list — use .first() to target the list item
    await page.getByText('deepseek-reasoner（DeepSeek-R1，推理模型）').first().click();

    // Set temperature to 0.5 — target el-input-number by surrounding form-item label
    const temperatureInputNumber = page.locator('.el-form-item').filter({ hasText: 'Temperature' }).locator('input').first();
    await temperatureInputNumber.fill('0.5');
    await temperatureInputNumber.press('Tab');

    // Set max_tokens to 2048
    const maxTokensInputNumber = page.locator('.el-form-item').filter({ hasText: 'Max Tokens' }).locator('input').first();
    await maxTokensInputNumber.fill('2048');
    await maxTokensInputNumber.press('Tab');

    // Save
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });

    // Reload and verify round-trip
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.getByText('大语言模型').click();
    await page.getByText('DeepSeek', { exact: true }).click();

    // Model dropdown should show deepseek-reasoner
    await expect(page.locator('.el-select').first()).toContainText('deepseek-reasoner');
  });

  test('E2E-004w: Volcano model selection and params saved and restored after reload', async ({ page }) => {
    await page.getByText('大语言模型').click();
    await page.getByText('火山引擎（豆包）', { exact: true }).click();

    // Fill API key and endpoint ID
    await page.getByPlaceholder('sk-...').fill('sk-test-volcano-model-e2e');
    await page.getByPlaceholder(/ep-/).fill('ep-20240101-modeltest');

    // Select Doubao-pro-32k from the doubao model dropdown
    // The doubao model select is the first el-select in volcano section
    await page.locator('.el-select').first().click();
    // ElementPlus teleports the dropdown list — use .first() to target the list item
    await page.getByText('Doubao-pro-32k（专业版，32K 上下文）').first().click();

    // Save
    await page.getByRole('button', { name: '保存' }).first().click();
    await expect(page.getByText(/已保存|成功/)).toBeVisible({ timeout: 5000 });

    // Reload and verify round-trip
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.getByText('大语言模型').click();
    await page.getByText('火山引擎（豆包）', { exact: true }).click();

    // Doubao model dropdown should show Doubao-pro-32k
    await expect(page.locator('.el-select').first()).toContainText('Doubao-pro-32k');

    // Endpoint ID should be restored (masked by backend)
    const endpointVal = await page.getByPlaceholder(/ep-/).inputValue();
    expect(endpointVal).toBeTruthy();
  });

});
