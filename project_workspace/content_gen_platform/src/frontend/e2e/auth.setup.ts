/**
 * E2E 认证前置步骤（auth.setup.ts）
 *
 * 在所有 E2E 测试开始前执行一次登录，将登录态（Cookie / localStorage）
 * 保存为 e2e/.auth/user.json，后续测试直接复用，不重复登录。
 *
 * 环境变量：
 *   E2E_USERNAME  — 测试账号用户名（默认 e2e_user）
 *   E2E_PASSWORD  — 测试账号密码（默认 e2e_pass_123）
 */
import { test as setup, expect } from '@playwright/test'
import path from 'path'

const AUTH_FILE = path.join(__dirname, '.auth/user.json')

const E2E_USERNAME = process.env.E2E_USERNAME || 'e2e_user'
const E2E_PASSWORD = process.env.E2E_PASSWORD || 'e2e_pass_123'

setup('authenticate', async ({ page }) => {
  await page.goto('/login')

  // 等待登录表单出现（避免 h1 重复陷阱：用精确 label 而非 heading 角色）
  await page.locator('input[placeholder*="用户名"], input[name="username"]').fill(E2E_USERNAME)
  await page.locator('input[type="password"]').fill(E2E_PASSWORD)
  await page.locator('button[type="submit"], .login-btn').click()

  // 登录成功后跳转到工作台，等待路由稳定
  await page.waitForURL('**/workspace', { timeout: 10_000 })
  await expect(page.locator('h2').first()).toBeVisible()

  // 保存登录态供后续测试复用
  await page.context().storageState({ path: AUTH_FILE })
})
