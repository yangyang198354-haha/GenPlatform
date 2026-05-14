# 用户故事 v1.2 — AI 图片功能增强

**file_header**
- document_id: US-v1.2
- author_agent: sub_agent_requirement_analyst
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2 AI 图片功能 4 项调整
- status: DRAFT
- created_at: 2026-05-14
- source: requirements_spec.md v1.2

> 格式约定：每条 AC 采用 Given/When/Then 结构，可被 Playwright E2E 测试直接覆盖。

---

## Epic 1：豆包图片生成 API 参数完整支持

### US-01：尺寸精确输入（像素）

**As** 设计师用户，
**I want** 能精确指定生成图片的像素尺寸（如 2048×2048），
**So that** 我的图片满足特定平台的分辨率要求。

**Acceptance Criteria：**

**AC-01-1（像素尺寸选择）**
- Given：用户在 AI 图片页面，尺寸输入方式选择"精确像素"
- When：用户从下拉列表选择 `2880x1620`
- Then：提交后，后端 Celery Task 调用 Ark API 时 `size` 参数为 `"2880x1620"`

**AC-01-2（越界拒绝）**
- Given：用户通过 API 直接提交 `size: "999x999"`
- When：POST /api/v1/image/generate/ 被处理
- Then：Serializer 返回 400，响应含 `{"error": "不支持的图片尺寸"}`

### US-02：尺寸档位输入（2K/3K/4K）

**As** 内容创作者，
**I want** 快速选择 2K/3K/4K 档位来指定图片精度，
**So that** 无需记忆像素数字。

**AC-02-1（2K 档位映射）**
- Given：用户选择尺寸方式"档位"，选择档位"2K"
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 `size` 为 `"2048x2048"`

**AC-02-2（4K 档位映射）**
- Given：用户选择尺寸方式"档位"，选择档位"4K"
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 `size` 为 `"4096x4096"`

### US-03：尺寸比例×档位输入（1:1 / 16:9 等，配合 2K/3K/4K 档位）

**As** 社媒运营人员，
**I want** 按比例（如 9:16）并指定档位（如 3K）选择图片尺寸，
**So that** 图片比例和分辨率都精确匹配目标平台需求。

**AC-03-1（9:16 比例 × 默认2K 映射）**
- Given：用户选择尺寸方式"比例"，选择 9:16，档位保持默认 2K
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 `size` 为 `"1620x2880"`

**AC-03-2（4:3 比例 × 默认2K 映射）**
- Given：用户选择比例 4:3，档位保持默认 2K
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 `size` 为 `"2880x2160"`

**AC-03-3（16:9 比例 × 4K 组合）**
- Given：用户选择比例 16:9，档位选择 4K
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 `size` 为 `"4096x2304"`

**AC-03-4（9:16 比例 × 3K 组合）**
- Given：用户选择比例 9:16，档位选择 3K
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 `size` 为 `"2160x3840"`

### US-04：高级参数配置

**As** 有经验的 AI 图片用户，
**I want** 在高级选项中配置 seed / guidance_scale / negative_prompt / steps / watermark，
**So that** 我能精确控制生成效果。

**AC-04-1（seed 复现）**
- Given：用户展开"高级选项"，填入 seed=12345
- When：点击"开始生成"
- Then：后端 Task 传给 Ark 的 advanced_params 含 `seed=12345`；连续两次相同 seed+prompt 生成结果视觉上一致（Canary 守卫测试验证参数传递）

**AC-04-2（steps 条件显示）**
- Given：用户选择模型 `doubao-seedream-5-0-260128`（5.0 Lite）
- When：展开"高级选项"
- Then：`steps` 输入框不显示（或显示为禁用状态）

**AC-04-3（steps 白名单过滤）**
- Given：用户选择模型 5.0 Lite，通过 API 强行提交 `steps=50`
- When：后端 Task 构建 Ark 请求体
- Then：Ark 请求体中不含 `steps` 字段（MODEL_ADVANCED_PARAMS 白名单过滤）

**AC-04-4（guidance_scale 默认值）**
- Given：用户未修改 guidance_scale
- When：提交生成请求
- Then：后端传给 Ark 的 guidance_scale 为 7.5（或不传，Ark 使用其默认值）

**AC-04-5（watermark 开关）**
- Given：用户开启 watermark 开关
- When：提交生成请求
- Then：Ark 请求体含 `"watermark": true`

### US-05：生成模式切换（主图 / 多图）

**As** 内容创作者，
**I want** 在 UI 上切换"主图模式"（生成 1 张）和"多图模式"（生成 2–4 张），
**So that** 我可以快速获得一张最优图，或一次生成多个候选。

**AC-05-1（主图模式）**
- Given：用户切换到"主图模式"
- When：点击"开始生成"
- Then：提交的 `n=1`；结果区展示 1 张图片

**AC-05-2（多图模式）**
- Given：用户切换到"多图模式"，选择张数 3
- When：点击"开始生成"
- Then：提交的 `n=3`；结果区最终显示 3 张图片卡片

