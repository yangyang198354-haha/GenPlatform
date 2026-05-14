# 实施计划（增量补丁）：API Key 配置 UX 修复

**文档编号**：DEV-IMPL-IMG-001-PATCH
**版本**：v1.1
**创建日期**：2026-05-14
**状态**：DRAFT — GROUP_C 实施中
**作者**：software-developer 子代理（由 PM 编排）
**输入文档**：
  - ARCH-MOD-IMG-001-PATCH v1.1（PASS，module_design_v1.1.md）
  - REQ-SPEC-IMG-001-PATCH v0.3（APPROVED，requirements_spec_v0.3.md）
  - user_stories.md（APPROVED，US-08）

---

## 一、变更范围

本实施计划为**增量补丁**，仅覆盖 v1.1 架构设计中新增/修改的文件。
基准 v1.0（豆包 Seedream 主功能）已上线，本轮不修改其已有实现逻辑。

---

## 二、任务拆分

### T1 — 后端：`apps/settings_vault/ark_validator.py`（新增）

| 项 | 值 |
|---|---|
| 文件 | `apps/settings_vault/ark_validator.py` |
| 类型 | 新增 |
| 关联需求 | FR-6.3、US-08 AC-08-3、ADR-08 |
| 预估工时 | 1h |
| 依赖 | 无（独立验证模块） |
| 核心实现 | `validate_doubao_key(api_key: str) -> tuple[bool, str]` |
| 关键约束 | 仅对网络错（TimeoutException/ConnectError）用 tenacity 重试（共 3 次）；401/429 立即返回；api_key 不入日志 |

**状态**：DONE

---

### T2 — 后端：`apps/settings_vault/models.py`（修改）

| 项 | 值 |
|---|---|
| 文件 | `apps/settings_vault/models.py` |
| 类型 | 修改（新增字段 + 新增方法） |
| 关联需求 | FR-6.3、ADR-08、ADR-10 |
| 预估工时 | 0.5h |
| 依赖 | T1（`_test_connection()` 调用 `ark_validator`） |
| 变更内容 | 新增 `last_validated_at` 字段；补 `_required_keys()` doubao_image 分支；补 `_test_connection()` doubao_image 分支 |

**状态**：DONE

---

### T3 — 后端：`apps/settings_vault/serializers.py`（新增）

| 项 | 值 |
|---|---|
| 文件 | `apps/settings_vault/serializers.py` |
| 类型 | 新增文件 |
| 关联需求 | FR-6.3、FR-7.1、ADR-09、ADR-10 |
| 预估工时 | 0.5h |
| 依赖 | 无 |
| 变更内容 | `ServiceStatusSerializer`（read_only）；`TestAndSaveSerializer`（api_key write_only） |
| 安全约束 | api_key write_only=True；错误消息不 echo Key 内容 |

**状态**：DONE

---

### T4 — 后端：`apps/settings_vault/views.py`（修改，新增 View）

| 项 | 值 |
|---|---|
| 文件 | `apps/settings_vault/views.py` |
| 类型 | 修改（原有 View 不变，追加新 View） |
| 关联需求 | FR-6.1、FR-6.3、FR-7.1、ADR-09、ADR-10 |
| 预估工时 | 1.5h |
| 依赖 | T1（validate_doubao_key）、T3（serializers） |
| 变更内容 | 新增 `ServiceStatusView`（GET，IsAuthenticated）；新增 `TestAndSaveView`（POST，transaction.atomic） |
| 安全约束 | status 响应体字段穷举仅 is_configured/last_validated_at；TestAndSaveView 中 api_key 不入日志/响应 |

**状态**：DONE

---

### T5 — 后端：`apps/settings_vault/urls.py`（修改）

| 项 | 值 |
|---|---|
| 文件 | `apps/settings_vault/urls.py` |
| 类型 | 修改（原有路由不变，追加新路由） |
| 关联需求 | ADR-09、ADR-10 |
| 预估工时 | 0.25h |
| 依赖 | T4 |
| 变更内容 | 新增 `users/me/services/<service_type>/status/` 和 `users/me/services/<service_type>/test-and-save/` 路由 |
| 最终 URL | `/api/v1/settings/users/me/services/doubao_image/status/` 和 `.../test-and-save/` |

