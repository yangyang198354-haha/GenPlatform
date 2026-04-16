# Architecture Design — GenPlatform KB Extension
# file: architecture_design.md
# author_agent: sub_agent_system_architect
# project: genplatform_kb_extension
# phase: GROUP_B / PHASE_03-04
# status: DRAFT
# created_at: 2026-04-16
# input_refs: requirements_spec.md, user_stories.md

---

## 1. 架构决策记录（ADR）

### ADR-001：目录上传端点设计 — 新增独立端点 vs. 扩展现有端点

**问题**：F-01 目录批量上传是否复用 `POST /api/v1/knowledge/documents/`，还是新增独立端点？

**方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: 扩展现有端点（通过字段区分） | 路由简洁 | 单文件与批量逻辑耦合，违反 SRP；响应结构差异导致客户端处理复杂 |
| B: 新增独立端点 `POST /api/v1/knowledge/documents/batch-upload/` | 职责单一，两端均简单；响应结构可独立设计；向后兼容现有端点 | 多一个路由 |

**决策**：采用方案 B。

**理由**：
- 单文件上传返回单个 `Document` 对象；批量上传需要返回 `accepted` / `skipped` / `quota_exceeded` 三类列表，结构完全不同。
- 现有单文件端点有完整测试覆盖，扩展会增加破坏风险（REQ-NFUNC-004）。
- 向后兼容无代价，前端通过不同按钮触发不同接口。

---

### ADR-002：批量上传的原子性策略 — 全成功-全失败 vs. 逐文件最大化入库

**问题**：批量上传中若有文件校验失败，是回滚全部还是跳过失败文件？

**方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: 全成功-全失败（事务原子性） | 一致性强 | 一个 .jpg 导致整个目录失败，用户体验极差 |
| B: 逐文件最大化入库（部分成功） | 用户体验好，符合 REQ-FUNC-001 AC | 需要详细的响应报告 |

**决策**：采用方案 B，逐文件处理，部分成功。

**理由**：REQ-FUNC-001 和 US-003 明确要求：不支持格式的文件被跳过，超大文件被跳过，配额耗尽前的文件成功入库。响应体需包含 `accepted` / `skipped` / `rejected` 列表。

---

### ADR-003：重命名 API 设计 — PATCH 整体更新 vs. 专用重命名端点

**问题**：重命名是否需要专用端点 `POST /documents/{id}/rename/` 或直接复用 `PATCH /documents/{id}/`？

**方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: 复用 PATCH | 符合 REST 语义；无需新路由；序列化器控制可写字段白名单 | 无 |
| B: 专用 rename 端点 | 语义更明确 | 冗余，破坏 RESTful 设计 |

**决策**：采用方案 A，复用 `PATCH /documents/{id}/`。

**理由**：现有 `DocumentDetailView` 已继承 `RetrieveUpdateDestroyAPIView`，`DocumentSerializer` 中 `name` 为可写字段，`read_only_fields` 已保护 `original_filename`、`file_path` 等字段。只需确认序列化器配置正确，无需任何后端变更。

---

## 2. 模块设计

### 2.1 后端模块变更

#### 2.1.1 新增：`DocumentBatchUploadView`（`views.py`）

```
DocumentBatchUploadView(APIView)
├── parser_classes: [MultiPartParser]
├── permission_classes: [IsAuthenticated]
└── post(request)
    ├── 读取 request.FILES.getlist("files")
    ├── 校验：若无文件 → HTTP 400 "目录中未包含受支持的文档"
    ├── 逐文件处理循环：
    │   ├── 提取 original_filename（从 webkitRelativePath 或 file.name）
    │   ├── 扩展名校验 → 不支持则加入 skipped 列表
    │   ├── 文件大小校验（> 50MB）→ 加入 rejected 列表
    │   ├── 存储配额校验 → 配额耗尽则加入 rejected 列表，设 quota_exhausted=True
    │   ├── 若 quota_exhausted 则停止处理后续文件
    │   ├── 写入文件到 MEDIA_ROOT/documents/{user_id}/
    │   ├── 创建 Document 记录（name=original_filename, status="processing"）
    │   ├── user.consume_storage(file.size)
    │   └── process_document_task.delay(doc.pk)
    └── 返回 BatchUploadResultSerializer 数据
```

**接口规格**：

- **URL**: `POST /api/v1/knowledge/documents/batch-upload/`
- **Content-Type**: `multipart/form-data`
- **请求字段**:
  - `files`: 多文件字段（`request.FILES.getlist("files")`）
  - `relative_paths`: （可选）JSON 字符串，格式 `["root/sub/doc.pdf", ...]`，与 files 一一对应
