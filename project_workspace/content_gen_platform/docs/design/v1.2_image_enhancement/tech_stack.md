# 技术栈说明 v1.2 — AI 图片功能增强

**file_header**
- document_id: TECH-v1.2
- author_agent: sub_agent_system_architect
- orchestrated_by: main_agent_pm
- project: content_gen_platform
- feature_scope: v1.2 AI 图片功能 4 项调整
- status: DRAFT
- created_at: 2026-05-14

---

## 1. 现有技术栈（不变）

| 层 | 技术 | 版本 |
|----|------|------|
| 后端框架 | Django | 4.2 |
| API 层 | Django REST Framework | 3.x |
| 任务队列 | Celery | 5.x |
| HTTP 客户端 | httpx | 0.2x |
| 重试 | tenacity | 8.x |
| 数据库 | PostgreSQL | 14+ |
| 缓存/MQ | Redis | 6+ |
| 前端框架 | Vue 3 | 3.4+ |
| UI 组件库 | Element Plus | 2.x |
| 构建工具 | Vite | 5.x |
| 测试（后端） | pytest / pytest-django | 7+ |
| 测试（E2E） | Playwright | 1.4x |

---

## 2. v1.2 新增 / 变更依赖

**结论：本次 v1.2 无新增外部依赖。**

| 功能 | 实现方式 | 新增依赖 |
|------|---------|---------|
| SizeNormalizer | 纯 Python（dict 映射） | 无 |
| Serializer 扩展 | 现有 DRF | 无 |
| SizeSelector 组件 | Vue 3 + Element Plus（已有） | 无 |
| GenerationModeSelector | Vue 3 + Element Plus（已有） | 无 |
| Lightbox 图片预览 | Element Plus `el-image` preview 属性（已有） | 无 |
| 即梦 UI 清理 | 代码删除 | 无 |

---

## 3. 技术约束确认

1. **Ark API 认证**：Bearer Token（httpx，已有），不变
2. **加密存储**：AES-256-GCM（`core/encryption`），不变
3. **model ID 格式**：`doubao-xxx-x-y-yymmdd`（含日期后缀），开发期需真调验证
4. **Python 版本**：3.12（不变）
5. **Node 版本**：前端构建环境不变

---

## 4. 开发期验证检查单

开发阶段（software_developer 执行时）需完成以下验证：

| 检查项 | 方法 | 负责方 |
|-------|------|-------|
| Seedream 5.0 Lite 生图端点可用性 | 真调 `doubao-seedream-5-0-260128` | 开发 |
| Seedream 4.5 生图端点可用性 | 真调 `doubao-seedream-4-5-251128` | 开发 |
| Seedream 4.0 生图端点可用性 | 真调 `doubao-seedream-4-0-250828` | 开发 |
| `el-image` preview-src-list 在当前 EP 版本可用 | 查 EP changelog | 开发 |
| size 参数枚举是否与 PDF 实际一致 | 对照 PDF §2.1 重新确认 | 开发（PDF 阅读） |
