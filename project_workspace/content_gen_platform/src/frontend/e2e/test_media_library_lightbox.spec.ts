/**
 * E2E：MediaLibraryView Lightbox 预览（US-07 + v1.2.1 BUG-02）
 *
 * AC-07-1：点击图片缩略图显示 Lightbox（v1.2.1 修正：hover → click el-image__inner）
 * AC-07-2：Esc 键关闭 Lightbox
 * AC-07-3：点击蒙层关闭 Lightbox
 * AC-07-4：Lightbox 关闭后删除/下载按钮仍可用
 * AC-07-5：非图片条目无预览入口（el-image 组件不渲染）
 * AC-B02-4（v1.2.1 新增）：hover 后点击操作按钮不触发 Lightbox
 * AC-B02-5（v1.2.1 新增）：hover 覆盖状态下点击图片区仍触发 Lightbox（核心漏测修复）
 *
 * 测试策略：
 *   - Mock GET /api/v1/media/ 返回预设数据（含 1 张图片 + 1 个文档）
 *   - 避免依赖真实数据库；el-image preview 弹层挂载在 body
 *
 * 关键陷阱（既往 memory + v1.2.1 发现）：
 *   - el-image Lightbox 挂载在 body，使用 page.locator('.el-image-viewer__wrapper')
 *   - v1.2.1 BUG-02 修复：.hover-overlay 现有 pointer-events:none，不再拦截点击
 *   - 正确点击策略：hover → 等待 overlay 可见 → click '.el-image__inner'（非按钮）
 *   - preview-teleported 使弹层在 document.body，z-index 不受 overflow:hidden 限制
 *   - 蒙层元素为 .el-image-viewer__mask（el-image 内置），Esc 由 el-image 内部监听
 */
import { test, expect, Page } from '@playwright/test'

const MEDIA_API = '**/api/v1/media/**'

// ── 测试固件：Mock 媒体数据 ───────────────────────────────────────────────────

const MOCK_IMAGE_ITEM = {
  id: 1,
  title: '测试生成图片.jpg',
  media_type: 'image',
  source: 'ai_generated',
  file_url: 'https://picsum.photos/seed/e2e-test/400/300',  // 公共测试图片
  file_size: 102400,
  created_at: '2026-05-14T10:00:00Z',
}

const MOCK_DOC_ITEM = {
  id: 2,
  title: '项目说明文档.pdf',
  media_type: 'document',
  source: 'uploaded',
  file_url: 'https://example.com/docs/test.pdf',
  file_size: 204800,
  created_at: '2026-05-14T09:00:00Z',
}

const MOCK_MEDIA_RESPONSE = {
  count: 2,
  next: null,
  previous: null,
  results: [MOCK_IMAGE_ITEM, MOCK_DOC_ITEM],
}

/**
 * 注入媒体 API Mock 并导航到 /media-library
 */
async function gotoMediaLibraryWithMock(page: Page) {
  await page.route(MEDIA_API, async (route) => {
    const url = route.request().url()
    if (url.includes('api/v1/media')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_MEDIA_RESPONSE),
      })
    } else {
      await route.continue()
    }
  })

  await page.goto('/media-library')
  // 等待页面标题和媒体卡片出现
  await page.locator('h2:text-is("素材库")').waitFor({ state: 'visible' })
  // 等待媒体网格渲染（至少有一个 media-card）
  await page.locator('.media-card').first().waitFor({ state: 'visible', timeout: 10_000 })
}

// ── 测试用例 ──────────────────────────────────────────────────────────────────