**状态**：DONE

---

### T6 — 前端：`src/api/index.js`（修改）

| 项 | 值 |
|---|---|
| 文件 | `src/api/index.js` |
| 类型 | 修改（settingsAPI 对象新增两个函数） |
| 关联需求 | FR-6.3、FR-7.1、ADR-09、ADR-10 |
| 预估工时 | 0.25h |
| 依赖 | T5（后端路由） |
| 变更内容 | `settingsAPI.getServiceStatus(serviceType)`；`settingsAPI.testAndSaveServiceKey(serviceType, apiKey)` |

**状态**：DONE

---

### T7 — 前端：`src/components/Settings/DoubaoImageKeyPanel.vue`（新增）

| 项 | 值 |
|---|---|
| 文件 | `src/components/Settings/DoubaoImageKeyPanel.vue` |
| 类型 | 新增文件 |
| 关联需求 | FR-6.1、FR-6.2、US-08 AC-08-2/AC-08-3 |
| 预估工时 | 1.5h |
| 依赖 | T6（API 函数） |
| 关键 UI 元素 | el-input type="password" + show-password；el-button "测试并保存"（无独立保存按钮，OQ-8=A）；el-alert info 引导文案（FR-6.2）；错误码→中文映射（FR-7.2） |

**状态**：DONE

---

### T8 — 前端：`src/views/SettingsView.vue`（修改）

| 项 | 值 |
|---|---|
| 文件 | `src/views/SettingsView.vue` |
| 类型 | 修改（新增 Tab + 导入新组件 + 状态管理） |
| 关联需求 | FR-6.1、US-08 AC-08-4 |
| 预估工时 | 1h |
| 依赖 | T6（API）、T7（组件） |
| 变更内容 | 新增"豆包图片生成"el-tab-pane（name="doubao_image"）；URL query `?tab=doubao_image` 自动激活；doubaoImageStatus 响应式状态；onDoubaoImageConfigured 回调 |

**状态**：DONE

---

### T9 — 前端：`src/components/ImageGenerator/PreflightBanner.vue`（新增）

| 项 | 值 |
|---|---|
| 文件 | `src/components/ImageGenerator/PreflightBanner.vue` |
| 类型 | 新增文件 |
| 关联需求 | FR-7.1、US-08 AC-08-1/AC-08-2、OQ-7=A |
| 预估工时 | 0.5h |
| 依赖 | 无（纯展示组件） |
| 关键约束 | el-alert `:closable="false"`（OQ-7=A 锁定）；el-button "前往配置" → router.push `/settings?tab=doubao_image` |

**状态**：DONE

---

### T10 — 前端：`src/views/ImageGeneratorView.vue`（修改）

| 项 | 值 |
|---|---|
| 文件 | `src/views/ImageGeneratorView.vue` |
| 类型 | 修改（新增预检逻辑 + PreflightBanner 集成） |
| 关联需求 | FR-7.1、US-08 AC-08-1/AC-08-4 |
| 预估工时 | 1h |
| 依赖 | T6（API）、T9（组件） |
| 变更内容 | `doubaoIsConfigured` 响应式变量（默认 true 防止闪烁）；`fetchDoubaoStatus()` 函数；`onMounted` + `onActivated` 均调用（刷新 Banner 状态）；`<PreflightBanner v-if="!doubaoIsConfigured" />` |

**状态**：DONE

---

### T11 — 前端：`src/views/ImageGeneratorView.vue`（修改，错误提示增强）

| 项 | 值 |
|---|---|
| 文件 | `src/views/ImageGeneratorView.vue`（与 T10 同一文件） |
| 类型 | 修改（submitGeneration 错误处理增强） |
| 关联需求 | FR-7.2、US-08 AC-08-3 |
| 预估工时 | 0.5h |
| 依赖 | T6 |
| 变更内容 | ARK_KEY_INVALID/DOUBAO_IMAGE_NOT_CONFIGURED/含"未配置"的错误 → ElMessageBox.confirm 弹出"前往配置"选项（点击后 router.push /settings?tab=doubao_image） |

