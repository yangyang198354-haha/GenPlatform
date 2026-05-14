# 架构设计文档增量补丁：API Key 配置 UX 修复

**文档编号**：ARCH-DES-IMG-001-PATCH  
**基准版本**：v1.0（ARCH-DES-IMG-001，已决稿，2026-05-13）  
**本补丁版本**：v1.1  
**创建日期**：2026-05-14  
**最后更新**：2026-05-14  
**状态**：DRAFT — 等待 PM 门控评审  
**输入文档**：REQ-SPEC-IMG-001-PATCH v0.3（APPROVED）、REQ-US-IMG-001 US-08（APPROVED）  
**作者**：system-architect 子代理（由 PM 编排）  
**阅读方式**：本文档为**增量补丁**，不重写 v1.0 内容。阅读时须与 ARCH-DES-IMG-001 v1.0 联合使用。ADR-01 至 ADR-07 继续有效，本补丁仅新增 ADR-08、ADR-09、ADR-10，以及对高层架构的最小化修订。

---

## 一、变更摘要

| 变更类型 | 内容 | 关联需求 |
|---------|------|---------|
| **新增** | ADR-08：测试连接 endpoint 选择（OQ-6=B 落地） | FR-6.3、US-08 AC-08-3 |
| **新增** | ADR-09：Banner 状态查询方案 | FR-7.1、US-08 AC-08-1/08-4 |
| **新增** | ADR-10：自动保存事务一致性（OQ-8=A 落地） | FR-6.1/6.3、US-08 AC-08-3/08-4 |
| **修订** | §1.1 高层架构图：在 settings_vault 层增加两个新视图 | FR-6.3、FR-7.1 |
| **修订** | ADR-06 影响一节勘误：settings_vault 确实需要新增视图（v0.3 补丁已说明） | FR-6、FR-7 |
| **不变** | ADR-01、ADR-02、ADR-03、ADR-04、ADR-05、ADR-07 全部内容 | — |

---

## 二、高层架构修订（§1.1 补丁）

> v1.0 §1.1 架构分层图继续有效，以下仅补充新增的 settings_vault 层变化。

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层（Vue 3 + Element Plus）            │
│  【新增】SettingsView.vue → DoubaoImageKeyPanel.vue             │
│  【新增】ImageGeneratorView.vue → PreflightBanner.vue           │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────────┐
│                     Django REST 层（新增端点）                    │
│  settings_vault/views.py:                                        │
│    【新增】ServiceStatusView  GET  /services/<type>/status/      │
│    【新增】TestAndSaveView    POST /services/<type>/test-and-save/│
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              验证服务层（新增 ark_validator.py）                  │
│  validate_doubao_key(api_key) → 调用 Ark /api/v3/models         │
└────────────────────────┬────────────────────────────────────────┘
                         │ 调用 Ark /api/v3/models（仅 GET，验权）
┌────────────────────────▼────────────────────────────────────────┐
│              外部服务层（扩展）                                   │
│  原有：POST /api/v3/images/generations（生图）                   │
│  【新增】GET /api/v3/models（验权，零费用）                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、新增架构决策记录

---

### ADR-08：测试连接 endpoint 选择

**文档状态**：新增（v1.1）  
**关联需求**：FR-6.3、US-08 AC-08-3、OQ-6=B（用户已决）

**背景**：FR-6.3 要求后端 `_test_connection()` 的 `doubao_image` 分支能真实验证 Ark API Key 的有效性。OQ-6=B 决策要求"调用 Ark 非生图接口验权，零生图费用"。需决定具体调用哪个接口以及如何封装验证逻辑。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A（已决）** | 调用 Ark `GET /api/v3/models` 列表接口，以 HTTP 响应状态码判断 Key 有效性 | 零生图费用；可检测 Key 吊销/欠费（401/403）；接口稳定（Ark OpenAI 兼容层标准路由）；实现简单（单次 GET，无请求体） | 严格意义上只验证 API Key 对 Ark 平台的认证，不能区分"有 LLM 权限但无图片权限"（实际上 Ark Key 是平台级 Key，权限不区分接口类型） |
| **B** | 调用 Ark `POST /api/v3/images/generations` 并传入 dry-run 参数（最小 prompt） | 直接验证图片生成权限 | 产生实际图片生成费用；Ark 未提供官方 dry-run 模式；生成结果需处理 |
| **C** | 仅执行前端格式校验（Key 前缀/长度检查） | 零网络调用，最快 | 无法检测 Key 吊销、欠费、权限不足等真实问题；用户保存后仍可能在生图时报错 |

