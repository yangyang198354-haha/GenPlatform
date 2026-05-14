# API Key 管理设计审查报告

**文档编号**：REQ-REVIEW-IMG-001  
**版本**：v1.0  
**创建日期**：2026-05-14  
**状态**：REVIEW — 待用户拍板决策方向  
**负责人**：PM 主代理（缺陷分析 + 需求澄清阶段，不进入开发实施）

---

## 一、根因分析

### 1.1 用户报错的完整调用链路

用户在新物理机部署后尝试生图，触发以下调用链：

```
用户点击"生成" (ImageGeneratorView.vue)
  → POST /api/v1/image/generate/
  → Django View 创建 ImageBatch，派发 Celery 任务
  → generate_image_task(batch_id) 在 Celery worker 中执行
  → tasks.py 第 98-113 行：
      UserServiceConfig.objects.get(
          user_id=user.pk,
          service_type="doubao_image",   ← 精确查找此 service_type
          is_active=True
      )
      → 抛出 UserServiceConfig.DoesNotExist
      → _fail_batch() 置批次为 failed
      → push_notification_sync() 推送错误："请先在设置中配置豆包 Ark API Key"
  → 前端 WebSocket 收到 image_failed 事件，展示该错误消息
```

**报错消息来源**：`apps/image_generator/tasks.py` 第 104-112 行，硬编码字符串 `"请先在设置中配置豆包 Ark API Key"`。

### 1.2 当前 settings_vault 的 service_type 清单

`apps/settings_vault/models.py` 第 6-12 行，当前 SERVICE_CHOICES 共 4 项：

| service_type | 显示名称 | 用途 |
|---|---|---|
| `llm_deepseek` | DeepSeek LLM | 大语言模型（DeepSeek） |
| `llm_volcano` | 火山引擎（豆包） | 大语言模型（豆包 LLM Endpoint） |
| `jimeng` | 即梦视频/图片生成 | 视频生成（仍在使用） |
| `doubao_image` | 豆包图片生成 | 图片生成（本次新增，Ark Bearer Token） |

**关键点**：`llm_volcano` 存储的是豆包 LLM 的 Ark Key；`doubao_image` 存储的是图片生成的 Ark Key。两者在模型层是独立的两行记录。

### 1.3 为何当前设计要求独立配置

`llm_gateway/providers.py` 第 119-135 行的 `get_provider()` 工厂函数，在调用豆包 LLM 时使用 `service_type="llm_volcano"` 查询 Key。图片生成的 `tasks.py` 使用 `service_type="doubao_image"` 查询 Key。两条查询路径**完全隔离，无任何 fallback 机制**，代码中不存在跨服务复用 Key 的逻辑。

### 1.4 发现的三处设计实施缺口（新发现，非用户反馈）

在分析过程中发现以下三处实施缺口，直接导致用户无法配置 `doubao_image` Key：

**缺口 1（最严重）：前端 SettingsView.vue 完全缺少豆包图片 Key 的配置入口**  
`SettingsView.vue` 目前只有三个 Tab：大语言模型、即梦 API、存储设置。**没有"豆包图片生成"Tab**，用户在 UI 上没有任何入口来配置 `doubao_image` 类型的 Key。这是用户报错的直接原因——即便用户想配，界面上也找不到地方。

**缺口 2：`settings_vault/views.py` `_required_keys()` 漏判 `doubao_image`**  
`views.py` 第 102-107 行的 `_required_keys()` 函数，未包含 `doubao_image` 的必填字段定义。虽然保存行为本身（`update_or_create`）不依赖此函数也能正常执行，但必填校验缺失意味着存入空 `api_key` 时后端不会拒绝，留下隐患。

**缺口 3：`_test_connection()` 没有 `doubao_image` 分支**  
`views.py` 第 116-152 行的 `_test_connection()` 函数，没有 `doubao_image` 的处理分支，用户配置后无法测试连通性。

**总结**：架构阶段 ADR-06 在"影响"一节中写到"settings_vault 视图/序列化器：无需新增，现有通用 CRUD 接口已支持任意 service_type"——这个判断低估了前端 SettingsView 需要同步新增配置 Tab 的工作量，导致该工作在实施阶段被遗漏。

---

## 二、方案对比表

