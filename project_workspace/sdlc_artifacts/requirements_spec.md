# Requirements Specification — GenPlatform KB Extension
# file: requirements_spec.md
# author_agent: sub_agent_requirement_analyst
# project: genplatform_kb_extension
# phase: GROUP_A / PHASE_01
# status: DRAFT
# created_at: 2026-04-16
# source: 用户原始需求描述（PM Orchestrator 转述）

---

## 1. 背景与范围

### 1.1 项目背景

GenPlatform 现有知识库（Knowledge Base）功能已支持：
- 单文件上传（PDF / DOCX / TXT / MD），上传后异步处理（文本提取 → 分块 → 向量嵌入）
- 文档列表查询（按当前登录用户过滤）
- 文档删除（含物理文件清理与存储配额释放）
- 语义检索（RAG：向量相似度 + 锚点注入 + 关键词兜底）

已有数据模型：
- `Document`：关联 `User`，字段包含 `name`、`original_filename`、`file_path`、`file_type`、`status`、`chunk_count` 等
- `DocumentChunk`：关联 `Document`，含 `chunk_index`、`content`、`embedding`（512-dim pgvector）

### 1.2 扩展范围（本期）

本期对知识库新增三项功能：

| 编号 | 特性 | 优先级 |
|------|------|--------|
| F-01 | 支持上传目录（含嵌套目录，批量入库） | P0 |
| F-02 | 知识库按用户隔离（默认私有，防止越权） | P0 |
| F-03 | 上传文档默认使用文件名，支持重命名 | P1 |

### 1.3 不在范围内（本期）

- 知识库"共享"功能（多用户共享同一知识库）
- 管理员跨用户访问
- 目录上传的实时进度推送（WebSocket）
- 断点续传
- 压缩包（.zip）解压后入库

---

## 2. 利益相关方

| 角色 | 关切 |
|------|------|
| 最终用户（已登录） | 能上传整个目录、看到自己的文档、为文档命名 |
| 系统管理员 | 数据隔离正确，无越权风险 |
| 开发团队 | 最小化对现有接口的破坏性变更 |

---

## 3. 需求规格

### 3.1 F-01：目录上传

#### REQ-FUNC-001
**来源**：用户需求 1 — "支持上传整个目录（包含多级嵌套子目录）"

后端 API 必须提供一个新端点（或扩展现有端点），接收通过 `multipart/form-data` 提交的**多个文件**（含来自多级子目录的文件），每个文件均附带其**相对路径**（`webkitRelativePath` 或等价字段）。

**验收标准（AC）**：
- **Given** 用户提交一个含 3 个文档的目录（含 1 个子目录），**When** POST 到目录上传端点，**Then** 数据库中创建 3 条 `Document` 记录，每条状态初始为 `processing`，且 Celery 任务被触发 3 次（每个文件一次）。
- **Given** 目录中含有不受支持的文件格式（如 `.exe`、`.jpg`），**When** 上传，**Then** 不支持格式的文件被跳过（不入库），受支持的文件正常入库，响应体中包含跳过文件的列表。
- **Given** 批量上传中某单个文件超过 50MB 限制，**When** 上传，**Then** 该文件被跳过，其余文件正常处理，响应体中包含被拒绝文件及原因。
- **Given** 目录上传导致用户存储配额不足，**When** 上传，**Then** 在配额耗尽前的文件入库，超出配额的文件跳过，响应体明确标注配额已满。

#### REQ-FUNC-002
**来源**：用户需求 1 — "后端应递归遍历目录下所有受支持的文档"

后端处理逻辑须能正确处理嵌套层级不限的目录结构（前端已将所有文件以 flat 列表形式发送，相对路径信息包含在字段中）。

**验收标准（AC）**：
- **Given** 用户上传一个三层嵌套目录（`root/a/b/doc.pdf`），**When** 处理，**Then** `Document.original_filename` 记录为 `doc.pdf`，`Document.name` 默认为 `doc.pdf`（可后续重命名）。
- **Given** 空目录（无受支持文件），**When** 上传，**Then** 返回 HTTP 400，提示"目录中未包含受支持的文档"。

#### REQ-FUNC-003
**来源**：用户需求 1 — "前端需要提供选择目录的入口"

