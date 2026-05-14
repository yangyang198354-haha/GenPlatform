/**
 * E2E 共用工具函数
 *
 * 封装常见陷阱规避模式（参见 memory feedback_e2e_playwright_patterns.md）：
 * - el-radio-button 选择：通过精确 label 文本定位，避免 getByText 多匹配
 * - el-select 下拉：点击触发器 → 等待弹层 → 选择选项
 * - el-input-number：fill 后等待 300ms 让 Vue 响应
 * - Lightbox（el-image preview）：弹层挂载在 body，通过 .el-image-viewer__wrapper 定位
 */
import { Page, Locator, expect } from '@playwright/test'

/**
 * 在 el-radio-group 中点击指定 label 的 radio button。
 * 使用精确文本 + 向上查找 .el-radio-button 容器，避免 getByText 多匹配。
 */
export async function clickRadioButton(container: Locator | Page, labelText: string) {
  // el-radio-button__inner 是可见的 label span
  const btn = (container as any).locator(`.el-radio-button__inner:text-is("${labelText}")`)
  await btn.click()
}

/**
 * 打开 el-select 并选择指定选项（通过 label 文本）。
 * 选项弹层挂载在 body，用 page.locator 而非 container.locator。
 */
export async function selectOption(page: Page, trigger: Locator, optionText: string) {
  await trigger.click()
  // 等待下拉弹层出现
  await page.locator('.el-select-dropdown__item').first().waitFor({ state: 'visible' })
  // 用精确文本匹配（避免 getByText 匹配多个含该文本的元素）
  await page.locator(`.el-select-dropdown__item:text-is("${optionText}")`).click()
}

/**
 * 等待 el-image Lightbox 弹层出现（挂载在 body）。
 * 返回 Lightbox 包装元素的 Locator，供后续断言使用。
 */
export async function waitForLightbox(page: Page): Promise<Locator> {
  const lightbox = page.locator('.el-image-viewer__wrapper')
  await lightbox.waitFor({ state: 'visible', timeout: 8_000 })
  return lightbox
}

/**
 * 等待 el-image Lightbox 关闭（消失）。
 */
export async function waitForLightboxClosed(page: Page) {
  const lightbox = page.locator('.el-image-viewer__wrapper')
  await lightbox.waitFor({ state: 'hidden', timeout: 5_000 })
}

/**
 * 设置 el-input-number 的值（直接 triple-click 清空再 fill，然后等待响应）。
 * 规避既往陷阱：el-input-number 内部有嵌套 input，必须定位到实际 input 元素。
 */
export async function fillInputNumber(container: Locator | Page, value: number) {
  const input = (container as any).locator('.el-input-number input').first()
  await input.tripleClick()
  await input.fill(String(value))
  // 等待 Vue 响应式更新（既往陷阱：直接断言可能拿到旧值）
  await (container as any).page().waitForTimeout(300)
}