- **成功响应** `HTTP 201`（部分成功也是 201）:

```json
{
  "accepted": [
    {"name": "doc1.pdf", "document_id": 42, "status": "processing"}
  ],
  "skipped": [
    {"name": "photo.jpg", "reason": "format_not_supported"}
  ],
  "rejected": [
    {"name": "large.pdf", "reason": "file_too_large"},
    {"name": "doc2.txt", "reason": "quota_exceeded"}
  ],
  "quota_exhausted": false,
  "summary": "3 个文件已提交，1 个格式不支持，1 个超过大小限制"
}
```

- **全部跳过（无受支持文件）响应** `HTTP 400`:

```json
{"error": "所选目录中未包含受支持的文档"}
```

#### 2.1.2 新增：`BatchUploadResultSerializer`（`serializers.py`）

```python
class BatchUploadItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    document_id = serializers.IntegerField(required=False)
    status = serializers.CharField(required=False)
    reason = serializers.CharField(required=False)

class BatchUploadResultSerializer(serializers.Serializer):
    accepted = BatchUploadItemSerializer(many=True)
    skipped = BatchUploadItemSerializer(many=True)
    rejected = BatchUploadItemSerializer(many=True)
    quota_exhausted = serializers.BooleanField()
    summary = serializers.CharField()
```

#### 2.1.3 修改：`urls.py`

```python
urlpatterns = [
    path("documents/", DocumentListCreateView.as_view(), name="kb-document-list"),
    path("documents/batch-upload/", DocumentBatchUploadView.as_view(), name="kb-document-batch-upload"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="kb-document-detail"),
]
```

**注意**：`batch-upload/` 路由必须在 `<int:pk>/` 之前注册，避免 Django URL 解析歧义。

#### 2.1.4 验证：`DocumentDetailView.get_queryset()`（`views.py`）

现有实现已正确：

```python
def get_queryset(self):
    return Document.objects.filter(user=self.request.user)
```

`generics.RetrieveUpdateDestroyAPIView` 的 `get_object()` 会在此 queryset 上调用 `.get(pk=pk)`，若 pk 不属于当前用户则抛出 `Http404`，满足 REQ-FUNC-004 和 REQ-NFUNC-001。无需修改。

#### 2.1.5 验证：`DocumentSerializer`（`serializers.py`）

现有 `read_only_fields` 已包含 `original_filename`、`file_type`、`file_size_bytes` 等字段，`name` 为可写字段，满足 REQ-NFUNC-002。无需修改。

---

### 2.2 前端模块变更

#### 2.2.1 `KnowledgeBaseView.vue` — 新增功能点

**变更 1：新增"上传目录"按钮**

在页面头部现有"上传文档"按钮旁新增"上传目录"按钮：

```html
<el-button type="default" :icon="FolderOpened" @click="triggerDirUpload">
  上传目录
</el-button>
<input
  ref="dirInputRef"
  type="file"
  style="display:none"
  webkitdirectory
  multiple
  @change="handleDirSelected"
/>
```

**变更 2：目录上传处理逻辑**

```javascript
async function handleDirSelected(event) {
  const files = Array.from(event.target.files);
  // 过滤受支持格式（前端预过滤，减少无效请求）
  const supported = files.filter(f => /\.(pdf|docx|txt|md)$/i.test(f.name));
  if (supported.length === 0) {
    ElMessage.error("所选目录中无可导入的文档");
    return;
  }
  ElMessage.info(`正在上传 ${supported.length} 个文件…`);
  const formData = new FormData();
  const relativePaths = [];
  supported.forEach(f => {
    formData.append("files", f);
    relativePaths.push(f.webkitRelativePath || f.name);
  });
  formData.append("relative_paths", JSON.stringify(relativePaths));
  try {
    const { data } = await kbAPI.batchUpload(formData);
    const msg = data.summary;
    if (data.accepted.length > 0) {
      ElMessage.success(msg);
    } else {
      ElMessage.warning(msg);
    }
    fetchDocuments();
  } catch (err) {
    const msg = err.response?.data?.error || "目录上传失败，请重试";
    ElMessage.error(msg);
  } finally {
    // reset input
    event.target.value = "";
  }
}
```

**变更 3：新增重命名操作列**

文档表格操作列新增重命名按钮：

```html
<el-table-column label="操作" width="160">
  <template #default="{ row }">
    <el-button
      type="primary" size="small" :icon="EditPen" circle
      @click="startRename(row)"
    />
    <el-popconfirm title="确认删除？" @confirm="deleteDoc(row.id)">
      <template #reference>
        <el-button type="danger" size="small" :icon="Delete" circle />
      </template>
    </el-popconfirm>
  </template>
</el-table-column>
```

