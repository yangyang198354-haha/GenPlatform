/**
 * E2E：AI 图片页面布局（US-06）
 *
 * AC-06-1：浏览器视口 ≥ 1200px 时，左侧"生成设置"面板宽度 ≥ 460px
 * AC-06-2：面板中可见"图片尺寸"区块，含三种输入方式切换控件
 * AC-06-3：浏览器视口 ≤ 900px 时，生成设置面板改为单列布局
 *
 * 注意（既往 E2E 陷阱）：
 *   - h2 重复：页面中只有一个 h2="AI 图片生成"，直接定位即可
 *   - getBoundingClientRect 需在页面稳定（动画完成）后调用
 */
import { test, expect } from '@playwright/test'

test.describe('US-06 — AI 图片页面布局优化', () => {

  /**
   * AC-06-1：面板宽度 ≥ 460px（视口 ≥ 1200px）
   *
   * Given：浏览器视口宽度 ≥ 1200px
   * When：打开 AI 图片生成页面
   * Then：左侧"生成设置"面板宽度 ≥ 460px，所有参数控件完整显示无截断
   */
  test('AC-06-1: 宽视口下左侧面板宽度 ≥ 460px', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/image-generator')
    await page.locator('h2:text-is("AI 图片生成")').waitFor({ state: 'visible' })

    // 等待"生成图片" Tab 内容完全渲染
    await page.locator('.input-panel').waitFor({ state: 'visible' })

    const panelWidth = await page.locator('.input-panel').evaluate(
      (el) => el.getBoundingClientRect().width
    )
    expect(panelWidth, `面板宽度应 ≥ 460px，实际: ${panelWidth}px`).toBeGreaterThanOrEqual(460)
  })

  /**
   * AC-06-2：面板中可见"图片尺寸"区块，含三种模式切换
   *
   * Given：用户打开 AI 图片生成页面
   * When：查看"生成设置"面板
   * Then：面板中可见"图片尺寸"区块，含三种输入方式（精确像素 / 档位 / 比例）的切换控件
   */
  test('AC-06-2: 图片尺寸区块和三种模式切换控件存在', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/image-generator')
    await page.locator('.input-panel').waitFor({ state: 'visible' })

    // "图片尺寸" label
    await expect(page.locator('.size-selector .field-label:text-is("图片尺寸")')).toBeVisible()

    // 三种模式 Radio Button（通过 .el-radio-button__inner 的精确文本）
    await expect(page.locator('.size-selector .el-radio-button__inner:text-is("精确像素")')).toBeVisible()
    await expect(page.locator('.size-selector .el-radio-button__inner:text-is("档位")')).toBeVisible()
    await expect(page.locator('.size-selector .el-radio-button__inner:text-is("比例")')).toBeVisible()
  })

  /**
   * AC-06-2 补充：生成模式 Radio Group 存在
   *
   * Given：用户打开 AI 图片生成页面
   * When：查看"生成设置"面板
   * Then：面板中可见"生成模式" Radio Group，含主图×1 / 多图×2/3/4 四个选项
   */
  test('AC-06-2 补充: 生成模式 Radio Group 四个选项均可见', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/image-generator')
    await page.locator('.input-panel').waitFor({ state: 'visible' })

    const modeSelector = page.locator('.generation-mode-selector')
    await expect(modeSelector).toBeVisible()

    // 四个 Radio Button
    await expect(modeSelector.locator('.el-radio-button__inner:text-is("主图 ×1")')).toBeVisible()
    await expect(modeSelector.locator('.el-radio-button__inner:text-is("多图 ×2")')).toBeVisible()
    await expect(modeSelector.locator('.el-radio-button__inner:text-is("多图 ×3")')).toBeVisible()
    await expect(modeSelector.locator('.el-radio-button__inner:text-is("多图 ×4")')).toBeVisible()
  })

  /**
   * AC-06-3：小视口下单列布局，无横向溢出
   *
   * Given：浏览器视口宽度 ≤ 900px
   * When：打开 AI 图片生成页面
   * Then：生成设置与结果面板改为单列布局，参数面板无横向溢出
   */
  test('AC-06-3: 小视口（≤900px）下单列布局，无横向溢出', async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 900 })
    await page.goto('/image-generator')
    await page.locator('.generator-layout').waitFor({ state: 'visible' })

    // 在小视口下，.input-panel 宽度应 ≤ 视口宽度（无横向溢出）
    const panelWidth = await page.locator('.input-panel').evaluate(
      (el) => el.getBoundingClientRect().width
    )
    expect(panelWidth, `小视口下面板不应溢出视口，实际宽度: ${panelWidth}px`).toBeLessThanOrEqual(800)

    // 生成结果面板也在视口内（单列布局时，两面板上下排列）
    const resultPanel = page.locator('.result-panel')
    if (await resultPanel.isVisible()) {
      const resultLeft = await resultPanel.evaluate(
        (el) => el.getBoundingClientRect().left
      )
      // 单列布局：result-panel 的 left 应接近 0（与 input-panel 同列）
      expect(resultLeft, '单列布局下 result-panel left 应接近 0').toBeLessThanOrEqual(50)
    }
  })
})
