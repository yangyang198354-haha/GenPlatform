# 技术选型表：豆包 Seedream 图片生成接入

**文档编号**：ARCH-TECH-IMG-001  
**版本**：v1.0  
**创建日期**：2026-05-13  
**状态**：DRAFT  
**输入文档**：REQ-SPEC-IMG-001 v0.2、ARCH-DES-IMG-001 v1.0  
**作者**：system-architect 子代理（由 PM 编排）

---

## 一、现有技术栈确认（无变更）

| 组件 | 版本（生产） | 本次迁移是否变更 |
|------|-----------|--------------|
| Python | 3.12 | 否 |
| Django | 4.2.x | 否 |
| Django REST Framework | 3.14.x | 否 |
| Celery | 5.x | 否（task 结构改造，框架不变） |
| Redis | 7.x（Broker + Cache） | 否 |
| PostgreSQL | 15.x | 否（新增表和字段，引擎不变） |
| Django Channels | 4.x | 否（复用 WebSocket 推送机制） |
| httpx | 0.27.x | 否（现有依赖，DoubaoImageClient 直接使用） |
| Vue 3 | 3.4.x | 否 |
| Element Plus | 2.x | 否 |
| Vite | 5.x | 否 |

---

## 二、新增依赖

### 2.1 后端新增依赖

| 包名 | 建议版本 | 用途 | 引入原因 | 备选方案 |
|------|---------|------|---------|---------|
| `tenacity` | `>=8.2.0,<9.0` | HTTP 调用层自动重试（指数退避、网络错误重试） | 现有代码无统一重试基础设施；`tenacity` 是 Python 重试库事实标准，零依赖，API 简洁 | `stamina`（更轻量，但功能有限）；手写 for 循环（不够 DRY，ADR-07 要求可配置重试策略） |

**否决方案**：
- `openai` SDK：接口兼容，但引入后与现有手写 HTTP 风格不一致，且 SDK 对 Ark 扩展参数的支持不确定（ADR-01 已决）。
- `volcengine-python-sdk`：图片接口支持不完整，SDK 维护频率低（ADR-01 已决）。

### 2.2 前端新增依赖

| 包名 | 建议版本 | 用途 | 引入原因 |
|------|---------|------|---------|
| 无新增 npm 包 | — | — | Element Plus 已包含 el-collapse、el-input-number、el-select、el-upload 等所有所需组件；Pinia 已作为状态管理库存在 |

---

## 三、版本约束

### 3.1 `tenacity` 版本约束说明

```
tenacity>=8.2.0,<9.0
```

- `8.2.0` 引入了 `retry_if_exception_type` 的改进 API，本项目使用该 API。
- 锁定 `<9.0` 避免 major 版本升级时的 API 破坏性变更（tenacity 历史上有两次 major breaking change）。

### 3.2 httpx 版本约束说明

`httpx` 已在 `requirements.txt` 中，本次无需修改版本约束。`DoubaoImageClient` 使用同步 `httpx.Client`（非异步），与 Celery task 的同步执行上下文一致。

> 说明：现有 `JimengImageClient` 和 `VolcanoProvider` 使用 `asyncio.run()` 包裹异步 httpx 调用。本次 `DoubaoImageClient` 改为直接使用同步 `httpx.Client`，无需 `asyncio.run()`，更简洁，也避免了 Celery 中嵌套事件循环的潜在问题（这是现有代码的一个技术债，本次顺带修复）。

---

## 四、安全与合规

### 4.1 API Key 存储方案

| 项目 | 方案 | 说明 |
|------|------|------|
| 加密算法 | AES-256-GCM | 复用现有 `core.encryption` 模块，对称加密，密钥由 `settings.SECRET_KEY` 派生（PBKDF2） |
| 存储位置 | `settings_service_config.encrypted_config`（BinaryField） | 与 `llm_deepseek`、`llm_volcano` 等现有服务 Key 存储方式完全一致 |
| 传输 | HTTPS only（生产环境强制 HTTPS，Django `SECURE_SSL_REDIRECT=True`） | Key 不出现在 URL、日志、错误响应 |
| 展示（前端） | 掩码显示（`ark-***...`），不回传明文 | AC-07-1 |
| 访问控制 | 仅 Celery task 内部通过 `core.encryption.decrypt` 访问；Django View 层不接触明文 Key | 最小权限原则 |

### 4.2 日志安全

| 项目 | 约束 |
|------|------|
| Celery task 日志 | 记录 `model`, `batch_id`, `task_id`, 耗时，成功/失败原因；**禁止**记录 API Key、prompt 全文（可记录 prompt 前 30 字） |
| Django 请求日志 | 记录提交用户 ID、模型选择、是否图生图、生成张数；**禁止**记录参考图 base64 内容 |
| httpx 日志级别 | 设置为 WARNING 以上，避免 httpx 默认 DEBUG 日志输出请求头（含 Authorization） |

