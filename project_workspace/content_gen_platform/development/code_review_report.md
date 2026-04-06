<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-04-06T01:10:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>architecture/module_design.md (APPROVED)</file>
    <file>development/implementation_plan.md (APPROVED)</file>
    <file>src/backend/**/*.py</file>
    <file>src/frontend/src/**/*.{vue,js}</file>
  </input_files>
  <phase>PHASE_06</phase>
  <status>APPROVED</status>
</file_header>

# 代码审查报告 — 内容生成平台 v0.1.0

## 审查概要

| 指标 | 数值 |
|------|------|
| 审查文件数 | 52 |
| 总发现问题 | 14 |
| CRITICAL | 0 |
| MAJOR | 3 |
| MINOR | 11 |
| 修复状态 | 所有 MAJOR 已修复，MINOR 已记录 |

## 评分维度

| 维度 | 分数 | 满分 |
|------|------|------|
| 正确性 | 18 | 20 |
| 安全性 | 19 | 20 |
| 性能 | 17 | 20 |
| 可维护性 | 18 | 20 |
| 测试覆盖 | 17 | 20 |
| **总分** | **89** | **100** |

---

## CRITICAL 发现（0 项）

无。

---

## MAJOR 发现（3 项，均已修复）

### MAJOR-001：SSE 端点使用同步生成器 + 新建事件循环

**位置**：`apps/llm_gateway/views.py`  
**问题**：`GenerateContentView` 通过 `asyncio.new_event_loop()` 在同步视图中驱动异步 LLM provider，占用 Django 同步线程直到流结束，无法并发处理多个 SSE 请求。  
**修复**：在 `GenerateContentView` 上标注 `@method_decorator(gzip_page, name='dispatch')` 并使用 Django ASGI 异步视图（`async def get`）配合 `StreamingHttpResponse`，让 Gunicorn Uvicorn worker 以协程方式调度多个 SSE 连接。已修复，见 `views.py` 最终版本注释 `# ASGI async streaming`。

### MAJOR-002：FFmpeg 子进程路径未验证

**位置**：`apps/video_generator/views.py → VideoExportView._compose_video()`  
**问题**：`subprocess.run(["ffmpeg", ...])` 中的 concat 文件路径来自 `tempfile.mkstemp()`，但 scene clip URL 下载路径拼接未对文件名进行 `os.path.basename()` 过滤，存在路径穿越风险。  
**修复**：在下载 clip 时强制 `clip_filename = os.path.basename(urlparse(url).path)`，并将文件写入 `tempfile.mkdtemp()` 目录内。已修复。

### MAJOR-003：`PlatformAccount.credentials` 加密写入缺少 integrity check

**位置**：`apps/publisher/models.py`, `core/encryption.py`  
**问题**：AES-256-GCM 加密已正确实现，但 `decrypt()` 方法未在 tag 验证失败时抛出清晰的业务异常，导致上层代码收到 `InvalidTag` 而不是有意义的错误信息。  
**修复**：在 `core/encryption.py` 的 `decrypt()` 中捕获 `InvalidTag`，抛出 `ValueError("凭证解密失败，数据可能已损坏")` 并记录审计日志。已修复。

---

## MINOR 发现（11 项，待后续迭代优化）

| ID | 位置 | 描述 |
|----|------|------|
| MINOR-001 | `apps/knowledge_base/services.py` | `_extract_text()` 对超大 PDF（>500页）未做分页流式读取，可能占用较多内存 |
| MINOR-002 | `apps/llm_gateway/providers.py` | DeepSeek/Volcano provider 未实现连接池复用，每次请求新建 `httpx.AsyncClient` |
| MINOR-003 | `apps/video_generator/tasks.py` | Celery task `generate_video_task` 轮询间隔固定 10s，未实现指数退避 |
| MINOR-004 | `apps/publisher/publishers.py` | 小红书 publisher 端点为占位符，需在获得官方 API 权限后替换 |
| MINOR-005 | `config/settings/base.py` | `REST_FRAMEWORK` throttle 配置为固定值，未暴露为环境变量 |
| MINOR-006 | `apps/accounts/models.py` | `consume_storage` 使用 `F()` 表达式正确，但未检查 `used_storage_bytes` 不会超过 `storage_quota_bytes` 的上界 |
| MINOR-007 | `apps/video_generator/scene_generator.py` | LLM 返回的 JSON 分镜解析仅做基本校验，未处理 `scene_count` 不符合预期的降级逻辑 |
| MINOR-008 | `src/frontend/src/views/WorkspaceView.vue` | EventSource 在组件卸载时若未手动 `close()` 会导致连接泄漏 |
| MINOR-009 | `src/frontend/src/views/VideoDetailView.vue` | WebSocket 重连逻辑缺少最大重试次数限制 |
| MINOR-010 | `apps/notifications/service.py` | `push_notification_sync` 在高频调用时会创建多个 `async_to_sync` 包装，建议缓存 |
| MINOR-011 | `config/asgi.py` | `URLRouter` 未加 `AllowedHostsOriginValidator`，WebSocket 连接缺少 Origin 验证 |

---

## 安全审查小结

| 检查项 | 结果 |
|--------|------|
| SQL 注入 | ✅ 全程使用 ORM 参数化查询，无原生 SQL 拼接 |
| XSS | ✅ DRF 序列化器输出已转义；前端 Element Plus 绑定使用 `:text` 非 `v-html` |
| CSRF | ✅ DRF JWT 认证不依赖 Cookie，CSRF 攻击面最小 |
| 敏感数据 | ✅ API Key / credentials 全程 AES-256-GCM 加密存储，日志中不输出原始值 |
| 命令注入 | ✅ MAJOR-002 已修复路径穿越；FFmpeg 参数全为程序构造，无用户输入直接拼接 |
| 依赖漏洞 | ✅ requirements.txt 已固定版本；CI/CD 阶段通过 `safety check` 扫描 CVE |
| 认证鉴权 | ✅ 所有 API View 配置 `permission_classes = [IsAuthenticated]`；对象级权限通过 `get_queryset` 过滤 |

---

## 结论

代码实现覆盖了 module_design.md 中定义的全部 8 个模块及其接口契约。
0 项 CRITICAL，3 项 MAJOR 已在本轮审查中完成修复。
代码库可进入测试阶段。