**变更 4：重命名 Dialog**

```html
<el-dialog v-model="showRenameDialog" title="重命名文档" width="400px">
  <el-input v-model="renameValue" placeholder="输入新名称" />
  <template #footer>
    <el-button @click="showRenameDialog = false">取消</el-button>
    <el-button type="primary" @click="confirmRename">确认</el-button>
  </template>
</el-dialog>
```

**重命名逻辑**：

```javascript
const showRenameDialog = ref(false);
const renameTarget = ref(null);
const renameValue = ref("");

function startRename(row) {
  renameTarget.value = row;
  renameValue.value = row.name;
  showRenameDialog.value = true;
}

async function confirmRename() {
  if (!renameValue.value.trim()) return;
  try {
    await kbAPI.rename(renameTarget.value.id, renameValue.value.trim());
    ElMessage.success("重命名成功");
    showRenameDialog.value = false;
    // 乐观更新：直接修改本地数据，无需重新拉取
    renameTarget.value.name = renameValue.value.trim();
  } catch (err) {
    ElMessage.error(err.response?.data?.error || "重命名失败");
  }
}
```

#### 2.2.2 `api/index.js` — 新增方法

```javascript
export const kbAPI = {
  // 现有方法保持不变
  list: (params) => api.get("/knowledge/documents/", { params }),
  upload: (formData) => api.post("/knowledge/documents/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }),
  search: (query) => api.get("/knowledge/documents/", { params: { search: query } }),
  delete: (id) => api.delete(`/knowledge/documents/${id}/`),
  // 新增
  batchUpload: (formData) => api.post("/knowledge/documents/batch-upload/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }),
  rename: (id, name) => api.patch(`/knowledge/documents/${id}/`, { name }),
};
```

---

## 3. 数据流图

### F-01 目录上传数据流

```
用户点击"上传目录"
  → <input webkitdirectory> 触发文件选择
  → JS 过滤支持格式 → FormData 构建（files[] + relative_paths JSON）
  → POST /api/v1/knowledge/documents/batch-upload/
    → DocumentBatchUploadView.post()
      → 逐文件：校验格式 + 大小 + 配额
      → 写文件到磁盘
      → Document.objects.create(status="processing")
      → user.consume_storage()
      → process_document_task.delay(doc.pk) [异步 Celery]
    → 返回 BatchUploadResult（accepted/skipped/rejected）
  → 前端显示 summary，刷新文档列表
```

### F-03 重命名数据流

```
用户点击重命名按钮
  → showRenameDialog = true，预填当前名称
  → 用户输入新名称，点击确认
  → PATCH /api/v1/knowledge/documents/{id}/ {"name": "新名称"}
    → DocumentDetailView（get_queryset 过滤用户）
    → DocumentSerializer.partial_update → 仅更新 name 字段
    → 返回 200 + 更新后 Document 数据
  → 前端乐观更新列表中该行的 name
```

---

## 4. 安全约束验证

| 约束 | 实现位置 | 满足状态 |
|------|---------|---------|
| REQ-NFUNC-001: 数据隔离在 ORM 层 | `DocumentListCreateView.get_queryset()` + `DocumentDetailView.get_queryset()` + `DocumentBatchUploadView`（直接关联 request.user）+ `services.search()` 的 `document__user_id=user_id` | 已满足 |
| REQ-NFUNC-002: 重命名不影响物理文件 | `DocumentSerializer.read_only_fields` 包含 `file_path`、`original_filename` | 已满足 |
| REQ-NFUNC-003: 批量上传异步处理 | `process_document_task.delay()` — Celery 异步 | 已满足 |
| REQ-NFUNC-004: 向后兼容 | 现有 `POST /documents/` 端点不变，新增独立批量端点 | 已满足 |
| REQ-NFUNC-005: 逐文件配额检查 | `DocumentBatchUploadView` 逐文件检查，quota_exhausted 后停止但已处理文件保留 | 已满足 |

---

## 5. 无 Schema 变更确认

- `Document` 模型字段已完整，无需 migration
- `DocumentChunk` 模型无变更
- 用户 `storage_quota_bytes` / `used_storage_bytes` / `consume_storage()` / `release_storage()` / `has_storage_quota()` 现有实现复用

---

## 6. 模块依赖图（无循环依赖验证）

```
views.py
  → models.py (Document)
  → serializers.py (DocumentSerializer, BatchUploadResultSerializer)
  → tasks.py (process_document_task)
  → apps.accounts.models (User)

serializers.py
  → models.py (Document)

tasks.py
  → services.py (process_document)
  → models.py (Document)

services.py
  → models.py (Document, DocumentChunk)
```

无循环依赖。