**决策**：选择选项 A — 调用 Ark `GET /api/v3/models` 接口验权。

**理由**：
1. OQ-6=B 明确要求"调用 Ark 非生图接口验权"，选项 A 完整满足。
2. Ark API Key 为平台级 Token，`/api/v3/models` 接口能有效区分"Key 不存在（401）"、"账号欠费/限制（403）"、"网络不可达（5xx）"三类主要故障场景，覆盖用户最常见的配置问题。
3. 实现路径最简：单次 `httpx.get()` + Bearer Token，无请求体构造，无响应解析（只判断状态码）。
4. `/api/v3/models` 是 OpenAI 兼容层标准路由，Ark 长期稳定支持，不会随模型迭代废弃。

**实现约束**：
- 新建 `apps/settings_vault/ark_validator.py`（或放置于 `apps/image_generator/ark_validator.py`，由 module_design_v1.1.md 决定），避免在 settings_vault views 中直接内嵌 HTTP 调用逻辑。
- 函数签名：`validate_doubao_key(api_key: str) -> tuple[bool, str]`，返回 `(is_valid, error_reason)`。
- 调用超时：设置 `timeout=10.0`（秒），防止 Ark 不可达时长时阻塞。
- 禁止在函数参数、日志、异常消息中以任何形式记录 `api_key` 明文。

**错误映射**：

| Ark 响应 | 映射含义 | 返回给前端的 `error` 字段 |
|---------|---------|----------------------|
| HTTP 200 | Key 有效 | 无（`saved: true`） |
| HTTP 401 | Key 无效（不存在或已吊销） | `"ARK_KEY_INVALID"` |
| HTTP 403 | 账号欠费或权限受限 | `"ARK_QUOTA_EXCEEDED"` |
| HTTP 5xx | Ark 服务临时不可达 | `"ARK_UNREACHABLE"` |
| `httpx.TimeoutException` | 请求超时 | `"ARK_UNREACHABLE"` |
| `httpx.ConnectError` | 网络不可达 | `"ARK_UNREACHABLE"` |

**影响**：
- `apps/settings_vault/ark_validator.py`：新增（见 module_design_v1.1.md §2.1）
- `apps/settings_vault/views.py`：新增 `TestAndSaveView`，内部调用 `validate_doubao_key()`（见 ADR-10）
- `apps/settings_vault/models.py`：`_required_keys()` 和 `_test_connection()` 分支补充（见 module_design_v1.1.md §2.3）
- ADR-01 至 ADR-07：不变

---

### ADR-09：Banner 状态查询方案

**文档状态**：新增（v1.1）  
**关联需求**：FR-7.1、US-08 AC-08-1/AC-08-4

**背景**：FR-7.1 要求前端在进入 `ImageGeneratorView` 时，能查询当前用户的 `doubao_image` Key 配置状态（`is_configured`），并据此决定是否展示预检 Banner。需决定状态查询的架构方案。

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A（已决）** | 每次进入 `ImageGeneratorView` 时，前端调用专用 `GET /api/v1/users/me/services/doubao_image/status/` 接口，获取 `{is_configured, last_validated_at}` | 接口职责单一，无副作用；响应体轻量（仅 2 个字段）；不污染现有 `GET /api/v1/settings/configs/` 接口语义；安全（不返回 Key 值） | 每次进入图片生成页多一次 HTTP 请求（低频页面，可接受） |
| **B** | 登录时一次性获取所有服务状态，写入 Pinia store，后续前端本地读取 | 减少 HTTP 请求次数 | 登录接口需扩展返回字段，污染认证响应；状态可能因 Key 被删除后未及时刷新导致 Banner 不显示（脏状态）；全局 store 状态管理复杂度增加 |
| **C** | `PreflightBanner.vue` 组件懒加载时独立调用 `GET /api/v1/settings/configs/?service_type=doubao_image`，从现有配置接口解析 `is_configured` | 复用现有接口 | 现有 `settings/configs/` 接口返回加密配置，前端需额外解析；接口语义耦合（配置管理 vs. 状态查询）；若接口变更影响面扩大 |

