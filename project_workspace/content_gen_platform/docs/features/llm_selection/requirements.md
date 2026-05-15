# LLM 模型选择功能 — 增量需求规格

**版本**：v0.1.0-DRAFT
**日期**：2026-05-15
**特性分支**：llm_selection
**关联用户原话**：
> 对于 LLM 服务配置的大语言模型，且在文案生成的时候用户可以选择使用哪一个具体服务商或者大语言模型（测试有效的）。默认使用 deepseek V3。先澄清需求和更新用户故事。以及设计方案，确认后再开始开发。

**背景**：当前文案生成入口（`apps/llm_gateway/views.py:57-80`）通过 `UserServiceConfig.objects.filter(...).first()` 自动选取用户第一条有效 LLM 配置，用户无法在生成时手动选择 provider 或 model；且 `.first()` 无 `order_by`，存在结果不确定性 BUG。

---

## 范围说明

- **本次覆盖**：文案生成（`/api/v1/llm/generate/`）的 provider/model 选择
- **本次不覆盖**：图像生成（doubao_image、jimeng）— 不动
- **当前已知 service_type**：`llm_deepseek`（DeepSeek）、`llm_volcano`（火山引擎豆包）

---

## 功能需求（FR）

### FR-LLM-SEL-01：显示可用 provider + model 下拉列表

**描述**：在文案生成表单中新增"模型"下拉控件，列出该用户已配置且 `last_test_ok = True` 的所有 LLM provider，并在 provider 层级下展示各 provider 支持的 model 列表（动态拉取）。

**验收条件（Given/When/Then）**：
- Given 用户已配置 `llm_deepseek`（last_test_ok=True）和 `llm_volcano`（last_test_ok=True）
- When 用户打开文案生成页面
- Then 下拉控件呈现两个 provider 分组，每组下列出对应 model 列表；加载过程展示 loading 状态

**关键约束**：
- 下拉数据来源：前端先调用 `/api/v1/llm/providers/`（返回用户有效 provider 列表），再对每个 provider 调用其 `/models` 接口（后端代理）获取 model 列表
- **拉取失败必须 fallback**：若任一 provider 的 /models 接口超时（>800ms）或返回非 2xx，后端返回内置白名单（见 FR-LLM-SEL-05），并在响应中附带 `models_source: "fallback"` 标志；前端检测到此标志后显示提示："模型列表加载失败，使用默认列表"
- **Ark /models 假阳性风险**（记忆 `feedback_ark_model_id_format.md`）：Ark `/v3/models` 接口验权通过不等于该 model 真正可用于生图/文案生成，白名单中的 ID 必须是经过真实业务端点验证的 ID

**对应 AC**：AC-01

---

### FR-LLM-SEL-02：默认选中规则

**描述**：进入文案生成页面时，下拉控件按以下优先级自动选中初始值：
1. 用户上次成功生成时使用的 provider + model（持久化偏好，见 FR-LLM-SEL-04）
2. 若无偏好记录或偏好对应的 provider 已失效：默认选中 `llm_deepseek` + `deepseek-chat`（DeepSeek V3）
3. 若 `llm_deepseek` 未配置或 last_test_ok=False：不自动选中任何 provider，展示占位提示（见 FR-LLM-SEL-06）

**验收条件**：
- Given 用户无偏好记录，且已配置有效的 llm_deepseek
- When 打开文案生成页面
- Then 下拉默认选中 `DeepSeek / deepseek-chat`

- Given 用户上次选了 `llm_volcano / doubao-pro-32k`，且该 provider 当前仍有效
- When 打开文案生成页面
- Then 下拉默认选中 `火山引擎 / doubao-pro-32k`

**对应 AC**：AC-02、AC-03

---

### FR-LLM-SEL-03：用户手动选择并提交

**描述**：用户可以在下拉中选择任意有效的 provider + model 组合，点击"生成"后以该组合发起请求。前端将选中的 `service_type` 和 `model` 通过请求参数传给后端。

**验收条件**：
- Given 用户在下拉中选择 `llm_volcano / doubao-pro-32k`
- When 点击"生成文案"
- Then 后端使用 VolcanoProvider 以 model=`doubao-pro-32k` 调用 API，生成结果正确返回

**关键约束**：
- 前端传参：`service_type`（如 `llm_volcano`）、`model`（如 `doubao-pro-32k`）
- 后端校验：传入的 `service_type` 必须在用户的有效配置中，否则返回 400；传入的 `model` 必须在对应 provider 的白名单或已通过验证的列表中
- 修复现有 BUG（`views.py:73`）：废弃 `.first()` 无序选取逻辑，改为以用户显式传入的 `service_type` 精确查找

