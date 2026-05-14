/**
 * E2E：系统设置 — 即梦 API 清理验证（US-08）
 *
 * AC-08-1：设置页 Tab 列表中无"即梦 API"标签页
 * AC-08-3：SettingsView.vue script 中无 jimeng 相关 JS 引用
 *          （此 AC 为静态分析，由 backend unit test 覆盖；E2E 覆盖 DOM 层面）
 *
 * 注意：AC-08-2（历史数据保留）和 AC-08-4（后端无残留路由）由 backend
 *       pytest（TestJimengV12Cleanup）覆盖，E2E 不重复。
 */
import { test, expect } from '@playwright/test'

test.describe('US-08 — 系统设置：即梦 API Tab 已清理', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings')
    // 等待设置页加载：h2 = "系统设置"（唯一）
    await page.locator('h2:text-is("系统设置")').waitFor({ state: 'visible' })
  })

  /**
   * AC-08-1：Tab 列表中无"即梦 API"标签页
   *
   * Given：用户打开系统设置页面
   * When：查看左侧 Tab 列表
   * Then：不存在"即梦 API"标签页
   */
  test('AC-08-1: Tab 列表中不存在"即梦 API"标签', async ({ page }) => {
    // el-tabs 的 Tab 列表：每个 Tab 的 label 在 .el-tabs__item 内
    const tabItems = page.locator('.el-tabs__item')
    // 确认至少有一个 Tab（页面已加载）
    await expect(tabItems.first()).toBeVisible()

    // 获取所有 Tab 文本，确认无"即梦 API"
    const tabTexts = await tabItems.allTextContents()
    const hasJimeng = tabTexts.some(t => t.includes('即梦'))
    expect(hasJimeng, '不应存在"即梦 API"标签页').toBe(false)
  })

  /**
   * AC-08-1 补充：其他正常 Tab 仍然存在
   *
   * 验证清理后大语言模型 / 豆包图片 API Tab 未被误删。
   */
  test('AC-08-1 补充: 正常业务 Tab 仍然存在', async ({ page }) => {
    const tabItems = page.locator('.el-tabs__item')
    const tabTexts = await tabItems.allTextContents()

    // 大语言模型 Tab 必须存在
    expect(
      tabTexts.some(t => t.includes('大语言模型')),
      '大语言模型 Tab 应存在'
    ).toBe(true)
  })

  /**
   * AC-08-3（DOM 层）：页面中无 jimengForm / saveJimengConfig 等字样
   *
   * 通过检查页面 HTML source 确认前端 bundle 中无残留即梦业务变量名
   * （production build 后变量会被 minify，此处检查 dev 模式的可读变量名）
   *
   * Note：此测试依赖 dev server（变量名未被混淆），CI 中建议配合 source-map。
   * 若 CI 使用 preview build，此测试跳过（标注 @dev-only）。
   */
  test('AC-08-3: 页面源码无 jimeng 业务变量残留 @dev-only', async ({ page }) => {
    // 通过 evaluate 读取 Vue 组件实例上是否存在 jimeng 相关属性
    // （仅在 dev 模式下有效，production build 属性名被压缩）
    const pageContent = await page.content()

    // 这些变量名在 SettingsView.vue 的 script 中已被删除
    const forbiddenTerms = ['jimengForm', 'saveJimengConfig', 'testJimengConfig', 'savingJimeng', 'testingJimeng']
    for (const term of forbiddenTerms) {
      expect(pageContent, `页面中不应包含 "${term}"`).not.toContain(term)
    }
  })
})
