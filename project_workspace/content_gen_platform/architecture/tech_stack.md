<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-04-06T00:10:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files><file>requirements/requirements_spec.md (APPROVED)</file></input_files>
  <phase>PHASE_03</phase>
  <status>APPROVED</status>
</file_header>

# 技术栈说明 — 内容生成平台

## 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 主语言 |
| Django | 4.2 LTS | Web 框架 |
| Django REST Framework | 3.15 | RESTful API |
| Django Channels | 4.x | WebSocket/SSE（流式输出） |
| Celery | 5.x | 异步任务队列（视频生成、发布任务） |
| Redis | 7.x | Celery Broker + 缓存 + 任务状态 |
| PostgreSQL | 15+ | 主数据库 |
| pgvector | 0.5+ | 向量存储（知识库 Embedding） |
| LangChain | 0.2+ | RAG 框架（文档分割、Embedding、检索） |
| sentence-transformers | 2.x | 本地 Embedding 模型（bge-m3） |
| cryptography | 41+ | AES-256 加密（API Key 存储） |
| httpx | 0.26+ | 异步 HTTP 客户端（LLM/平台 API 调用） |
| FFmpeg（系统级） | 6.x | 视频分片合成（调用 subprocess） |
| Gunicorn + Uvicorn | 最新稳定版 | ASGI/WSGI 生产部署 |

## 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.4+ | 前端框架 |
| Vite | 5.x | 构建工具 |
| Vue Router | 4.x | 路由 |
| Pinia | 2.x | 状态管理 |
| Element Plus | 2.6+ | UI 组件库 |
| Axios | 1.6+ | HTTP 客户端 |
| WaveSurfer.js / 自研时间轴 | — | 视频时间轴裁剪组件 |
| marked + highlight.js | — | Markdown 预览 |

## 第三方服务 API

| 服务 | 用途 | 集成方式 |
|------|------|---------|
| DeepSeek API | LLM 文案生成 | OpenAI 兼容接口，httpx 调用 |
| 火山引擎（豆包）API | LLM 文案生成 | 官方 Python SDK |
| 即梦（Jimeng）API | AI 视频生成 | REST API，异步任务轮询 |
| 微博开放平台 | 自媒体发布 | OAuth 2.0 + REST API |
| 小红书开放平台 | 自媒体发布 | API Key + REST API |
| 微信公众号/视频号 | 自媒体发布 | 微信公众平台 API |
| 今日头条/头条号 | 自媒体发布 | OAuth 2.0 + REST API |

## 基础设施

| 技术 | 用途 |
|------|------|
| Docker + Docker Compose | 容器化部署 |
| Nginx | 反向代理、静态文件服务 |
| MinIO（或本地文件系统） | 文档文件存储、视频文件存储 |