test.describe('US-07 — MediaLibraryView Lightbox 预览', () => {

  /**
   * AC-07-1：点击图片缩略图显示 Lightbox
   *
   * v1.2.1 BUG-02 修正：
   * - 旧策略：`elImage.click()`（未触发 hover，overlay 不可见，可能绕过真实用户场景）
   * - 新策略：hover → 等待 overlay 可见 → 点击 `.el-image__inner`（图片区，非按钮）
   * - 修复后 `.hover-overlay { pointer-events: none }` 不拦截点击，Lightbox 正常弹出
   *
   * Given：MediaLibraryView 中存在至少一张 AI 生成图片
   * When：用户 hover 后点击图片区（非操作按钮）
   * Then：页面显示 Lightbox 弹层，遮罩层覆盖背景
   */
  test('AC-07-1: 点击图片缩略图显示 Lightbox 弹层（hover 策略，v1.2.1 修正）', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    const firstCard = page.locator('.media-card').first()
    await expect(firstCard).toBeVisible()

    // v1.2.1 修正：hover 后点击 el-image__inner（而非直接 .el-image.click()）
    await firstCard.hover()
    // 等待 hover-overlay 出现（CSS transition 完成）
    await firstCard.locator('.hover-overlay').waitFor({ state: 'visible', timeout: 5_000 })
    // 点击图片内部区域（overlay pointer-events:none 后不拦截，el-image preview 触发）
    await firstCard.locator('.el-image__inner').click()

    // 等待 Lightbox 弹层出现（挂载在 body）
    const lightbox = page.locator('.el-image-viewer__wrapper')
    await lightbox.waitFor({ state: 'visible', timeout: 8_000 })
    await expect(lightbox).toBeVisible()

    // 验证遮罩层存在
    const mask = page.locator('.el-image-viewer__mask')
    await expect(mask).toBeVisible()

    // 验证图片以大图形式展示
    const img = page.locator('.el-image-viewer__canvas img')
    await expect(img).toBeVisible()
  })

  /**
   * AC-07-2：Esc 键关闭 Lightbox
   *
   * Given：Lightbox 已弹出
   * When：用户按下 Esc 键
   * Then：Lightbox 关闭
   */
  test('AC-07-2: Esc 键关闭 Lightbox', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    // 打开 Lightbox（使用修正后的 hover → click el-image__inner 策略）
    const firstCard = page.locator('.media-card').first()
    await firstCard.hover()
    await firstCard.locator('.hover-overlay').waitFor({ state: 'visible', timeout: 5_000 })
    await firstCard.locator('.el-image__inner').click()

    const lightbox = page.locator('.el-image-viewer__wrapper')
    await lightbox.waitFor({ state: 'visible', timeout: 8_000 })

    // 按 Esc 关闭
    await page.keyboard.press('Escape')

    // 等待 Lightbox 消失
    await lightbox.waitFor({ state: 'hidden', timeout: 5_000 })
    await expect(lightbox).not.toBeVisible()
  })

  /**
   * AC-07-3：点击蒙层关闭 Lightbox
   *
   * Given：Lightbox 已弹出
   * When：用户点击 Lightbox 外部蒙层区域
   * Then：Lightbox 关闭
   */
  test('AC-07-3: 点击蒙层关闭 Lightbox', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    // 打开 Lightbox
    const firstCard = page.locator('.media-card').first()
    await firstCard.hover()
    await firstCard.locator('.hover-overlay').waitFor({ state: 'visible', timeout: 5_000 })
    await firstCard.locator('.el-image__inner').click()

    const lightbox = page.locator('.el-image-viewer__wrapper')
    await lightbox.waitFor({ state: 'visible', timeout: 8_000 })

    // 点击蒙层（.el-image-viewer__mask 是 Lightbox 外围点击区域）
    const mask = page.locator('.el-image-viewer__mask')
    await mask.click()

    // 等待 Lightbox 消失
    await lightbox.waitFor({ state: 'hidden', timeout: 5_000 })
    await expect(lightbox).not.toBeVisible()
  })

  /**
   * AC-07-4：Lightbox 关闭后操作按钮仍正常可用
   *
   * Given：Lightbox 已弹出，且图片条目有"删除"和"下载"按钮
   * When：用户关闭 Lightbox 后
   * Then："删除"和"下载"按钮仍正常可用
   */
  test('AC-07-4: Lightbox 关闭后删除/下载按钮仍可用', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    const firstCard = page.locator('.media-card').first()

    // Hover + 点击图片区打开 Lightbox
    await firstCard.hover()
    await firstCard.locator('.hover-overlay').waitFor({ state: 'visible', timeout: 5_000 })
    await firstCard.locator('.el-image__inner').click()

    const lightbox = page.locator('.el-image-viewer__wrapper')
    await lightbox.waitFor({ state: 'visible', timeout: 8_000 })

    // 关闭 Lightbox
    await page.keyboard.press('Escape')
    await lightbox.waitFor({ state: 'hidden', timeout: 5_000 })

    // 重新 Hover 触发 overlay（Lightbox 关闭后 overlay 应恢复正常）
    await firstCard.hover()

    // 验证下载按钮可见且可点击
    const downloadBtn = firstCard.locator('.hover-actions .el-button').first()
    await expect(downloadBtn).toBeVisible()
    await expect(downloadBtn).toBeEnabled()

    // 验证删除按钮可见且可点击（type="danger"）
    const deleteBtn = firstCard.locator('.hover-actions .el-button').nth(1)
    await expect(deleteBtn).toBeVisible()
    await expect(deleteBtn).toBeEnabled()
  })

  /**
   * AC-07-5：非图片条目不渲染 el-image（无放大预览入口）
   *
   * Given：素材库中有一条文档类型条目（media_type=document）
   * When：用户查看该条目
   * Then：无 el-image 组件（无放大预览图标或点击区域）
   */
  test('AC-07-5: 非图片条目不渲染 el-image 预览组件', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    // 找到文档类型的卡片（second card = MOCK_DOC_ITEM）
    const docCard = page.locator('.media-card').nth(1)
    await expect(docCard).toBeVisible()

    // 文档卡片中不应有 el-image 组件
    const elImageInDoc = docCard.locator('.el-image')
    expect(await elImageInDoc.count(), '文档条目不应渲染 el-image').toBe(0)

    // 文档卡片中应有 .thumb-audio 或其他非图片占位符
    // （根据模板：document 类型走 v-else 分支，audio icon 或 doc icon）
    // 此处只确认 el-image 不存在即可
  })

  /**
   * US-07 补充：图片条目缩略图使用 el-image（而非原生 img）
   *
   * 验证 v1.2 改造已将原生 img 替换为 el-image（ADR-v1.2-03 要求）
   */
  test('US-07 补充: 图片条目使用 el-image 组件（非原生 img）', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    const firstCard = page.locator('.media-card').first()

    // 应使用 el-image（.el-image 容器存在）
    const elImage = firstCard.locator('.el-image')
    await expect(elImage).toBeVisible()

    // el-image 在有 preview-src-list 时会在内部 img 上渲染 .el-image__inner
    const previewImg = firstCard.locator('.el-image .el-image__inner')
    await expect(previewImg).toBeVisible()
  })

  // ── v1.2.1 BUG-02 新增测试 ─────────────────────────────────────────────────

  /**
   * AC-B02-4（v1.2.1 新增）：hover 后点击操作按钮不触发 Lightbox
   *
   * Given：MediaLibraryView 图片卡片 hover 状态下 overlay 可见
   * When：用户点击 hover-actions 内的操作按钮（下载/删除），而非图片区
   * Then：Lightbox 不弹出（操作按钮保持 pointer-events: auto，overlay 本身 pointer-events: none）
   *
   * 此为 v1.2 漏测点：只验证了"能开"，未验证"按钮区不误开"。
   */
  test('AC-B02-4: hover 后点击操作按钮不触发 Lightbox（反向验证）', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    const firstCard = page.locator('.media-card').first()

    // Hover 触发 overlay
    await firstCard.hover()
    await firstCard.locator('.hover-overlay').waitFor({ state: 'visible', timeout: 5_000 })

    // 点击第一个操作按钮（下载按钮）
    const firstActionBtn = firstCard.locator('.hover-actions .el-button').first()
    await expect(firstActionBtn).toBeVisible()
    await firstActionBtn.click()

    // 断言 Lightbox 未弹出（操作按钮不应触发 Lightbox）
    const lightbox = page.locator('.el-image-viewer__wrapper')
    // 给 Lightbox 500ms 窗口，若有误触发应能检测到
    await page.waitForTimeout(500)
    await expect(lightbox).not.toBeVisible()
  })

  /**
   * AC-B02-5（v1.2.1 新增，核心漏测修复）：hover 覆盖状态下点击图片区仍触发 Lightbox
   *
   * Given：用户正在 hover 某张图片（hover-overlay 可见）
   * When：用户点击图片内部区域（.el-image__inner），而非操作按钮
   * Then：Lightbox 正常弹出
   *
   * 修复验证：.hover-overlay { pointer-events: none } → el-image 接收点击 → Lightbox 弹出
   * 此为 v1.2 最关键漏测点：原 E2E 在 non-hover 状态测试，未发现 overlay 拦截问题。
   */
  test('AC-B02-5: hover 覆盖状态下点击图片区仍触发 Lightbox（v1.2.1 核心漏测修复）', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    const firstCard = page.locator('.media-card').first()

    // Hover 触发 overlay（确保 overlay 可见）
    await firstCard.hover()
    const overlay = firstCard.locator('.hover-overlay')
    await overlay.waitFor({ state: 'visible', timeout: 5_000 })
    await expect(overlay).toBeVisible()

    // 在 overlay 可见状态下，点击 el-image__inner（图片区，非按钮）
    // v1.2.1 修复：overlay pointer-events:none → 点击穿透到 el-image → Lightbox 弹出
    const elImageInner = firstCard.locator('.el-image__inner')
    await elImageInner.click()

    // 断言 Lightbox 弹出
    const lightbox = page.locator('.el-image-viewer__wrapper')
    await lightbox.waitFor({ state: 'visible', timeout: 8_000 })
    await expect(lightbox).toBeVisible()

    // 清理：关闭 Lightbox
    await page.keyboard.press('Escape')
    await lightbox.waitFor({ state: 'hidden', timeout: 5_000 })
  })
})
