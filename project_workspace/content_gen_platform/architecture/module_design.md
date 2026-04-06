<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-04-06T00:12:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files><file>requirements/requirements_spec.md (APPROVED)</file></input_files>
  <phase>PHASE_04</phase>
  <status>APPROVED</status>
</file_header>

# 模块设计说明书 — 内容生成平台

---

## 模块依赖图

```
MOD-001 (accounts)
    ↑
MOD-002 (knowledge_base) ──────────────────────┐
    ↑                                           │
MOD-003 (llm_gateway) ──── depends on ─────────┤
    ↑                                           │
MOD-004 (content) ──────── depends on ─────────┤
    ↑                    MOD-002, MOD-003        │
MOD-005 (publisher) ───── depends on ───────── MOD-004
    ↑                                           │
MOD-006 (video_generator) ─ depends on ─────── MOD-004
    ↑
MOD-007 (notifications) ── depends on ─────── MOD-004, MOD-005, MOD-006
MOD-008 (settings_vault) ── depends on ─────── MOD-001
```

无循环依赖 ✓

---

## MOD-001：accounts（用户账户模块）

**职责**：用户注册、登录、JWT 认证、用户档案管理。  
**关联需求**：REQ-FUNC-001

### 数据模型
```python
class User(AbstractUser):
    email: EmailField(unique=True)
    created_at: DateTimeField
    storage_quota_bytes: BigIntegerField(default=2*1024**3)  # 2GB
    used_storage_bytes: BigIntegerField(default=0)
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| POST | /api/v1/auth/register/ | 用户注册 |
| POST | /api/v1/auth/login/ | 用户登录，返回 JWT |
| POST | /api/v1/auth/token/refresh/ | 刷新 Access Token |
| GET/PATCH | /api/v1/auth/profile/ | 获取/更新用户档案 |

---

## MOD-002：knowledge_base（知识库模块）

**职责**：文档上传、存储、向量化（Embedding）、语义检索（RAG）、文档管理。  
**关联需求**：REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004

### 数据模型
```python
class Document(Model):
    user: ForeignKey(User, on_delete=CASCADE)
    name: CharField(max_length=255)
    original_filename: CharField(max_length=255)
    file_path: CharField(max_length=1024)  # MinIO path
    file_size_bytes: BigIntegerField
    file_type: CharField(choices=['pdf','docx','txt','md'])
    status: CharField(choices=['processing','available','error'])
    chunk_count: IntegerField(default=0)
    created_at: DateTimeField
    updated_at: DateTimeField

class DocumentChunk(Model):
    document: ForeignKey(Document, on_delete=CASCADE)
    chunk_index: IntegerField
    content: TextField
    embedding: VectorField(dim=1024)  # bge-m3 output dim
    created_at: DateTimeField
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| GET | /api/v1/knowledge/documents/ | 列表（支持搜索、分页） |
| POST | /api/v1/knowledge/documents/ | 上传文档（multipart） |
| GET | /api/v1/knowledge/documents/{id}/ | 文档详情 |
| PATCH | /api/v1/knowledge/documents/{id}/ | 重命名 |
| DELETE | /api/v1/knowledge/documents/{id}/ | 删除文档+向量 |

### 核心服务接口
```python
class KnowledgeBaseService:
    def process_document(document_id: int) -> None:
        """异步：分割文档、生成 Embedding、存入 pgvector"""
    
    def search(user_id: int, query: str, top_k: int = 3) -> List[DocumentChunk]:
        """语义检索，返回最相关的 top_k 文档片段"""
```

---

## MOD-003：llm_gateway（LLM 网关模块）

**职责**：统一 LLM API 调用接口，屏蔽 DeepSeek/火山引擎的差异，支持流式输出。  
**关联需求**：REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008

### 数据模型（无独立 DB 表，使用 MOD-008 存储配置）

