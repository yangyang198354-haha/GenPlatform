/**
 * E2E：MediaLibraryView Lightbox 预览（US-07）
 *
 * AC-07-1：点击图片缩略图显示 Lightbox
 * AC-07-2：Esc 键关闭 Lightbox
 * AC-07-3：点击蒙层关闭 Lightbox
 * AC-07-4：Lightbox 关闭后删除/下载按钮仍可用
 * AC-07-5：非图片条目无预览入口（el-image 组件不渲染）
 *
 * 测试策略：
 *   - Mock GET /api/v1/media/ 返回预设数据（含 1 张图片 + 1 个文档）
 *   - 避免依赖真实数据库；el-image preview 弹层挂载在 body
 *
 * 关键陷阱（既往 memory）：
 *   - el-image Lightbox 挂载在 body，使用 page.locator('.el-image-viewer__wrapper')
 *   - el-image 本身需可点击：检查 .el-image__preview 或直接点击 el-image 元素
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
   * Given：MediaLibraryView 中存在至少一张 AI 生成图片
   * When：用户点击该图片缩略图
   * Then：页面显示 Lightbox 弹层，遮罩层覆盖背景
   */
  test('AC-07-1: 点击图片缩略图显示 Lightbox 弹层', async ({ page }) => {
    await gotoMediaLibraryWithMock(page)

    // 定位图片类型的 el-image 元素（第一张图片）
    const elImage = page.locator('.media-card .el-image').first()
    await expect(elImage).toBeVisible()

    // 点击图片触发 Lightbox（el-image 自带预览点击区域）
    await elImage.click()

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

    // 打开 Lightbox
    await page.locator('.media-card .el-image').first().click()
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
    await page.locator('.media-card .el-image').first().click()
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

    // Hover 触发 action overlay（HoverActions Overlay）
    await firstCard.hover()

    // 打开 Lightbox
    await firstCard.locator('.el-image').click()
    const lightbox = page.locator('.el-image-viewer__wrapper')
    await lightbox.waitFor({ state: 'visible', timeout: 8_000 })

    // 关闭 Lightbox
    await page.keyboard.press('Escape')
    await lightbox.waitFor({ state: 'hidden', timeout: 5_000 })

    // 重新 Hover 触发 overlay（Lightbox 关闭后 overlay 应恢复正常）
    await firstCard.hover()

    // 验证下载按钮可见且可点击（tooltip content="下载"）
    const downloadBtn = firstCard.locator('.hover-actions .el-button').first()
    await expect(downloadBtn).toBeVisible()
    await expect(downloadBtn).toBeEnabled()

    // 验证删除按钮可见且可点击（type="danger"）
    const deleteBtn = firstCard.locator('.hover-actions .el-button[type="danger"]')
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

    // el-image 应有 preview-src-list 属性（通过 DOM 验证组件正确渲染）
    // 注意：preview-src-list 是 Vue prop，不直接映射到 HTML attribute
    // 但 el-image 在有 preview-src-list 时会在内部 img 上添加 .el-image__preview class
    const previewImg = firstCard.locator('.el-image .el-image__inner')
    await expect(previewImg).toBeVisible()
  })
})