**httpx 日志配置（须在 Django settings.py 中设置）**：

```python
LOGGING = {
    ...
    "loggers": {
        "httpx": {"level": "WARNING", "handlers": ["console"]},
        "httpcore": {"level": "WARNING", "handlers": ["console"]},
    }
}
```

### 4.3 内容审核策略

| 场景 | 处理方式 |
|------|---------|
| Ark 内容审核拒绝（HTTP 400 + content_filter 错误码） | 任务置 `failed`，用户提示"提示词包含不允许的内容"；不暴露 Ark 原始错误信息 |
| 参考图内容审核（Ark 侧） | 同上处理 |
| 前端 prompt 预校验 | 不在前端做内容审核（无法覆盖所有情况，后端 Ark 响应是权威来源） |

### 4.4 参考图临时文件安全

| 项目 | 方案 |
|------|------|
| 存储路径 | `settings.MEDIA_ROOT/temp/{uuid}/ref.jpg`（与现有逻辑相同） |
| 清理时机 | Celery task 中 `try/finally` 保证无论成功失败均清理（AC-02-5） |
| 权限 | 临时目录权限 600，仅 worker 进程可读 |

---

## 五、已选方案 vs 被否决方案对照表

### 5.1 HTTP 客户端选型

| 方案 | 结论 | 理由 |
|------|------|------|
| `httpx`（同步 Client）| **已选** | 现有依赖；Celery 同步上下文天然适配；无 asyncio 嵌套问题 |
| `openai` Python SDK | **否决** | 引入新依赖；与项目手写 HTTP 风格不一致；SDK 对 Ark 扩展参数支持存疑 |
| `requests` | **否决** | 项目已统一使用 httpx，不引入第二个 HTTP 客户端 |
| `volcengine-python-sdk` | **否决** | 图片接口支持不完整；SDK 依赖重；维护不活跃 |

### 5.2 重试机制选型

| 方案 | 结论 | 理由 |
|------|------|------|
| `tenacity` | **已选** | Python 重试库标准选择；API 简洁；支持类型级重试过滤 |
| Celery `self.retry()` | **否决** | Ark 为同步接口，失败后重入队列延迟过长（默认 3 分钟）；不适合"最多重试 1 次，5 秒后"的需求 |
| 手写 for 循环 | **否决** | 代码重复，不可配置，与 ADR-07 的分类重试策略难以结合 |
| `stamina` | **备选**（未选）| 更轻量，但 API 略有不同；tenacity 在团队中更熟悉 |

### 5.3 批次多张图片生成策略

| 方案 | 结论 | 理由 |
|------|------|------|
| 单次 Celery task，Ark `n` 参数一次返回多张 | **已选（首选）** | Ark 接口支持 `n` 参数（1-4）；一次 HTTP 请求最高效；Celery 任务数最少 |
| 每张图片独立 Celery task | **已选（降级）** | 当 Ark 不支持 `n > 1` 时启用；通过 `settings.DOUBAO_BATCH_MODE` 切换 |
| 前端分 n 次请求 | **否决** | 批次概念在后端管理；前端多次请求竞态处理复杂 |

### 5.4 高级参数差异兼容

| 方案 | 结论 | 理由 |
|------|------|------|
| 后端维护模型参数白名单，按模型过滤 | **已选** | 前端无感知；参数兼容逻辑集中于 `doubao_image_client.py`；未来新增模型只改常量 |
| 前端按模型动态渲染参数 | **否决** | 需新增"模型能力查询"API，实现复杂度过高 |
| 全量透传，由 Ark 忽略 | **否决** | Ark 可能对未知参数返回 400（不稳定） |

### 5.5 即梦代码处置

| 方案 | 结论 | 理由 |
|------|------|------|
| 保留文件，停止调用（ADR-02 选项 A） | **已选** | 符合 OQ-1 原文；回滚成本低；与 video_generator jimeng_client 并存无混淆 |
| 物理删除 | **否决** | 增加回滚成本；git 历史仍存在 |
| 标记 `@deprecated` | **否决** | 无实际约束力；增加维护心智负担 |

---

## 六、依赖更新说明

**`requirements.txt` 新增行**：

```
tenacity>=8.2.0,<9.0
```

**无需更新的依赖**：
- `httpx`：已存在，版本无需变更
- 所有前端 npm 包：无新增

---

*文档版本 v1.0，状态 DRAFT，等待 PM 门控评审。*