> **前置问题：火山方舟 Ark 同一 API Key 是否同时支持 LLM 和图像端点？**
>
> 根据火山方舟官方文档（`ark.cn-beijing.volces.com`）的架构说明：
> - Ark 平台使用统一的 Bearer Token（API Key）体系，同一 Key 可以调用该账号下所有已开通的服务端点
> - `/api/v3/chat/completions`（LLM）和 `/api/v3/images/generations`（图像）均属于 Ark API v3，使用相同的认证体系
> - 区别在于：LLM 调用还需要额外指定 Endpoint ID（推理接入点，格式 `ep-xxxxxxxx`），即本平台 `llm_volcano` 中存储的 `model_name` 字段；图像接口直接指定模型名称（如 `Doubao-Seedream-4.5`），不需要独立的 Endpoint ID
>
> **结论：技术上，同一个 Ark API Key 可以同时调用 LLM 端点和图像端点，方案 A 技术可行。**  
> **但 LLM 服务还额外依赖 Endpoint ID（ep- 前缀），而图像服务不需要。**

---

### 方案 A：统一复用豆包 Ark Key（单 service_type）

设计思路：废弃 `doubao_image` service_type，图片生成改为从 `llm_volcano` 读取 Ark Key。

| 维度 | 评估 |
|---|---|
| **技术可行性** | 可行。Ark 同一 Key 支持 LLM 和图像端点。但 `llm_volcano` 存储的配置 JSON 包含 `{"api_key": "...", "model_name": "ep-xxx", ...}`，图片生成只需要 `api_key`，读取时需单独提取该字段，需改动 `tasks.py` 的 Key 读取逻辑。 |
| **UX** | 最简单。用户只需配置一次 Key（在现有"大语言模型 - 火山引擎"Tab），即可同时启用 LLM 和图片生成。无重复填写。 |
| **安全** | 配额耗尽为单点故障：LLM 高频调用消耗配额后，图片生成也会失败（HTTP 429）。无法为 LLM 和图片设置独立的用量告警。 |
| **运维** | 账单无法按 LLM/图片拆分统计。Key 轮转时两项服务同步受影响。 |
| **实施成本** | 低。主要改动：`tasks.py` 改为读 `llm_volcano` Key；删除 `doubao_image` service_type；前端无需新增 Tab。 |

**额外限制**：若用户未配置 LLM 豆包（只配了 DeepSeek），则图片生成无 Key 可用，错误提示需更新为引导用户配置火山引擎 LLM Key，语义模糊。

---

### 方案 B：独立管理（当前设计，修复前端缺口）

设计思路：保持 `doubao_image` service_type 独立，但补全前端配置入口（修复缺口 1/2/3）。

| 维度 | 评估 |
|---|---|
| **技术可行性** | 完全可行，当前后端逻辑已完整实现，只缺前端 UI 入口。 |
| **UX** | 用户需要在"设置"页配置两个 Key（如果同时用 LLM 豆包和图片豆包）。即便填入的是同一个值，也需要操作两次。新用户容易遗漏。 |
| **安全** | 配额隔离，LLM 和图片独立计量，可分别设置告警和轮转策略。符合最小权限原则（若需要，可为图片服务使用权限更受限的子账号 Key）。 |
| **运维** | 账单可按服务类型拆分。两个 Key 分别管理，独立更换，互不影响。 |
| **实施成本** | 中。主要改动：SettingsView.vue 新增豆包图片 Tab；views.py 补全 `_required_keys` 和 `_test_connection`；AC-01-4 的错误提示需增强为带跳转链接。 |

---

### 方案 C：独立 service_type + "从 LLM Key 一键复制"（折中方案）

设计思路：保持 `doubao_image` service_type 独立，但在前端提供"复制自火山引擎 LLM Key"的快捷按钮，减少用户重复填写的摩擦。

| 维度 | 评估 |
|---|---|
| **技术可行性** | 可行。前端读取 `llm_volcano` 的已保存 Key 掩码，点击复制时通过专用接口（或引导用户手动填写）填入 `doubao_image` 表单。注意：由于 Key 在展示时已脱敏（掩码），"一键复制"需要后端提供专用的"从服务 A 克隆配置到服务 B"接口，或改为前端"提示用户在两处填写相同值"的引导文案。 |
| **UX** | 优于方案 B，劣于方案 A。有明确引导，用户不会困惑为何需要配两次。 |
| **安全** | 与方案 B 相同，配额隔离，独立管理。 |
| **运维** | 与方案 B 相同。 |
| **实施成本** | 中高。在方案 B 基础上需额外设计克隆接口或引导文案，前端 UX 设计复杂度略高。 |

---

## 三、设计缺失评估

### 3.1 ADR-06 是否遗漏了"Key 复用策略"

**结论：是，ADR-06 存在明显的漏判。**

ADR-06 在"选项对比"表中列出了三个选项（A/B/C），全部聚焦于"如何存储单个 Key"的技术实现，**完全没有分析"是否与现有 `llm_volcano` Key 共享"这一业务问题**。在"影响"一节仅写"settings_vault 视图/序列化器无需新增"，这个结论跳过了"前端是否需要新增配置入口"的核实步骤。