**对应 AC**：AC-04

---

### FR-LLM-SEL-04：用户偏好持久化

**描述**：每次文案生成成功完成（SSE 流正常结束，非错误结束）后，后端将本次使用的 `service_type` 和 `model` 写入用户偏好记录，供下次访问时作为默认选中值。

**验收条件**：
- Given 用户选了 `llm_volcano / doubao-pro-32k` 并成功生成
- When 下次打开文案生成页面
- Then 下拉自动选中 `火山引擎 / doubao-pro-32k`

**关键约束**：
- 偏好存储在后端（新增 `UserLLMPreference` 表 或 在 `UserServiceConfig` 中存偏好字段，架构阶段确定方案）
- 偏好失效场景：若偏好中记录的 provider 被用户删除或 last_test_ok 变为 False，则回退到 FR-LLM-SEL-02 规则 2

**对应 AC**：AC-05

---

### FR-LLM-SEL-05：模型白名单（fallback 与校验基准）

**描述**：系统内置各 provider 的最小可用 model 白名单，作为动态拉取失败时的 fallback，以及前端/后端双端校验 model 合法性的基准。

**白名单内容（初始值，需要在落地时经过真实业务端点验证）**：

| Provider | service_type | model ID | 备注 |
|---|---|---|---|
| DeepSeek | llm_deepseek | deepseek-chat | V3，通用文案默认 |
| DeepSeek | llm_deepseek | deepseek-reasoner | R1，复杂推理 |
| 火山引擎豆包 | llm_volcano | doubao-pro-4k | 当前 providers.py:80 默认值 |
| 火山引擎豆包 | llm_volcano | doubao-pro-32k | 长文案场景 |

**风险提示**：Ark 平台 model ID 含日期后缀（如 `doubao-xxx-yymmdd`），Ark 发布新版本时旧 ID 会失效。白名单需要定期维护，或在 CI 中增加业务端点冒烟测试守卫。

**对应 AC**：AC-06

---

### FR-LLM-SEL-06：未配置 DeepSeek 时的提示行为

**描述**：若用户未配置任何有效 LLM provider（或仅配置了 DeepSeek 但 last_test_ok=False），且未手动选择其他 provider，则"生成"按钮置灰，并在表单区域展示提示信息。

**提示文案**：「请先配置 DeepSeek 服务，或在下拉框选择其他已配置的模型」

**验收条件**：
- Given 用户未配置任何 LLM provider（或所有 LLM 配置均 last_test_ok=False）
- When 用户打开文案生成页面
- Then 下拉控件为空/禁用状态，"生成"按钮禁用，展示上述提示
- And 用户无法发出文案生成请求（前端拦截）

**关键约束**：
- 不静默回退到其他 provider（决策 Q3-C）
- 后端也需双重防御：若 `service_type` 无效，返回 400 + 明确错误信息

**对应 AC**：AC-07

---

### FR-LLM-SEL-07：Content 表新增 provider/model 审计字段

**描述**：后端 Content 模型（文案记录表）新增 `provider` 和 `model` 字段，每次文案生成成功后将使用的 provider + model 写入该记录，供后端审计和成本核算使用。

**验收条件**：
- Given 用户以 `llm_volcano / doubao-pro-32k` 成功生成文案
- When 查询该 Content 记录
- Then `provider = "llm_volcano"`，`model = "doubao-pro-32k"` 已正确写入

**关键约束**：
- 前端"我的文案"列表不展示这两个字段（决策 Q5-B）
- 仅供后端审计/成本核算
- 字段可为 nullable（对历史数据向后兼容）

**对应 AC**：AC-08

---

### FR-LLM-SEL-08：修复 `.first()` 无序选取 BUG

**描述**：当前 `views.py:73` 使用无 `order_by` 的 `.first()`，数据库实现不保证返回顺序，可能导致每次选取到不同 provider。修复方式：改为以用户显式传入的 `service_type` 精确查找，若未传入则按 `-updated_at` 降序（即最近更新的配置优先）作为兜底。

**验收条件**：
- Given 用户配置了 `llm_deepseek`（updated_at=2026-01-01）和 `llm_volcano`（updated_at=2026-05-01）
- When 后端未收到显式 `service_type` 参数（旧客户端兼容场景）
- Then 选取 `llm_volcano`（updated_at 更新）

**对应 AC**：AC-09