**状态**：DONE

---

### 测试（各 Task 并行进行）

| 文件 | 覆盖范围 | 状态 |
|------|---------|------|
| `test_ark_validator.py` | validate_doubao_key 7 种场景 + 安全 Canary | DONE |
| `test_service_status_view.py` | ServiceStatusView 6 种场景 + 安全守卫 | DONE |
| `test_test_and_save_view.py` | TestAndSaveView 12 种场景 + 安全守卫 + 用户隔离 | DONE |

---

## 三、文件变更清单

### 后端（新增/修改）

| 文件路径 | 变更类型 | 关联 ADR |
|---------|---------|---------|
| `apps/settings_vault/ark_validator.py` | 新增 | ADR-08 |
| `apps/settings_vault/serializers.py` | 新增 | ADR-09/10 |
| `apps/settings_vault/models.py` | 修改（新增字段+方法） | ADR-08/10 |
| `apps/settings_vault/views.py` | 修改（新增 2 View） | ADR-09/10 |
| `apps/settings_vault/urls.py` | 修改（新增 2 路由） | ADR-09/10 |
| `apps/settings_vault/migrations/0003_userserviceconfig_last_validated_at.py` | 新增 | ADR-10 |
| `apps/settings_vault/tests/test_ark_validator.py` | 新增 | ADR-08 |
| `apps/settings_vault/tests/test_service_status_view.py` | 新增 | ADR-09 |
| `apps/settings_vault/tests/test_test_and_save_view.py` | 新增 | ADR-10 |

### 前端（新增/修改）

| 文件路径 | 变更类型 | 关联需求 |
|---------|---------|---------|
| `src/api/index.js` | 修改（新增 2 函数） | FR-6.3/FR-7.1 |
| `src/components/Settings/DoubaoImageKeyPanel.vue` | 新增 | FR-6.1/6.2 |
| `src/components/ImageGenerator/PreflightBanner.vue` | 新增 | FR-7.1 |
| `src/views/SettingsView.vue` | 修改（新增 Tab + 导入 + 状态） | FR-6.1 |
| `src/views/ImageGeneratorView.vue` | 修改（预检 + Banner + 错误提示） | FR-7.1/7.2 |

---

## 四、依赖关系图

```
T1(ark_validator)
    ↓
T2(models.py)
T3(serializers.py)
    ↓
T4(views.py) ←─────── T1、T3
    ↓
T5(urls.py)
    ↓
T6(api/index.js)
    ↓
T7(DoubaoImageKeyPanel.vue)  T9(PreflightBanner.vue，无依赖)
    ↓                             ↓
T8(SettingsView.vue) ←── T6、T7  T10/T11(ImageGeneratorView.vue) ←── T6、T9
```

---

## 五、迁移说明

`0003_userserviceconfig_last_validated_at.py`：
- 新增 `last_validated_at` 可空 DateTimeField，默认值 NULL
- 对现有数据无影响（现有行的该字段值为 NULL，含义为"尚未通过新版 test-and-save 验证"）
- 回滚：删除该列，现有加密配置数据不受影响

---

## 六、未决/待后续处理事项

| 编号 | 内容 | 优先级 | 说明 |
|------|------|--------|------|
| TODO-01 | `onActivated` 在非 keep-alive 路由下不触发 | LOW | 可改用 `beforeRouteEnter` 守卫补充覆盖，当前 `onMounted` 已能覆盖主流程 |
| TODO-02 | ServiceStatusView 支持其他 service_type 的配置状态查询 | LOW | 当前仅 doubao_image 有 last_validated_at 字段，其他类型通过此接口只返回 is_configured |
| TODO-03 | 前端 DoubaoImageKeyPanel 的 initialConfigured prop 初始化时序 | LOW | 如果 SettingsView onMounted 异步查询尚未完成就渲染 Panel，会短暂显示"未配置"状态 |

---

*文档版本 v1.1，2026-05-14*