### 核心服务接口
```python
class LLMGateway:
    def get_provider(user_id: int) -> BaseLLMProvider:
        """从 settings_vault 获取用户配置，返回对应 Provider 实例"""
    
    async def stream_generate(
        provider: BaseLLMProvider,
        system_prompt: str,
        user_prompt: str,
        context_chunks: List[str],
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """流式生成，yield Token"""

class BaseLLMProvider(ABC):
    @abstractmethod
    async def stream_chat(messages: List[dict]) -> AsyncGenerator[str, None]: ...

class DeepSeekProvider(BaseLLMProvider): ...
class VolcanoProvider(BaseLLMProvider): ...
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| GET | /api/v1/llm/providers/ | 获取支持的 LLM 提供商列表 |
| GET/SSE | /api/v1/llm/generate/ | 触发文案生成（SSE 流式响应） |

---

## MOD-004：content（文案内容模块）

**职责**：管理文案草稿、确认状态、编辑历史。  
**关联需求**：REQ-FUNC-008, REQ-FUNC-009

### 数据模型
```python
class Content(Model):
    user: ForeignKey(User, on_delete=CASCADE)
    title: CharField(max_length=255)
    body: TextField
    platform_type: CharField(choices=['weibo','xiaohongshu','wechat_mp','wechat_video','toutiao','general'])
    style: CharField(choices=['professional','casual','humorous','promotion'])
    word_limit: IntegerField(null=True)
    status: CharField(choices=['draft','confirmed','published'])
    generation_prompt: TextField  # 原始生成指令
    used_document_ids: JSONField(default=list)  # RAG 引用的文档 ID
    created_at: DateTimeField
    updated_at: DateTimeField
    confirmed_at: DateTimeField(null=True)
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| GET | /api/v1/contents/ | 文案列表（支持状态过滤、分页） |
| POST | /api/v1/contents/ | 创建文案（草稿） |
| GET | /api/v1/contents/{id}/ | 文案详情 |
| PATCH | /api/v1/contents/{id}/ | 更新文案内容 |
| POST | /api/v1/contents/{id}/confirm/ | 确认文案 |
| DELETE | /api/v1/contents/{id}/ | 删除文案 |

---

## MOD-005：publisher（发布模块）

**职责**：多平台账号绑定管理、文案发布（立即/定时）、发布历史。  
**关联需求**：REQ-FUNC-010, REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-013

### 数据模型
```python
class PlatformAccount(Model):
    user: ForeignKey(User, on_delete=CASCADE)
    platform: CharField(choices=['weibo','xiaohongshu','wechat_mp','wechat_video','toutiao'])
    display_name: CharField(max_length=255)
    auth_type: CharField(choices=['oauth','api_key'])
    encrypted_credentials: BinaryField  # AES-256-GCM
    is_active: BooleanField(default=True)
    created_at: DateTimeField

class PublishTask(Model):
    user: ForeignKey(User, on_delete=CASCADE)
    content: ForeignKey(Content, on_delete=CASCADE)
    platform_account: ForeignKey(PlatformAccount, on_delete=CASCADE)
    status: CharField(choices=['pending','publishing','success','failed'])
    scheduled_at: DateTimeField(null=True)  # null = 立即发布
    published_at: DateTimeField(null=True)
    platform_post_id: CharField(null=True)  # 平台返回的帖子 ID
    platform_post_url: URLField(null=True)
    error_message: TextField(null=True)
    retry_count: IntegerField(default=0)
    created_at: DateTimeField

class BasePlatformPublisher(ABC):
    @abstractmethod
    async def publish(content: Content, credentials: dict) -> PublishResult: ...

class WeiboPublisher(BasePlatformPublisher): ...
class XiaohongshuPublisher(BasePlatformPublisher): ...
class WechatMpPublisher(BasePlatformPublisher): ...
class WechatVideoPublisher(BasePlatformPublisher): ...
class ToutiaoPublisher(BasePlatformPublisher): ...
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| GET | /api/v1/publisher/accounts/ | 已绑定平台账号列表 |
| POST | /api/v1/publisher/accounts/{platform}/bind/ | 发起账号绑定 |
| DELETE | /api/v1/publisher/accounts/{id}/ | 解绑账号 |
| POST | /api/v1/publisher/tasks/ | 创建发布任务 |
| GET | /api/v1/publisher/tasks/ | 发布历史（支持过滤、分页） |
| POST | /api/v1/publisher/tasks/{id}/retry/ | 重试失败任务 |

---

## MOD-006：video_generator（视频生成模块）

**职责**：分镜生成、分镜编辑、调用即梦 API 生成视频、视频裁剪与合成。  
**关联需求**：REQ-FUNC-014 ~ REQ-FUNC-019

### 数据模型
```python
class VideoProject(Model):
    user: ForeignKey(User, on_delete=CASCADE)
    content: ForeignKey(Content, on_delete=CASCADE)
    status: CharField(choices=['draft','generating','completed','failed'])
    final_video_path: CharField(null=True)
    jimeng_task_id: CharField(null=True)
    created_at: DateTimeField
    updated_at: DateTimeField