**决策**：选择选项 A — 新增专用 `ServiceStatusView`，端点 `GET /api/v1/users/me/services/{service_type}/status/`。

**理由**：
1. 接口职责单一：状态查询与配置 CRUD 解耦，`status` 端点只回答"是否已配置"，不返回任何 Key 内容（满足安全自检要求）。
2. 响应体极轻量（`is_configured: bool` + `last_validated_at: datetime | null`），前端无需解析复杂对象。
3. 专用接口便于后续扩展（如加入 `key_expires_at`、`quota_remaining` 等字段）而不影响已有接口。
4. 选项 B 的 store 脏状态风险在 OQ-7=A（Banner 常驻）场景下尤为危险：若登录时缓存了旧状态（已配置），即使 Key 后来被删除，Banner 也不会重新显示。

**安全约束**：
- `ServiceStatusView` 响应体**严禁**包含 `api_key` 值、Key 前缀、Key 哈希值或任何派生信息。
- 响应体仅包含：`is_configured`（bool）和 `last_validated_at`（datetime | null，即最近一次成功验证时间）。
- 接口须登录鉴权（`IsAuthenticated` permission class），仅返回当前登录用户的状态。

**Banner 消失时机**：
- 前端从设置页完成 `test-and-save/` 操作后（成功响应），在页面路由回 `ImageGeneratorView` 时，`onMounted` 重新调用 `status/` 接口。
- 若 `is_configured=true`，Banner 不渲染（v-if 控制）。
- 不使用轮询；不使用 WebSocket 推送 Key 状态变更（频率极低，过度设计）。

**影响**：
- `apps/settings_vault/views.py`：新增 `ServiceStatusView`（见 module_design_v1.1.md §2.1）
- `apps/settings_vault/serializers.py`：新增 `ServiceStatusSerializer`
- `apps/settings_vault/urls.py`：新增路由
- `src/views/ImageGeneratorView.vue`：`onMounted` 调用 `status/` 接口
- `src/components/ImageGenerator/PreflightBanner.vue`：新增组件，v-if 绑定 `is_configured`
- ADR-01 至 ADR-07：不变

---

### ADR-10：自动保存事务一致性

**文档状态**：新增（v1.1）  
**关联需求**：FR-6.1、FR-6.3、US-08 AC-08-3/AC-08-4、OQ-8=A（用户已决）

**背景**：OQ-8=A 决策要求"测试成功即自动保存 Key，一步完成"。核心架构问题是：测试（调用 Ark `/api/v3/models`）和保存（写入 `UserServiceConfig` 加密存储）两步操作，是否由同一个 endpoint 在事务中原子完成？如何保证测试失败时 Key 不被写入？

**选项对比**：

| 选项 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A（已决）** | 合并为单一 `POST /api/v1/users/me/services/doubao_image/test-and-save/`，在 Django view 中：先调用 `validate_doubao_key()`，验证通过后在**同一数据库事务**中写入 `UserServiceConfig`；验证失败则不写入，直接返回 400 | 原子保证：验证失败时数据库无脏写；操作步骤最少；前端逻辑最简（一次 POST 即知结果）；与 OQ-8=A 完全一致 | 单 endpoint 承担验证+存储两种职责（但这正是 OQ-8=A 要求的语义） |
| **B** | 先调用 `POST /services/<type>/test/` 返回验证结果，前端判断通过后再调用 `POST /services/<type>/save/` | 职责更分离 | 两次 HTTP 往返；测试通过到保存之间存在时间窗口（Key 可能在此期间失效）；不符合 OQ-8=A"一步完成"决策 |
| **C** | 仅 `POST /services/<type>/save/`，内部隐式调用验证（save 时自动测试） | 接口名语义直接 | "保存"语义对用户不透明（用户不知道保存时会自动测试）；与 OQ-8=A"测试即保存"的 UX 意图方向相反（按钮文字应是"测试连接"而非"保存"） |

**决策**：选择选项 A — `POST /api/v1/users/me/services/doubao_image/test-and-save/`，原子事务。

**理由**：
1. OQ-8=A 决策原文"测试成功后自动保存 Key（测试即保存，一步完成）"，选项 A 是该决策在 API 层的唯一一致实现。
2. 原子事务保证不产生脏数据：若 Ark 返回 401（Key 无效），Django view 不进入写入逻辑，数据库状态不变。
3. 避免"测试通过 → 保存失败 → 用户重试 → 重新测试"的循环，提升用户体验一致性。
4. 与 ADR-08 的 `validate_doubao_key()` 函数天然结合：`TestAndSaveView.post()` → `validate_doubao_key()` → 通过后 `with transaction.atomic(): UserServiceConfig.objects.update_or_create(...)`。

