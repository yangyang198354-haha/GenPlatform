/**
 * E2E：AI 图片尺寸三模式 UI（US-01 / US-02 / US-03）
 *
 * 注意：US-01 AC-01-2（API 级 400 拒绝）和 US-02/03 的具体像素映射值
 *       由 backend unit test（test_serializers.py）覆盖，E2E 只验证 UI 行为：
 *       - pixel 模式：下拉选择后，请求体含正确 size 字符串
 *       - tier 模式：点击档位后，mode/tier 字段正确
 *       - ratio 模式：比例 + 档位选择后，出现预计尺寸预览文字
 *
 * 测试策略：
 *   - 拦截 POST /api/v1/image/generate/ 请求验证参数
 *   - 比例模式不提交，只验证预览文字（避免触发真实 API）
 *
 * 既往 E2E 陷阱：
 *   - el-select 下拉挂载在 body：用 page.locator，不用 el 容器的 locator
 *   - el-radio-button 选中用 :text-is() 精确匹配，避免 getByText 多匹配
 */
import { test, expect } from '@playwright/test'

const API_GENERATE = '**/api/v1/image/generate/**'

test.describe('US-01/02/03 — 图片尺寸三模式 UI', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/image-generator')
    await page.locator('h2:text-is("AI 图片生成")').waitFor({ state: 'visible' })
    await page.locator('.size-selector').waitFor({ state: 'visible' })
  })

  // ── US-01：精确像素模式 ──────────────────────────────────────────────────────

  /**
   * AC-01-1（UI 层）：pixel 模式下选择 2880x1620，提交请求含 size_mode=pixel，size=2880x1620
   *
   * Given：用户选择尺寸输入方式"精确像素"
   * When：从下拉列表选择 2880x1620，点击"开始生成"
   * Then：请求体含 size_mode=pixel, size=2880x1620（或归一化后等价值）
   */
  test('AC-01-1: pixel 模式选择 2880x1620 后请求含正确 size', async ({ page }) => {
    let capturedPostData: string | null = null

    await page.route(API_GENERATE, async (route) => {
      capturedPostData = route.request().postData()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ batch_id: 'mock', batch_name: 'Mock', n: 1, status: 'pending', ws_token: 'tok' }),
      })
    })

    // 确认当前模式为"精确像素"（默认）
    const sizeSelector = page.locator('.size-selector')
    const pixelBtn = sizeSelector.locator('.el-radio-button__inner:text-is("精确像素")')
    await pixelBtn.click()

    // 点击 el-select 触发器（pixel 模式下可见的下拉）
    await sizeSelector.locator('.el-select .el-input__wrapper').click()

    // 等待下拉弹层出现（弹层挂载在 body，用 page.locator）
    await page.locator('.el-select-dropdown__item').first().waitFor({ state: 'visible' })

    // 选择 2880x1620 选项（精确文本匹配，避免多匹配）
    await page.locator('.el-select-dropdown__item').filter({ hasText: '2880×1620' }).first().click()

    // 填入提示词并提交
    await page.locator('textarea[placeholder*="提示词"]').fill('pixel 模式测试提示词')
    await page.locator('button:has-text("开始生成")').click()
    await page.waitForTimeout(500)

    // 验证请求体含 2880x1620
    expect(capturedPostData, '请求体不应为空').toBeTruthy()
    expect(capturedPostData!, '请求体应含 size=2880x1620').toContain('2880x1620')
  })

  /**
   * US-01 补充：pixel 模式默认值显示正确（2048x2048）
   */
  test('pixel 模式默认选项为 2048x2048', async ({ page }) => {
    const sizeSelector = page.locator('.size-selector')

    // 确保在 pixel 模式
    await sizeSelector.locator('.el-radio-button__inner:text-is("精确像素")').click()

    // el-select 显示的当前值
    const selectInput = sizeSelector.locator('.el-select .el-input__inner')
    const inputValue = await selectInput.inputValue()
    expect(inputValue, '默认应为 2048x2048').toBe('2048x2048')
  })

  // ── US-02：档位模式 ──────────────────────────────────────────────────────────

  /**
   * AC-02-1（UI 层）：tier 模式选择 2K 后请求含 size_mode=tier, size_tier=2K
   *
   * Given：用户选择尺寸方式"档位"，选择档位"2K"
   * When：点击"开始生成"
   * Then：请求体含 size_mode=tier, size_tier=2K
   */
  test('AC-02-1: tier 模式选择 2K 请求参数正确', async ({ page }) => {
    let capturedPostData: string | null = null

    await page.route(API_GENERATE, async (route) => {
      capturedPostData = route.request().postData()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ batch_id: 'mock', batch_name: 'Mock', n: 1, status: 'pending', ws_token: 'tok' }),
      })
    })

    const sizeSelector = page.locator('.size-selector')

    // 切换到档位模式
    await sizeSelector.locator('.el-radio-button__inner:text-is("档位")').click()

    // 等待档位 Radio Group 出现
    await sizeSelector.locator('.tier-radio').waitFor({ state: 'visible' })

    // 选择 2K
    await sizeSelector.locator('.tier-radio .el-radio-button__inner:text-is("2K（约 4 MP）")').click()

    // 填入提示词并提交
    await page.locator('textarea[placeholder*="提示词"]').fill('tier 模式测试提示词')
    await page.locator('button:has-text("开始生成")').click()
    await page.waitForTimeout(500)

    // 验证请求体含 size_mode=tier 和 size_tier=2K
    expect(capturedPostData!, '请求体应含 size_mode=tier').toContain('tier')
    expect(capturedPostData!, '请求体应含 size_tier=2K 或 2K').toContain('2K')
  })

  /**
   * AC-02-2（UI 层）：tier 模式选择 4K 后请求含 4K 参数
   */
  test('AC-02-2: tier 模式选择 4K 请求参数正确', async ({ page }) => {
    let capturedPostData: string | null = null

    await page.route(API_GENERATE, async (route) => {
      capturedPostData = route.request().postData()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ batch_id: 'mock', batch_name: 'Mock', n: 1, status: 'pending', ws_token: 'tok' }),
      })
    })

    const sizeSelector = page.locator('.size-selector')
    await sizeSelector.locator('.el-radio-button__inner:text-is("档位")').click()
    await sizeSelector.locator('.tier-radio').waitFor({ state: 'visible' })
    await sizeSelector.locator('.tier-radio .el-radio-button__inner:text-is("4K（约 17 MP）")').click()

    await page.locator('textarea[placeholder*="提示词"]').fill('4K tier 测试')
    await page.locator('button:has-text("开始生成")').click()
    await page.waitForTimeout(500)

    expect(capturedPostData!, '请求体应含 4K').toContain('4K')
  })

  // ── US-03：比例×档位模式 ─────────────────────────────────────────────────────

  /**
   * AC-03-1（UI 层）：ratio 模式选择 9:16 × 默认 2K，预览尺寸为 1620×2880
   *
   * Given：用户选择尺寸方式"比例"，选择 9:16，档位保持默认 2K
   * When：查看预计尺寸预览
   * Then：预览显示 1620×2880（与 RATIO_TIER_MAP 一致）
   */
  test('AC-03-1: ratio 模式 9:16 × 2K 预览为 1620×2880', async ({ page }) => {
    const sizeSelector = page.locator('.size-selector')

    // 切换到比例模式
    await sizeSelector.locator('.el-radio-button__inner:text-is("比例")').click()
    await sizeSelector.locator('.ratio-radio').waitFor({ state: 'visible' })

    // 选择 9:16
    await sizeSelector.locator('.ratio-radio .el-radio-button__inner:text-is("9:16")').click()

    // 档位保持默认 2K（检查 .tier-section 中 2K 被选中）
    const tierSection = sizeSelector.locator('.tier-section .tier-radio')
    const activeTier = await tierSection.locator('.el-radio-button.is-active .el-radio-button__inner').textContent()
    expect(activeTier?.trim(), '默认档位应为 2K').toBe('2K')

    // 验证预计尺寸预览文字
    const preview = sizeSelector.locator('.preview-hint')
    await expect(preview).toContainText('1620×2880')
  })

  /**
   * AC-03-2（UI 层）：ratio 模式 4:3 × 2K 预览为 2880×2160
   */
  test('AC-03-2: ratio 模式 4:3 × 2K 预览为 2880×2160', async ({ page }) => {
    const sizeSelector = page.locator('.size-selector')
    await sizeSelector.locator('.el-radio-button__inner:text-is("比例")').click()
    await sizeSelector.locator('.ratio-radio').waitFor({ state: 'visible' })
    await sizeSelector.locator('.ratio-radio .el-radio-button__inner:text-is("4:3")').click()

    const preview = sizeSelector.locator('.preview-hint')
    await expect(preview).toContainText('2880×2160')
  })

  /**
   * AC-03-3（UI 层）：ratio 模式 16:9 × 4K 预览为 4096×2304
   */
  test('AC-03-3: ratio 模式 16:9 × 4K 预览为 4096×2304', async ({ page }) => {
    const sizeSelector = page.locator('.size-selector')
    await sizeSelector.locator('.el-radio-button__inner:text-is("比例")').click()
    await sizeSelector.locator('.ratio-radio').waitFor({ state: 'visible' })

    // 选择 16:9
    await sizeSelector.locator('.ratio-radio .el-radio-button__inner:text-is("16:9")').click()

    // 选择 4K
    const tierSection = sizeSelector.locator('.tier-section .tier-radio')
    await tierSection.locator('.el-radio-button__inner:text-is("4K")').click()

    const preview = sizeSelector.locator('.preview-hint')
    await expect(preview).toContainText('4096×2304')
  })

  /**
   * AC-03-4（UI 层）：ratio 模式 9:16 × 3K 预览为 2160×3840
   */
  test('AC-03-4: ratio 模式 9:16 × 3K 预览为 2160×3840', async ({ page }) => {
    const sizeSelector = page.locator('.size-selector')
    await sizeSelector.locator('.el-radio-button__inner:text-is("比例")').click()
    await sizeSelector.locator('.ratio-radio').waitFor({ state: 'visible' })

    await sizeSelector.locator('.ratio-radio .el-radio-button__inner:text-is("9:16")').click()
    const tierSection = sizeSelector.locator('.tier-section .tier-radio')
    await tierSection.locator('.el-radio-button__inner:text-is("3K")').click()

    const preview = sizeSelector.locator('.preview-hint')
    await expect(preview).toContainText('2160×3840')
  })

  /**
   * US-03 补充：切换模式时控件正确显示/隐藏
   */
  test('切换模式时子控件正确显示/隐藏', async ({ page }) => {
    const sizeSelector = page.locator('.size-selector')

    // pixel 模式：显示 el-select，不显示 tier-radio 或 ratio-radio
    await sizeSelector.locator('.el-radio-button__inner:text-is("精确像素")').click()
    await expect(sizeSelector.locator('.el-select')).toBeVisible()
    await expect(sizeSelector.locator('.ratio-radio')).not.toBeVisible()

    // tier 模式：显示 tier-radio（含"2K（约 4 MP）"），不显示 el-select 和 ratio-radio
    await sizeSelector.locator('.el-radio-button__inner:text-is("档位")').click()
    await expect(sizeSelector.locator('.tier-radio')).toBeVisible()
    await expect(sizeSelector.locator('.el-select')).not.toBeVisible()

    // ratio 模式：显示 ratio-radio 和 tier-section
    await sizeSelector.locator('.el-radio-button__inner:text-is("比例")').click()
    await expect(sizeSelector.locator('.ratio-radio')).toBeVisible()
    await expect(sizeSelector.locator('.tier-section')).toBeVisible()
    await expect(sizeSelector.locator('.el-select')).not.toBeVisible()
  })
})