**AC-05-3（n 超限拒绝）**
- Given：用户通过 API 提交 `n=5`
- When：POST /api/v1/image/generate/
- Then：返回 400，`{"error": "单批次最多生成 4 张图片"}`

---

## Epic 2：AI 图片页面 UI 布局优化

### US-06：生成设置面板容纳全部参数

**As** 平台用户，
**I want** 在"生成设置"面板中看到所有可配置选项且布局不拥挤，
**So that** 我能方便地配置图片参数。

**AC-06-1（面板宽度足够）**
- Given：浏览器视口宽度 ≥ 1200px
- When：打开 AI 图片生成页面
- Then：左侧"生成设置"面板宽度 ≥ 460px，所有参数控件完整显示无截断

**AC-06-2（尺寸区块存在）**
- Given：用户打开 AI 图片生成页面
- When：查看"生成设置"面板
- Then：面板中可见"图片尺寸"区块，含三种输入方式（精确像素 / 档位 / 比例）的切换控件

**AC-06-3（响应式）**
- Given：浏览器视口宽度 ≤ 900px
- When：打开 AI 图片生成页面
- Then：生成设置与结果面板改为单列布局，参数面板无横向溢出

---

## Epic 3：MediaLibraryView 图片放大预览

### US-07：点击图片触发 Lightbox（MediaLibraryView）

**As** 平台用户，
**I want** 在 **素材库**（`/media-library`）中点击图片缩略图就能查看大图，
**So that** 我无需下载即可确认图片质量和细节。

**AC-07-1（点击显示 Lightbox）**
- Given：MediaLibraryView（`/media-library`）中存在至少一张 AI 生成图片
- When：用户点击该图片缩略图（或图片行的预览区域）
- Then：页面显示 Lightbox 弹层，图片以原始比例放大显示；遮罩层覆盖背景

**AC-07-2（Esc 关闭）**
- Given：Lightbox 已弹出
- When：用户按下 Esc 键
- Then：Lightbox 关闭，返回列表页

**AC-07-3（点击蒙层关闭）**
- Given：Lightbox 已弹出
- When：用户点击 Lightbox 外部蒙层区域
- Then：Lightbox 关闭

**AC-07-4（操作并存）**
- Given：Lightbox 已弹出，且图片条目有"删除"和"下载"按钮
- When：用户关闭 Lightbox 后
- Then："删除"和"下载"按钮仍正常可用

**AC-07-5（非图片条目不显示预览入口）**
- Given：素材库中有一条文档类型条目（非图片）
- When：用户查看该条目
- Then：无放大预览图标或点击区域（仅有"删除"和"下载"）

---

## Epic 4：清理即梦 API 残留

### US-08：系统设置不再显示即梦 API 配置

**As** 平台管理员，
**I want** 系统设置页面不再显示已废弃的"即梦 API"配置区块，
**So that** 界面整洁，不引起用户误配置。

**AC-08-1（Tab 消失）**
- Given：用户打开系统设置页面
- When：查看左侧 Tab 列表
- Then：不存在"即梦 API"标签页

**AC-08-2（历史数据保留）**
- Given：数据库中存在 service_type="jimeng" 的 UserServiceConfig 记录
- When：后端完成清理后
- Then：该记录仍存在，未被删除（即数据库兼容）

**AC-08-3（前端无即梦相关 JS 引用）**
- Given：SettingsView.vue 代码
- When：审查 script 部分
- Then：不含 jimengForm / saveJimengConfig / testJimengConfig 变量和函数

**AC-08-4（后端无残留路由）**
- Given：后端 URL 配置
- When：执行 `python manage.py show_urls` 或检查 urls.py
- Then：无专属图片即梦 API 的 URL 路由（视频即梦路由不在此范围）

---

## 测试覆盖矩阵

| 用户故事 | AC | 测试类型 | 测试文件位置（建议） |
|---------|-----|---------|-------------------|
| US-01 | AC-01-1/2 | Unit（Serializer）+ E2E | `test_serializers.py` / `test_image_ui_size.spec.ts` |
| US-02 | AC-02-1/2 | Unit（Serializer） | `test_serializers.py` |
| US-03 | AC-03-1~4 | Unit（Serializer） | `test_serializers.py` |
| US-04 | AC-04-1~5 | Unit（Canary 守卫 + Serializer）+ E2E | `test_serializers.py` / `test_advanced_params.spec.ts` |
| US-05 | AC-05-1~3 | Unit + E2E | `test_views.py` / `test_image_ui_mode.spec.ts` |
| US-06 | AC-06-1~3 | E2E（Playwright 视口测试） | `test_image_ui_layout.spec.ts` |
| US-07 | AC-07-1~5 | E2E | `test_media_library_lightbox.spec.ts` |
| US-08 | AC-08-1~4 | E2E + Unit | `test_settings_cleanup.spec.ts` / `test_settings_vault.py` |
