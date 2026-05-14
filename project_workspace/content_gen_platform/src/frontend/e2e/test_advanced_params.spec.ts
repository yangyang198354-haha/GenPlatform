/**
 * E2E：高级参数配置（US-04）
 *
 * AC-04-1：seed 填入后，请求体含 seed 字段（Canary 参数传递验证）
 * AC-04-2：5.0 Lite 模型下，steps 输入框不显示
 * AC-04-3：5.0 Lite 强行提交 steps，后端不含 steps（由 backend unit test 覆盖；E2E 验 UI 不显示）
 * AC-04-4：guidance_scale 不填时，请求体无 guidance_scale 或使用默认（由 backend unit test 覆盖）
 * AC-04-5：watermark 开启后，请求体含 watermark=true
 *
 * 测试策略：
 *   - 拦截 POST /api/v1/image/generate/ 验证请求体参数
 *   - el-input-number（seed）需等待 300ms 再读取值（既往陷阱）
 *   - el-collapse 展开：点击 .el-collapse-item__header
 *   - 模型选择：通过 ModelSelector 组件的 el-select
 *
 * 注意：
 *   - AC-04-3（白名单过滤）的核心逻辑是后端行为，由 test_doubao_client.py 的
 *     test_canary_model_50_lite_steps_not_in_whitelist 覆盖
 *   - E2E 只验证 UI：5.0 Lite 时 steps 控件不可见
 */
import { test, expect, Page } from '@playwright/test'

const API_GENERATE = '**/api/v1/image/generate/**'

const MODEL_5_0_LITE = 'doubao-seedream-5-0-260128'
const MODEL_4_5     = 'doubao-seedream-4-5-251128'

async function gotoImageGenerator(page: Page) {
  await page.goto('/image-generator')
  await page.locator('h2:text-is("AI 图片生成")').waitFor({ state: 'visible' })
  await page.locator('.input-panel').waitFor({ state: 'visible' })
}

/**
 * 展开"高级选项"折叠面板
 */
async function expandAdvancedPanel(page: Page) {
  const header = page.locator('.el-collapse-item__header:has-text("高级选项")')
  // 检查是否已展开（el-collapse-item--active class）
  const isActive = await page.locator('.el-collapse-item.is-active').count() > 0
  if (!isActive) {
    await header.click()
    // 等待展开动画
    await page.waitForTimeout(400)
  }
  // 验证内容区域可见
  await expect(page.locator('.params-grid')).toBeVisible()
}

/**
 * 通过 ModelSelector 切换模型
 *
 * ModelSelector 是 el-select 下拉，选项弹层挂载在 body
 */
async function selectModel(page: Page, modelId: string) {
  // 点击 ModelSelector 的触发器（.model-selector 容器内的 el-select wrapper）
  const modelSelector = page.locator('.model-selector')
  await modelSelector.locator('.el-select .el-input__wrapper').click()

  // 等待下拉弹层
  await page.locator('.el-select-dropdown__item').first().waitFor({ state: 'visible' })

  // 选择包含 modelId 的选项
  const option = page.locator(`.el-select-dropdown__item`).filter({ hasText: modelId }).first()
  await option.click()
}