ADR-06 需要补充的判断点：
1. Ark 同一 Key 跨服务可行性（技术确认）
2. 选择独立 service_type 后，前端需要新增配置 Tab（实施边界）
3. 新用户 onboarding 流程：首次使用图片生成前，是否有引导提示

### 3.2 用户故事是否缺少 Onboarding 引导

**结论：是，存在用户故事缺口。**

US-07（配置豆包 Ark API Key）的验收标准只覆盖了"已知道要配置"的用户场景：

| 现有 AC | 覆盖场景 |
|---|---|
| AC-07-1 | 用户主动进入设置页配置 Key |
| AC-07-2 | 用户配置后发起生成，Key 正常使用 |
| AC-07-3 | Key 格式校验 |

**缺失的验收标准（未被任何 US 覆盖）**：

| 缺失 AC 编号（建议） | 场景描述 |
|---|---|
| AC-07-4（建议新增） | 用户首次登录，从未配置任何图片生成 Key，直接进入图片生成页面：系统应在页面顶部展示 Banner 提示"您尚未配置豆包图片生成 Key，前往设置配置"，并提供可点击跳转链接 |
| AC-07-5（建议新增） | 用户点击生成后收到"未配置 API Key"的任务失败通知：错误提示应包含直接跳转到设置页相应 Tab 的链接，而非仅展示文字提示 |
| US-08（建议新增）| **Onboarding 引导故事**：作为第一次使用 AI 图片生成的用户，我希望系统告知我需要先配置哪些服务的 Key 以及去哪里配置，以便我不需要阅读文档就能完成初次设置 |

### 3.3 错误提示是否足够好

**结论：不够好，存在三个层次的问题。**

**问题 1：后端错误消息无操作引导**  
`tasks.py` 第 107 行的错误消息为纯文字 `"请先在设置中配置豆包 Ark API Key"`，没有路径信息。用户收到后不知道去哪个页面配置。

**问题 2：前端无跳转链接**  
`ImageGeneratorView.vue` 收到 `image_failed` 事件后，仅通过 `ElMessage` 或状态展示错误文本，没有可点击的"前往配置"链接。

**问题 3：前端无预检机制（最优方案）**  
US-01 的 AC-01-4 描述了"用户未配置 API Key 时点击生成按钮，界面显示错误提示"，但该 AC 是在任务失败后（Celery 级别）才反馈错误。更好的做法是前端在页面加载时调用 `GET /api/v1/settings/` 接口（`settings_vault` 已有此接口），检查 `doubao_image` 是否 `is_configured=true`，若否则在页面顶部提前提示，**阻止用户在未配置时提交请求**，而不是等任务跑起来再报错。

---

## 四、PM 推荐方案

### 推荐：方案 C（独立 service_type + 引导文案）

**推荐理由**：

1. **技术安全性优先**：保持配额隔离的架构，LLM 和图片的使用量相互不影响，账单更清晰，符合平台多用户、多服务的长期发展方向。

2. **方案 A 的 UX 优势是表面的**：若用户只用 DeepSeek LLM，方案 A 中图片生成无 Key 可用，需要用户额外去配一个"豆包 LLM Key"——这不是为了用 LLM，而是为了借用 Key 给图片服务，语义混乱，比独立配置更令人困惑。

3. **方案 B 的实施成本与方案 C 相近**：在补全前端 Tab 的基础上，增加引导文案几乎没有额外成本。

4. **方案 C 的实施边界清晰**：
   - 后端：只需补全 2 个函数（`_required_keys`、`_test_connection`），无模型层改动
   - 前端：新增"豆包图片生成"配置 Tab，在图片生成页面增加"未配置 Key"的 Banner 预检
   - 引导文案无需实现"克隆接口"，改为显示提示"若您已在火山引擎 LLM 中配置了 Ark Key，可在此处填写相同的值"即可

**不推荐方案 A 的主要原因**：Ark LLM 调用还依赖 Endpoint ID（`ep-xxxxxxxx`），而图片服务不需要。若合并为同一 service_type，需要从 `llm_volcano` 的配置 JSON 中只读取 `api_key` 字段，在 `tasks.py` 中增加字段提取逻辑，且当用户未配置豆包 LLM（只用 DeepSeek）时图片服务无法工作，错误提示设计复杂。综合来看，方案 A 的 UX 收益不足以抵消架构耦合带来的复杂性。

---

## 五、后续工单清单

以下工单仅供参考，不进入实施阶段，等待用户决策后再排期。

### 工单 T-01（阻塞性，优先级 P0）：前端 SettingsView 新增豆包图片生成 Tab

