<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-04-06T00:11:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files><file>requirements/requirements_spec.md (APPROVED)</file></input_files>
  <phase>PHASE_03</phase>
  <status>APPROVED</status>
</file_header>

# 架构设计说明书 — 内容生成平台

---

## ADR-001：整体应用架构模式

**决策点**：选择单体 vs 前后端分离 vs 微服务？

**选项 A — 前后端分离单体（Django + Vue SPA）**
- 优势：开发效率高，部署简单，满足 REQ-NFUNC-001 的 Django+Vue 约束
- 劣势：水平扩展时后端整体扩容，模块耦合度较高
- 后果（正）：快速交付，运维成本低
- 后果（负）：高并发时扩展粒度不精细

**选项 B — 微服务架构**
- 优势：各模块独立扩展（LLM 生成、视频生成可单独扩容）
- 劣势：初期开发成本高，需要服务治理（API Gateway、服务发现），违背 REQ-NFUNC-001 的 Django 约束
- 后果（正）：极强的扩展性
- 后果（负）：开发/运维复杂度大幅提升

**选择：选项 A — 前后端分离单体**
**理由**：REQ-NFUNC-001 明确约束 Django + Vue；项目初期用户规模不确定；前后端分离 + Celery 异步任务已能解耦 LLM 和视频生成的重型计算，不需要微服务级别的扩展。后续可逐步拆分高负载模块。

---

## ADR-002：知识库向量存储方案

**决策点**：使用什么向量存储为 RAG 提供语义检索？（REQ-FUNC-003）

**选项 A — pgvector（PostgreSQL 扩展）**
- 优势：与主数据库统一，无需额外基础设施，支持 HNSW/IVFFlat 索引，向量查询 < 1s（REQ-NFUNC-004）
- 劣势：超大规模向量（>100万条）时性能不如专用向量数据库

**选项 B — Chroma（嵌入式向量数据库）**
- 优势：轻量，易于集成 LangChain
- 劣势：生产级持久化支持弱，多用户隔离需额外设计

**选项 C — Milvus**
- 优势：高性能向量存储，成熟的多租户支持
- 劣势：独立组件，增加运维成本

**选择：选项 A — pgvector**
**理由**：满足 REQ-NFUNC-004（< 1s 检索），与 PostgreSQL 统一存储减少运维复杂度；用户规模初期向量数量不会超过 pgvector 性能上限；LangChain 提供官方 pgvector 集成。

---

## ADR-003：异步任务处理方案

**决策点**：如何处理 LLM 生成、视频生成、定时发布等重型/长耗时任务？（REQ-FUNC-008, REQ-FUNC-016, REQ-FUNC-012）

**选项 A — Celery + Redis**
- 优势：Django 生态事实标准，支持任务优先级、重试、定时任务（Celery Beat）、任务状态查询
- 劣势：需要 Redis 作为 Broker，多一个依赖组件

**选项 B — Django Q2**
- 优势：无需 Redis，纯 Django ORM
- 劣势：性能不如 Celery，社区成熟度低

**选择：选项 A — Celery + Redis**
**理由**：Celery 是处理视频生成任务（分钟级）、定时发布、LLM 流式调用的最成熟方案；Redis 同时服务缓存和 WebSocket Channel Layer，一个组件多用途。

---

## ADR-004：LLM 流式输出方案

**决策点**：如何将 LLM 流式输出实时推送到前端？（REQ-FUNC-008）

**选项 A — SSE（Server-Sent Events）**
- 优势：HTTP 原生，浏览器内建支持，单向推送（LLM Token 推送场景完美匹配），无需 WebSocket 握手
- 劣势：单向通信，无法接收前端消息

**选项 B — WebSocket（Django Channels）**
- 优势：双向通信，同时可用于通知推送（视频生成完成通知）
- 劣势：文案生成场景只需单向推送，WebSocket 过重；前端维护长连接成本较高

**选择：选项 A（SSE）用于文案生成，选项 B（WebSocket）用于通知推送**
**理由**：文案生成为单向 Token 流，SSE 更简洁高效；视频生成完成通知、发布状态更新为双向，Django Channels WebSocket 处理这类事件通知。

---

## ADR-005：文件存储方案

**决策点**：如何存储用户上传的文档和生成的视频文件？（REQ-FUNC-002, REQ-FUNC-016, REQ-NFUNC-004）

**选项 A — MinIO（自托管对象存储）**
- 优势：兼容 S3 API，可扩展，支持私有化部署，用户配额控制方便
- 劣势：需要独立部署 MinIO 服务

**选项 B — 本地文件系统（Django MEDIA_ROOT）**
- 优势：零额外依赖，开发简单
- 劣势：不适合生产级别（单点故障，难扩展）

**选择：选项 A — MinIO，开发环境降级为本地文件系统（可配置切换）**
**理由**：MinIO 兼容 S3 API，生产环境可无缝迁移到云存储；开发环境通过 `STORAGE_BACKEND` 环境变量切换为本地存储，降低开发门槛。

---

## 系统总体架构图（文字描述）

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                │
│              Vue 3 SPA（Element Plus + Pinia）                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/SSE/WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx 反向代理                                 │
│         静态资源服务 + API 代理 + WebSocket 代理                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Django ASGI Application（Gunicorn+Uvicorn）         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ REST API    │  │ Django       │  │ Celery Workers         │ │
│  │ (DRF)       │  │ Channels     │  │ ┌──────────────────┐   │ │
│  │ /api/v1/    │  │ (WebSocket   │  │ │ LLM Task Worker  │   │ │
│  │             │  │  通知推送)    │  │ │ Video Task Worker│   │ │
│  └──────┬──────┘  └──────┬───────┘  │ │ Publish Worker   │   │ │
│         │                │          │ │ Celery Beat      │   │ │
└─────────┼────────────────┼──────────┤ └──────────────────┘   │ │
          │                │          └────────────────────────┘ │
          ▼                ▼                     │                │
┌─────────────────┐ ┌─────────────┐    ┌─────────▼──────────────┐│
│  PostgreSQL 15  │ │   Redis 7   │    │  外部 API              ││
│  + pgvector     │ │  (Broker +  │    │  DeepSeek / 火山引擎   ││
│  (主数据库 +    │ │   Cache +   │    │  即梦 Jimeng API       ││
│   向量存储)     │ │  Channel     │    │  微博/小红书/公众号    ││
└─────────────────┘ │   Layer)    │    │  视频号/头条 API       ││
                    └─────────────┘    └────────────────────────┘│
                                                                  │
┌─────────────────────────────────────────────────────────────────┘
│  MinIO / 本地文件系统（文档 + 视频文件存储）
└─────────────────────────────────────────────────────────────────
```

---

## 安全架构

1. **认证**：JWT（djangorestframework-simplejwt），Access Token（15分钟）+ Refresh Token（7天）
2. **API Key 存储**：AES-256-GCM 加密，密钥存储在 Django `SECRET_KEY`（生产环境存入环境变量）
3. **用户数据隔离**：所有数据库查询强制绑定 `user_id`（模型级别 FK，API 视图层二次校验）
4. **速率限制**：DRF Throttling，LLM 生成接口 10次/分钟/用户，发布接口 30次/小时/用户
5. **输入校验**：文件上传类型白名单（PDF/DOCX/TXT/MD），文件大小限制（50MB）