前端知识库页面（`KnowledgeBaseView.vue`）须新增"上传目录"按钮。点击后弹出目录选择器（`<input type="file" webkitdirectory>`），用户选定目录后，前端将所有文件（含相对路径）通过一次 HTTP 请求批量提交到后端目录上传端点。

**验收标准（AC）**：
- **Given** 用户点击"上传目录"按钮，**When** 选择包含 2 个文档的目录，**Then** 进度提示显示"正在上传 2 个文件…"，上传完成后列表刷新。
- **Given** 用户选择的目录不含任何受支持文件，**When** 提交，**Then** 前端展示错误提示"所选目录中无可导入的文档"。

---

### 3.2 F-02：用户隔离

#### REQ-FUNC-004
**来源**：用户需求 2 — "知识库默认属于创建它的用户，其他用户无法检索或查看该知识库的内容"

所有读取 `Document` 或 `DocumentChunk` 的 API 视图**必须**在 ORM 查询层以 `user=request.user`（或 `document__user_id=user_id`）做过滤。禁止在视图层以外通过业务逻辑做隔离（数据层过滤是唯一保证）。

**验收标准（AC）**：
- **Given** 用户 A 和用户 B 各有 1 个文档，**When** 用户 A 调用 `GET /api/v1/knowledge/documents/`，**Then** 响应中仅包含用户 A 的文档，不含用户 B 的文档。
- **Given** 用户 B 知道用户 A 的文档 ID，**When** 用户 B 调用 `GET /api/v1/knowledge/documents/{id}/`，**Then** 返回 HTTP 404（不泄露资源存在）。
- **Given** 用户 B 知道用户 A 的文档 ID，**When** 用户 B 调用 `DELETE /api/v1/knowledge/documents/{id}/`，**Then** 返回 HTTP 404，文档未被删除。

#### REQ-FUNC-005
**来源**：用户需求 2 — "所有查询（搜索、文档列表、分块检索等）必须在数据层做用户过滤"

`services.search()` 函数的现有实现中已有 `document__user_id=user_id` 过滤（见 `services.py` 第 232-235 行）。本期需求要求**代码审查确认**该过滤始终有效，并新增测试覆盖越权场景（跨用户检索不得返回他人数据）。

**验收标准（AC）**：
- **Given** 用户 A 和用户 B 各有 1 个已处理文档，**When** 以用户 A 的 `user_id` 调用 `search()`，**Then** 结果中不含用户 B 的 `DocumentChunk`。（注：现有 `TestSearch.test_search_excludes_other_users_chunks` 已覆盖此场景；本期需在集成测试层补充 API 级别的验证。）

#### REQ-NFUNC-001
**来源**：用户需求 2 — "防止越权"

数据隔离必须在 **ORM 查询层**实现，而不依赖应用层条件判断。即：`get_queryset()` 方法永远返回带有用户过滤的 QuerySet，而非先获取全量数据再在 Python 层过滤。

---

### 3.3 F-03：文件名默认 + 重命名

#### REQ-FUNC-006
**来源**：用户需求 3 — "文档上传后，默认以原始文件名作为显示名称"

现有上传逻辑（`views.py` 第 62-64 行）已实现 `name=request.data.get("name", file.name)`，即若前端不传 `name` 字段则默认使用原始文件名。本期需求要求：
1. **单文件上传**：默认行为维持现状（`name` 不传时 = 原始文件名）。
2. **目录上传**：每个文件的 `name` 默认为其 `original_filename`（即去除路径后的纯文件名）。
3. **前端**：上传对话框中可选填"文档标题"字段，不填时后端自动使用文件名；目录上传时不展示标题字段（因为是批量上传）。

**验收标准（AC）**：
- **Given** 用户上传文件 `report_2024.pdf` 且未填写标题，**When** 上传完成，**Then** `Document.name = "report_2024.pdf"`，`Document.original_filename = "report_2024.pdf"`。
- **Given** 用户上传文件 `report_2024.pdf` 并填写标题为"2024年度报告"，**When** 上传完成，**Then** `Document.name = "2024年度报告"`，`Document.original_filename = "report_2024.pdf"`。