---

## 非功能需求（NFR）

### NFR-01：下拉首屏加载性能

- 从用户打开页面到下拉控件可交互（含 model 列表加载完毕或超时 fallback），总耗时 ≤ 1s
- 各 provider 的 /models 接口后端代理超时设为 800ms；超时即返回白名单（fallback）
- 建议对 provider /models 结果在后端做短时缓存（TTL=5min），避免每次页面刷新都重复拉取

### NFR-02：可观测性

- 每条文案生成请求，后端日志必须包含以下字段：`provider`、`model`、`latency_ms`（LLM 调用耗时）、`success`（bool）
- SSE 错误路径（`views.py:133-158` 中 `except` 分支）须在错误日志中记录上述字段

### NFR-03：向后兼容

- 现有不传 `service_type`/`model` 参数的调用（旧前端、API 调试工具）继续可用，后端按 FR-LLM-SEL-08 的兜底逻辑处理

### NFR-04：安全

- `service_type` 参数必须在服务端白名单校验，禁止用户传入任意字符串访问未配置的 provider
- model 参数同样须在白名单中，防止枚举攻击

---

## 验收准则汇总（AC）

| AC-ID | 关联 FR/US | 验收描述 |
|---|---|---|
| AC-01 | FR-01, US-01, US-02 | 已配置有效 provider 的用户，页面首屏 ≤1s 内看到 provider+model 下拉，含 model 列表 |
| AC-02 | FR-02, US-01 | 无偏好记录 + 有效 DeepSeek 配置时，默认选中 deepseek-chat |
| AC-03 | FR-02, US-03 | 有偏好记录时，默认选中上次使用的 provider+model |
| AC-04 | FR-03, US-02 | 手动选择其他 provider+model 并生成，后端以正确 provider 调用 LLM |
| AC-05 | FR-04, US-03 | 成功生成后偏好持久化，下次打开页面自动选中 |
| AC-06 | FR-05, US-06 | /models 接口超时时，前端展示白名单 model + 明确提示"模型列表加载失败，使用默认列表" |
| AC-07 | FR-06, US-04 | 无有效 provider 配置时，"生成"按钮禁用 + 展示引导提示 |
| AC-08 | FR-07, US-07 | Content 表记录 provider+model，前端列表不展示 |
| AC-09 | FR-08 | `.first()` 替换为显式 service_type 查找，兜底按 -updated_at |

---

## 风险与开放点

### RISK-01：Ark /models 假阳性（高）

**描述**：火山引擎 Ark `/v3/models` 接口验权通过，不代表返回的 model ID 可真正用于文案生成。白名单中的 doubao model ID 含日期后缀，版本更新后旧 ID 失效。

**缓解措施**（必须在设计阶段确认）：
1. 后端拉取 /models 后，对非白名单的 ID 进行业务端点冒烟测试后方可展示
2. 或：仅展示白名单 ID，不展示动态拉取结果（降级方案）
3. CI 增加守卫测试，定期验证白名单 model ID 的真实可用性
4. 参考：`project_workspace/content_gen_platform/docs/requirements/doubao_image_migration/` 中的 Ark key 管理经验

### RISK-02：用户偏好与 key 撤销后的同步问题（中）

**描述**：用户偏好记录了某 provider，但用户事后在设置页面删除该 provider 配置或重置 key（last_test_ok 变 False）。偏好记录若未同步清理，下次默认值会指向已失效的 provider。

**缓解措施**：在 provider 列表查询时，将偏好与当前有效 provider 列表做交集，偏好失效时回退到 FR-LLM-SEL-02 规则 2

### RISK-03：动态 /models 拉取的并发与缓存策略（低-中）

**描述**：若用户配置了多个 provider，页面刷新时会并发请求多个 /models 接口，存在延迟叠加和重复请求问题。

**缓解措施**：后端对每个 provider 的 /models 结果按 `(user_id, service_type)` 缓存（TTL=5min），前端合并为单次聚合请求 `/api/v1/llm/providers/`（含 model 列表）

### OPEN-01：用户偏好的存储结构

设计阶段待确认：是新建 `UserLLMPreference` 表，还是在 `UserServiceConfig` 表中新增 `last_used_model` 字段？后者更简单但语义上混用了"服务配置"与"使用偏好"。

### OPEN-02：Ark model ID 白名单更新机制

白名单需要定期更新，但目前无自动化机制。设计阶段需确认：白名单以配置文件/代码常量/DB 配置表哪种方式存储，以便运维人员更新时不需要发版。