class Scene(Model):
    video_project: ForeignKey(VideoProject, on_delete=CASCADE, related_name='scenes')
    scene_index: IntegerField  # 顺序（可调整）
    scene_prompt: TextField    # 画面描述提示词
    narration: TextField       # 配音文案
    voice_style: JSONField     # {speed, emotion, voice_id}
    duration_sec: IntegerField(default=5)  # 2-10秒
    transition: CharField(choices=['cut','fade','push_pull'], default='cut')
    jimeng_clip_url: URLField(null=True)   # 即梦返回的分镜视频 URL
    is_deleted: BooleanField(default=False)
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| POST | /api/v1/video/projects/ | 从文案创建视频项目（自动生成分镜） |
| GET | /api/v1/video/projects/{id}/ | 视频项目详情+分镜列表 |
| POST | /api/v1/video/projects/{id}/generate/ | 提交即梦生成任务 |
| GET | /api/v1/video/projects/{id}/status/ | 轮询视频生成状态 |
| PATCH | /api/v1/video/projects/{id}/scenes/{scene_id}/ | 编辑单个分镜 |
| DELETE | /api/v1/video/projects/{id}/scenes/{scene_id}/ | 删除分镜 |
| POST | /api/v1/video/projects/{id}/reorder/ | 调整分镜顺序 |
| POST | /api/v1/video/projects/{id}/export/ | 合成并导出最终视频 |

### 核心服务接口
```python
class SceneGeneratorService:
    def generate_scenes(content: Content) -> List[Scene]:
        """调用 LLM 将文案拆解为结构化分镜列表"""
    
    def validate_continuity(scenes: List[Scene]) -> List[ContinuityIssue]:
        """校验分镜间逻辑连贯性，返回问题列表"""

class JimengAPIClient:
    async def submit_task(scenes: List[Scene]) -> str:  # returns task_id
    async def poll_status(task_id: str) -> TaskStatus
    async def get_result(task_id: str) -> List[ClipURL]

class VideoCompositorService:
    def compose(clips: List[ClipPath], transitions: List[str]) -> Path:
        """调用 FFmpeg 合成最终视频"""
```

---

## MOD-007：notifications（通知模块）

**职责**：通过 WebSocket 向用户推送实时通知（视频生成完成、发布状态变更等）。  
**关联需求**：REQ-FUNC-012, REQ-FUNC-016

### 核心接口
```python
class NotificationService:
    async def push(user_id: int, event_type: str, payload: dict) -> None:
        """通过 Django Channels 推送 WebSocket 通知"""
```

---

## MOD-008：settings_vault（配置保险库模块）

**职责**：安全存储和检索所有第三方 API 凭证（LLM Key、即梦 Key）；平台账号 OAuth 配置入口（平台账号凭证由 MOD-005 管理）。  
**关联需求**：REQ-FUNC-005, REQ-FUNC-016, REQ-NFUNC-002

### 数据模型
```python
class UserServiceConfig(Model):
    user: ForeignKey(User, on_delete=CASCADE)
    service_type: CharField(choices=['llm_deepseek','llm_volcano','jimeng'])
    encrypted_config: BinaryField  # AES-256-GCM 加密的 JSON
    is_active: BooleanField(default=True)
    created_at: DateTimeField
    updated_at: DateTimeField
```

### API 接口
| Method | URL | 功能 |
|--------|-----|------|
| GET | /api/v1/settings/services/ | 获取所有服务配置状态（不返回明文 Key） |
| PUT | /api/v1/settings/services/{service_type}/ | 保存/更新服务配置 |
| POST | /api/v1/settings/services/{service_type}/test/ | 测试连接 |
| DELETE | /api/v1/settings/services/{service_type}/ | 删除配置 |