test.describe('US-04 — 高级参数配置', () => {

  /**
   * AC-04-1：填入 seed=12345，提交请求含 seed=12345
   *
   * Given：用户展开"高级选项"，填入 seed=12345
   * When：点击"开始生成"
   * Then：请求体含 seed=12345
   */
  test('AC-04-1: seed=12345 正确传入请求体', async ({ page }) => {
    await gotoImageGenerator(page)
    await expandAdvancedPanel(page)

    let capturedPostData: string | null = null
    await page.route(API_GENERATE, async (route) => {
      capturedPostData = route.request().postData()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ batch_id: 'mock', batch_name: 'Mock', n: 1, status: 'pending', ws_token: 'tok' }),
      })
    })

    // 定位 seed 输入框（.el-input-number 内的 input）
    const seedInput = page.locator('.param-item').filter({ hasText: '随机种子' }).locator('input').first()
    await seedInput.tripleClick()
    await seedInput.fill('12345')

    // 等待 Vue 响应（既往 el-input-number 延迟陷阱）
    await page.waitForTimeout(300)

    // 填提示词并提交
    await page.locator('textarea[placeholder*="提示词"]').fill('seed 测试提示词')
    await page.locator('button:has-text("开始生成")').click()
    await page.waitForTimeout(500)

    // 验证请求体含 seed=12345
    expect(capturedPostData!, '请求体应含 seed').toContain('seed')
    expect(capturedPostData!, '请求体应含 12345').toContain('12345')
  })

  /**
   * AC-04-2：5.0 Lite 模型下，steps 输入框不显示
   *
   * Given：用户选择模型 doubao-seedream-5-0-260128
   * When：展开"高级选项"
   * Then：steps 输入框不显示（或显示为禁用状态）
   */
  test('AC-04-2: 5.0 Lite 模型时 steps 控件不显示', async ({ page }) => {
    await gotoImageGenerator(page)

    // 切换到 5.0 Lite 模型
    await selectModel(page, '5-0-260128')  // 含此字符串的选项即为 5.0 Lite

    // 展开高级选项
    await expandAdvancedPanel(page)

    // steps 控件不应出现（ModelSelector prop modelSupportsSteps 控制 v-if）
    const stepsItem = page.locator('.param-item').filter({ hasText: '推理步数' })
    await expect(stepsItem, 'steps 控件在 5.0 Lite 模型时不应显示').not.toBeVisible()
  })

  /**
   * AC-04-2 补充：4.5 模型下，steps 输入框显示
   *
   * Given：用户选择模型 doubao-seedream-4-5-251128
   * When：展开"高级选项"
   * Then：steps 输入框可见
   */
  test('AC-04-2 补充: 4.5/4.0 模型时 steps 控件显示', async ({ page }) => {
    await gotoImageGenerator(page)

    // 切换到 4.5 模型（支持 steps）
    await selectModel(page, '4-5-251128')

    // 展开高级选项
    await expandAdvancedPanel(page)

    // steps 控件应出现
    const stepsItem = page.locator('.param-item').filter({ hasText: '推理步数' })
    await expect(stepsItem, 'steps 控件在 4.5 模型时应显示').toBeVisible()
  })

  /**
   * AC-04-5：watermark 开关开启后，请求体含 watermark=true
   *
   * Given：用户开启 watermark 开关
   * When：提交生成请求
   * Then：请求体含 watermark=true
   */
  test('AC-04-5: watermark=true 正确传入请求体', async ({ page }) => {
    await gotoImageGenerator(page)
    await expandAdvancedPanel(page)

    let capturedPostData: string | null = null
    await page.route(API_GENERATE, async (route) => {
      capturedPostData = route.request().postData()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ batch_id: 'mock', batch_name: 'Mock', n: 1, status: 'pending', ws_token: 'tok' }),
      })
    })

    // 定位 watermark 开关（el-switch 在"添加水印"参数项内）
    const watermarkItem = page.locator('.param-item').filter({ hasText: '添加水印' })
    const switchEl = watermarkItem.locator('.el-switch')
    await switchEl.click()

    // 等待 Vue 响应
    await page.waitForTimeout(300)

    // 填提示词并提交
    await page.locator('textarea[placeholder*="提示词"]').fill('watermark 测试提示词')
    await page.locator('button:has-text("开始生成")').click()
    await page.waitForTimeout(500)

    // 验证请求体含 watermark
    expect(capturedPostData!, '请求体应含 watermark').toContain('watermark')
    // watermark=true 在 FormData 中为字符串 "true"
    expect(capturedPostData!, '请求体应含 watermark=true').toContain('true')
  })
})