**类型**：前端缺陷修复  
**关联缺口**：缺口 1  
**描述**：在 `SettingsView.vue` 中新增"豆包图片生成"Tab，包含：
- API Key 输入框（带掩码，show-password）
- "保存"按钮，调用 `PUT /api/v1/settings/doubao_image/`
- "测试连接"按钮，调用 `POST /api/v1/settings/doubao_image/test/`
- 引导文案（方案 C）："若您已在火山引擎 LLM 中配置了 Ark Key，可在此处填写相同的值"
**影响文件**：`src/frontend/src/views/SettingsView.vue`

---

### 工单 T-02（阻塞性，优先级 P0）：后端 settings_vault 补全 `doubao_image` 支持

**类型**：后端缺陷修复  
**关联缺口**：缺口 2、缺口 3  
**描述**：
1. `views.py` `_required_keys()` 新增 `"doubao_image": ["api_key"]`
2. `views.py` `_test_connection()` 新增 `doubao_image` 分支：用提供的 Key 调用 Ark `/api/v3/models`（或图片接口的轻量健康检查），验证 Key 有效性
**影响文件**：`apps/settings_vault/views.py`

---

### 工单 T-03（体验优化，优先级 P0）：图片生成页面增加"未配置 Key"预检 Banner

**类型**：前端体验优化  
**关联缺口**：US 缺口（AC-07-4）  
**描述**：`ImageGeneratorView.vue` 页面加载时调用 `GET /api/v1/settings/`，检查返回列表中 `service_type=doubao_image` 的 `is_configured` 字段。若为 `false`，在页面顶部展示 Warning Banner："您尚未配置豆包图片生成 API Key，点击前往设置"，点击后跳转至 `SettingsView` 并自动激活"豆包图片生成"Tab。此 Banner 在用户完成配置后隐藏。  
**影响文件**：`src/frontend/src/views/ImageGeneratorView.vue`

---

### 工单 T-04（体验优化，优先级 P1）：错误通知增强——带跳转链接

**类型**：前端体验优化  
**关联缺口**：US 缺口（AC-07-5）  
**描述**：当前端收到 `image_failed` WebSocket 事件且 `error` 内容包含"请先在设置中配置"时，将纯文字提示升级为带链接的通知组件（如 `ElNotification` with action button），提供"前往配置"按钮跳转至设置页。  
**影响文件**：`src/frontend/src/views/ImageGeneratorView.vue`

---

### 工单 T-05（需求文档补充，优先级 P1）：补写 US-08 Onboarding 用户故事

**类型**：需求文档完善  
**描述**：在 `docs/requirements/doubao_image_migration/user_stories.md` 中新增 US-08，覆盖首次使用图片生成时的 Key 配置引导场景（含 AC-07-4、AC-07-5 的验收标准）。  
**影响文件**：`docs/requirements/doubao_image_migration/user_stories.md`

---

### 工单 T-06（架构文档补充，优先级 P2）：ADR-06 补充 Key 复用策略判断

**类型**：架构文档完善  
**描述**：在 ADR-06 中补充以下内容：(1) Ark 同一 Key 跨服务的技术确认；(2) 选择独立 service_type 后前端必须新增配置 Tab 的实施边界说明；(3) 记录决策排除方案 A 的理由（Endpoint ID 依赖耦合问题）。  
**影响文件**：`docs/architecture/doubao_image_migration/architecture_design.md`

---

## 六、决策选项（请用户三选一）

> **请在以下三个选项中选择一个，PM 将据此安排后续工单的实施优先级。**

---

**选项 A：统一复用豆包 LLM Key**  
图片生成改为从 `llm_volcano` 读取 Ark Key，废弃 `doubao_image` service_type。  
实施范围：`tasks.py` 改读 Key 来源 + 错误提示更新 + 前端无需新增 Tab。  
适合场景：平台用户群体高度重叠（使用图片的用户几乎都用豆包 LLM），希望最简配置体验。

---

**选项 B：独立管理，仅修复缺口**  
保持 `doubao_image` 独立，仅补全前端 Tab + 后端校验 + 测试连接（T-01、T-02）。  
暂不实施 Onboarding Banner 和错误通知增强。  
适合场景：优先修复阻塞性问题，尽快上线，体验优化在下个迭代处理。

---

**选项 C（PM 推荐）：独立管理 + 完整 UX 修复**  
保持 `doubao_image` 独立，实施 T-01 至 T-04 全部工单（T-05、T-06 作为文档补充）。  
适合场景：一次性修复阻塞性问题和体验缺口，避免用户再次因缺少引导而卡住。

---

*本文档由 PM 主代理生成，分析范围为缺陷定位和需求澄清，不包含任何代码实施。*  
*代码改动须等待用户决策后，由 software_developer 子代理在独立工单中执行。*