**事务边界**：

```
POST /api/v1/users/me/services/doubao_image/test-and-save/
  request body: {"api_key": "<用户输入>"}
  
  1. Serializer 校验（api_key 非空，格式预检）
  2. validate_doubao_key(api_key)
     → 失败：return 400 {"error": "ARK_KEY_INVALID" | "ARK_QUOTA_EXCEEDED" | "ARK_UNREACHABLE", "detail": "..."}
     → 成功：继续
  3. with transaction.atomic():
       UserServiceConfig.objects.update_or_create(
           user=request.user,
           service_type="doubao_image",
           defaults={"encrypted_config": encrypt({"api_key": api_key})}
       )
  4. return 200 {"saved": true, "last_validated_at": "<ISO8601>"}
  
  注意：api_key 在步骤 3 完成后立即从内存变量清理（Python GC），
        不出现在任何日志、响应体、异常消息中。
```

**安全约束**：
- `request.data["api_key"]` 通过 `TestAndSaveSerializer` 校验后立即传给 `validate_doubao_key()`，不做任何日志记录。
- 响应体只包含 `{saved: true, last_validated_at: "..."}` 或错误码，**不返回** api_key 值（包括掩码）。
- 前端收到 200 后，重新调用 `GET /services/doubao_image/status/` 更新本地 `is_configured` 状态（或直接在前端将 `is_configured` 置为 `true`）。

**影响**：
- `apps/settings_vault/views.py`：新增 `TestAndSaveView`（见 module_design_v1.1.md §2.1）
- `apps/settings_vault/serializers.py`：新增 `TestAndSaveSerializer`（含 `api_key` 字段校验）
- `apps/settings_vault/urls.py`：新增路由
- `apps/settings_vault/ark_validator.py`：被 `TestAndSaveView` 调用
- 前端 `DoubaoImageKeyPanel.vue`：点击"测试连接"调用此端点，无独立保存按钮
- ADR-01 至 ADR-07：不变

---

## 四、ADR-06 影响一节勘误（v1.1 修订）

> 以下内容**修订** v1.0 ADR-06 的"影响"一节最后一条：

**v1.0 原文**（有误）：
> `settings_vault` 视图/序列化器：无需新增，现有通用 CRUD 接口已支持任意 `service_type`。

**v1.1 修正**：
> `settings_vault` 视图/序列化器：**需要新增以下内容**（v0.3 需求补丁已识别并说明）：
> - `ServiceStatusView` — `GET /services/{service_type}/status/`（ADR-09）
> - `TestAndSaveView` — `POST /services/{service_type}/test-and-save/`（ADR-10）
> - `ServiceStatusSerializer`、`TestAndSaveSerializer`
>
> 原判断"现有通用 CRUD 接口已支持"仅对 Key 存取 CRUD 成立，但对"验权+原子保存"和"状态轻量查询"两个新语义端点不成立。此勘误不影响 ADR-06 的核心决策（复用 `UserServiceConfig` 表 + AES-256-GCM 加密），仅修正实施范围低估。

---

## 五、补丁文档引用关系

```
ARCH-DES-IMG-001 v1.0（基准，已决稿）
  └── ARCH-DES-IMG-001-PATCH v1.1（本文档，增量补丁）
        ├── 新增：ADR-08（测试连接 endpoint 选择，OQ-6=B 落地）
        ├── 新增：ADR-09（Banner 状态查询，FR-7.1 落地）
        ├── 新增：ADR-10（自动保存事务一致性，OQ-8=A 落地）
        └── 修订：ADR-06 影响一节勘误

ARCH-MOD-IMG-001 v1.0（模块设计基准）
  └── ARCH-MOD-IMG-001-PATCH v1.1（module_design_v1.1.md，模块增量）
        └── 实现 ADR-08/09/10 所定义的模块、类、接口
```

---

*文档版本 v1.1，状态 DRAFT，等待 PM 门控评审。*  
*若 PM 门控 PASS，此文档状态升级为 APPROVED，可进入 GROUP_C 开发阶段。*