#### REQ-FUNC-007
**来源**：用户需求 3 — "用户可在上传后对文档名称进行修改（rename/edit）"

`DocumentDetailView`（`PATCH /api/v1/knowledge/documents/{id}/`）已支持通过 `name` 字段重命名。本期需求要求：
1. **后端**：`name` 字段为可写字段（现有 `serializer` 中 `name` 未在 `read_only_fields` 内，已满足）。
2. **前端**：文档列表中每行增加"重命名"操作，点击后弹出 inline 输入框或弹窗，提交 PATCH 请求更新 `name`。
3. **约束**：重命名只更新 `Document.name`，不修改 `file_path`、`original_filename` 或任何 `DocumentChunk`。

**验收标准（AC）**：
- **Given** 用户拥有文档 ID=5，`name="旧名称"`，**When** PATCH `/api/v1/knowledge/documents/5/` 携带 `{"name": "新名称"}`，**Then** 响应 200，数据库中 `Document(id=5).name = "新名称"`，`original_filename` 不变，`DocumentChunk` 不受影响。
- **Given** 用户 B 尝试 PATCH 用户 A 的文档，**When** 请求发出，**Then** 返回 HTTP 404，文档名称未变更。
- **Given** 用户在前端点击某文档的"重命名"，**When** 输入新名称并确认，**Then** 文档列表该行名称即时更新（乐观更新或重新拉取均可）。

#### REQ-NFUNC-002
**来源**：用户需求 3 — "重命名只影响显示名称，不影响物理文件或分块内容"

后端序列化器必须将 `file_path`、`original_filename`、`file_type`、`embedding`（分块）设为不可通过 PATCH 修改（`read_only_fields` 或 `partial=True` 下的字段白名单）。

---

## 4. 非功能需求汇总

| 编号 | 类型 | 要求 |
|------|------|------|
| REQ-NFUNC-001 | 安全 | 数据隔离在 ORM 层实现，禁止应用层过滤代替 |
| REQ-NFUNC-002 | 数据完整性 | 重命名不影响物理文件、original_filename、分块内容 |
| REQ-NFUNC-003 | 性能 | 目录上传中每个文件的 Celery 任务独立异步调度，不阻塞 HTTP 响应 |
| REQ-NFUNC-004 | 兼容性 | 现有单文件上传 API 接口不得有破坏性变更（向后兼容） |
| REQ-NFUNC-005 | 存储配额 | 目录上传时逐文件检查配额，超出时提前终止而非全部拒绝 |

---

## 5. 约束与假设

- 前端使用 `<input type="file" webkitdirectory multiple>` 获取目录文件列表，每个 `File` 对象均有 `.webkitRelativePath` 属性（主流浏览器支持）。
- 后端不需要实际在文件系统创建对应的目录结构；所有文件平铺存放于 `MEDIA_ROOT/documents/{user_id}/`。
- 嵌套路径信息仅用于 `Document.name`（默认值）的展示，不作为物理路径使用。
- 现有 `Document.user` FK 已正确建立，无需 Schema 变更即可满足 F-02 的隔离需求。
- `DocumentSerializer` 中 `name` 字段已为可写，无需 Schema 变更即可满足 F-03 的重命名需求。

---

## 6. 变更影响分析

| 模块 | 变更类型 | 说明 |
|------|---------|------|
| `views.py` | 扩展 | 新增 `DocumentBatchUploadView`（目录上传端点） |
| `urls.py` | 扩展 | 新增路由 `documents/batch-upload/` |
| `serializers.py` | 微调 | 新增 `BatchUploadResultSerializer` 用于批量上传响应 |
| `KnowledgeBaseView.vue` | 扩展 | 新增"上传目录"按钮、目录选择逻辑、重命名操作列 |
| `api/index.js` | 扩展 | 新增 `kbAPI.batchUpload()`、`kbAPI.rename()` |
| `tests/test_views.py` | 扩展 | 新增批量上传、越权访问、重命名测试用例 |
| `models.py` | 无变更 | 现有 Schema 已满足所有需求 |
| `services.py` | 无变更 | 现有 `search()` 过滤已正确，仅需测试覆盖确认 |
| `migrations/` | 无变更 | 无 Schema 变更 |
