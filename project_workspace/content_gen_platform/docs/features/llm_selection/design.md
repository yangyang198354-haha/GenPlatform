# LLM 模型选择功能 — 架构设计方案

**版本**：v0.1.0-DRAFT
**日期**：2026-05-15
**关联文档**：
- `docs/features/llm_selection/requirements.md`（已 APPROVED）
- `docs/features/llm_selection/user_stories.md`（已 APPROVED）

**特性分支**：llm_selection

---

## 1. 架构概览

### 1.1 数据流图（文字版）

```
前端 WorkspaceView
  │
  ├─[页面挂载 onMounted]──► GET /api/v1/llm/providers/
  │                              │
  │                         ProvidersView（新增）
  │                              │
  │                         selectors.list_available_providers(user)
  │                         ├─► UserServiceConfig.filter(user, service_type__startswith="llm_", is_active=True)
  │                         ├─► [并行] DeepSeekProvider.list_models()  ←──── DeepSeek /models 端点（800ms 超时→fallback）
  │                         └─► [并行] VolcanoProvider.list_models()   ←──── Ark /v3/models    （800ms 超时→fallback）
  │                              │
  │                         聚合响应（含 user_preference、providers[]、warnings[]）
  │                              │
  │                         ◄────────────────────────────────────────────
  │
  ├─[用户选择 provider+model]
  │
  ├─[点击"生成"]──────────► POST /api/v1/llm/generate/
  │                              │
  │                         GenerateContentView（修改）
  │                              │
  │                         selectors.validate_choice(user, service_type, model)
  │                         ├─若未传参─► selectors.resolve_default(user)
  │                         └─若传参──► 校验 provider 已配置 + model 在合法集合
  │                              │
  │                         decrypt(UserServiceConfig.encrypted_config)
  │                         get_provider(service_type, config, model)（修改）
  │                              │
  │                         [SSE] provider.stream_chat(messages)  ──► 第三方 LLM API
  │                              │
  │                         SSE 流结束（正常）
  │                         ├─► Content.save(provider=X, model=Y)     # 审计字段（新增）
  │                         └─► UserLLMPreference.save(service_type, model)  # 偏好（新增）
  │                              │
  │                         ◄──── SSE done 事件 {used_provider, used_model}
  │
  └─[生成成功，偏好回写由后端完成，无需前端额外调 /preference/]
```

### 1.2 模块分类

| 模块 | 状态 | 说明 |
|------|------|------|
| `apps/llm_gateway/selectors.py` | **新增** | 决策链、校验、provider 列表聚合 |
| `apps/llm_gateway/models.py` | **新增** | UserLLMPreference 表 |
| `apps/llm_gateway/views.py` | **修改** | 新增 ProvidersView；GenerateContentView 改 POST + 扩展入参 |
| `apps/llm_gateway/urls.py` | **修改** | 注册两条新路由 |
| `apps/llm_gateway/providers.py` | **修改** | get_provider 接受显式 model；各 Provider 新增 list_models() |
| `apps/settings_vault/models.py` | **修改** | UserServiceConfig 新增 last_tested_at |
| `apps/content/models.py` | **修改** | Content 新增 provider、model 审计字段 |
| `apps/content/migrations/` | **新增** | 0002_content_provider_model.py |
| `apps/llm_gateway/migrations/` | **新增** | 0001_userllmpreference.py |
| `apps/settings_vault/migrations/` | **新增** | 0004_userserviceconfig_last_tested_at.py |
| `src/frontend/src/components/LlmSelector.vue` | **新增** | provider+model 下拉组件 |
| `src/frontend/src/stores/llm.js` | **新增** | Pinia store |
| `src/frontend/src/views/WorkspaceView.vue` | **修改** | 接入 LlmSelector |
| `apps/settings_vault/` 其余文件 | **不动** | ark_validator、TestAndSaveView 等 |
| 图片生成相关模块 | **不动** | doubao_image、jimeng 完全隔离 |
| `apps/knowledge_base/` | **不动** | KB 搜索逻辑不受影响 |

---

## 2. API 契约

### 2.1 新增 `GET /api/v1/llm/providers/`

**认证**：必须登录（SessionAuthentication / TokenAuthentication，与现有接口一致）
**请求**：无 body，无 query params
**缓存策略**：响应头 `Cache-Control: no-store`（探活状态实时来自 DB，下拉数据每次打开实时取）

**响应 200 — 正常态（双 provider 均有效，models 动态拉取成功）**

```json
{
  "default": {
    "service_type": "llm_deepseek",
    "model": "deepseek-chat"
  },
  "user_preference": {
    "service_type": "llm_volcano",
    "model": "doubao-pro-32k"
  },
  "providers": [
    {
      "service_type": "llm_deepseek",
      "label": "DeepSeek",
      "configured": true,
      "last_test_ok": true,
      "models_source": "dynamic",
      "models": [
        {"id": "deepseek-chat",     "label": "DeepSeek V3"},
        {"id": "deepseek-reasoner", "label": "DeepSeek R1"}
      ]
    },
    {
      "service_type": "llm_volcano",
      "label": "火山引擎豆包",
      "configured": true,
      "last_test_ok": true,
      "models_source": "dynamic",
      "models": [
        {"id": "doubao-pro-4k",  "label": "豆包 Pro 4k"},
        {"id": "doubao-pro-32k", "label": "豆包 Pro 32k"}
      ]
    }
  ],
  "warnings": []
}
```

**响应 200 — fallback 态（Ark /models 超时，火山引擎使用白名单）**

```json
{
  "default": {"service_type": "llm_deepseek", "model": "deepseek-chat"},
  "user_preference": null,
  "providers": [
    {
      "service_type": "llm_deepseek",
      "label": "DeepSeek",
      "configured": true,
      "last_test_ok": true,
      "models_source": "dynamic",
      "models": [
        {"id": "deepseek-chat",     "label": "DeepSeek V3"},
        {"id": "deepseek-reasoner", "label": "DeepSeek R1"}
      ]
    },
    {
      "service_type": "llm_volcano",
      "label": "火山引擎豆包",
      "configured": true,
      "last_test_ok": true,
      "models_source": "fallback",
      "models": [
        {"id": "doubao-pro-4k",  "label": "豆包 Pro 4k"},
        {"id": "doubao-pro-32k", "label": "豆包 Pro 32k"}
      ]
    }
  ],
  "warnings": ["火山引擎模型列表加载失败，使用默认列表"]
}
```

**响应 200 — 完全空态（用户无任何有效 LLM 配置）**

```json
{
  "default": null,
  "user_preference": null,
  "providers": [],
  "warnings": []
}
```

> 前端收到 `providers: []` 或所有 provider `configured=false`/`last_test_ok=false` 时，禁用下拉 + 禁用生成按钮 + 展示引导提示。

**错误码**

| HTTP 状态 | 场景 |
|-----------|------|
| 401 | 未登录 |

**性能预算**

- P95 < 1s（从请求到达 Django 到响应返回）
- 内部 list_models() 并行发起（asyncio.gather 或 ThreadPoolExecutor），单 provider 超时 800ms
- 后端对 `(user_id, service_type)` 的 list_models() 结果做内存缓存，TTL=5min（使用 Django cache framework，默认 LocMemCache；生产环境已有 Redis 可直接用）

---

### 2.2 修改 `GET → POST /api/v1/llm/generate/`

**方向决定：改为 POST，body 比 query params 更适合携带结构化参数；旧 GET 调用向后兼容策略见下。**

**向后兼容策略**：

- 保留 GET 路由，但 GET 请求中若检测到无 `provider` / `model` 参数（旧客户端），走 `resolve_default` 决策链。
- 同时新增 POST 路由，前端统一切换到 POST。
- 两个路由均注册到同一 View，用 `http_method_names` 或分别定义 `get()`/`post()` 实现。
- 旧 GET 接口在下一个 major 版本（v2）才废弃，文档标注 `@deprecated`。

**POST 请求 body（application/json）**

```json
{
  "prompt":     "写一篇小红书种草文案",
  "platform":   "xiaohongshu",
  "style":      "casual",
  "word_limit": 500,
  "use_kb":     true,
  "provider":   "llm_volcano",
  "model":      "doubao-pro-32k"
}
```

> `provider` 与 `model` 为可选字段，二者要么同时传、要么同时省略；若只传其一，返回 400。

**校验规则**

| 场景 | 校验逻辑 | 失败返回 |
|------|----------|---------|
| `provider` 与 `model` 只传其一 | 互斥校验 | 400 `INVALID_PARAMS` |
| `provider` 不在用户已激活配置中 | 查 UserServiceConfig，is_active=True | 400 `PROVIDER_NOT_CONFIGURED` |
| `provider` 的 `is_active=False` | 同上 | 400 `PROVIDER_NOT_CONFIGURED` |
| `model` 不在动态列表 ∪ 白名单中 | 白名单在 selectors.py 常量中定义 | 400 `INVALID_MODEL` |
| 二者均省略，且 resolve_default 返回 None | 无可用 provider | 400 `NO_PROVIDER_AVAILABLE` |

**成功响应（SSE done 事件额外携带字段）**

SSE 流最后一帧 `done=true` 中新增：

```json
{
  "done": true,
  "used_doc_ids": ["doc-1"],
  "used_provider": "llm_volcano",
  "used_model": "doubao-pro-32k"
}
```

前端收到 `done=true` 后，无需额外调用 `/preference/`（偏好由后端在 Content 保存时一并写入，见第 2.3 节选型结论）。

**失败响应**

| HTTP 状态 | error_code | 场景 |
|-----------|------------|------|
| 400 | `INVALID_PARAMS` | provider/model 只传其一 |
| 400 | `PROVIDER_NOT_CONFIGURED` | service_type 未在用户配置中 |
| 400 | `INVALID_MODEL` | model 不在合法集合 |
| 400 | `NO_PROVIDER_AVAILABLE` | 无任何可用 provider（无配置/全 false） |
| 401 | — | 未登录 |
| 502 | `UPSTREAM_ERROR` | 第三方 API 调用失败（含 provider/model 信息） |

502 响应 body 示例：

```json
{
  "error": "LLM 调用失败",
  "error_code": "UPSTREAM_ERROR",
  "provider": "llm_volcano",
  "model": "doubao-pro-32k",
  "upstream_status": 429
}
```

> 注意：当前 GenerateContentView 使用 SSE StreamingHttpResponse，4xx 错误发生在流建立前，以普通 JSON Response 返回；502 发生在流建立后，以 SSE error 事件返回（与现有 `views.py:144` 逻辑一致，在 `_sync_sse_generator` 中）。

---

### 2.3 新增 `PUT /api/v1/llm/preference/`

**选型结论：偏好由后端在生成成功后自动写入（方案 A），不提供独立 PUT 接口。**

**理由**：
1. 偏好触发点是"成功生成"这个后端事件，后端天然知道何时写入，无需前端额外一次网络请求。
2. 前端不需要感知写入时机，降低前后端耦合；如果提供独立 PUT 接口，前端需要处理"生成成功 → 调 /preference/ → 如果 /preference/ 失败怎么办"的额外状态机。
3. 后端原子性更好：Content 记录与偏好记录在同一请求生命周期内写入，无跨请求不一致风险。

**结论**：`PUT /api/v1/llm/preference/` 本期不新增。如未来有"用户在不生成的情况下手动设置默认模型"需求，再按 PUT 接口规范扩展。

---

## 3. 数据模型变更

### 3.1 `UserServiceConfig`（settings_vault/models.py）

**字段现状核查**（来自 `apps/settings_vault/models.py`）：

- `is_active: BooleanField(default=True)` — 已存在：表示该配置是否被用户启用（用户可手动停用）
- `last_validated_at: DateTimeField(null=True)` — 已存在（v1.1 migration 0003）：记录最近一次 TestAndSaveView 验证成功时间
- **缺失**：无 `last_test_ok` 布尔字段 —— 当前"测试是否通过"的状态需从 `is_active` 与 `last_validated_at` 推断，语义模糊

**本次新增字段**：

```
last_tested_at: DateTimeField(null=True, blank=True)
```

> 命名采用 `last_tested_at` 而非 `last_test_ok`，与已有 `last_validated_at` 区分语义：
> - `last_validated_at`：由 TestAndSaveView 触发的主动 key 验证时间
> - `last_tested_at`：（预留）供未来连通性探活（不是 key 验证）使用，本期 migration 加字段但不填充值

**关于 requirements.md 中提到的 `last_test_ok` 字段**：当前模型中不存在此布尔字段。在 providers 聚合响应中，`last_test_ok` 字段的值由以下逻辑计算得出：

```
last_test_ok = (is_active == True) AND (last_validated_at IS NOT NULL)
```

此计算在 selectors.py 中完成，不新增 DB 列（避免双写不一致）。如未来需要持久化该状态，再做单独 migration。

**Migration**：`apps/settings_vault/migrations/0004_userserviceconfig_last_tested_at.py`

---

### 3.2 新建 `UserLLMPreference`（llm_gateway/models.py）

**选型说明**（对应 OPEN-01）：选择新建独立表，而非在 UserServiceConfig 中加 `last_used_model` 字段。

**理由**：UserServiceConfig 的语义是"服务连接配置"（含加密 key），UserLLMPreference 的语义是"使用偏好"，二者职责不同，混用会导致 settings_vault app 职责扩散到 UX 偏好领域。

**字段定义**：

```
表名：llm_gateway_userllmpreference（Django 默认命名）

user         : OneToOneField(User, on_delete=CASCADE, related_name="llm_preference")
service_type : CharField(max_length=30)   # 与 UserServiceConfig.service_type 同域，无 FK 依赖（松耦合）
model        : CharField(max_length=64)
updated_at   : DateTimeField(auto_now=True)
```

**约束**：
- OneToOneField 自带唯一约束（一个用户只有一条偏好记录）
- 不加 ForeignKey 指向 UserServiceConfig：偏好失效检测在 selectors.py 运行时做，不依赖 DB 约束（避免 provider 被删时级联清掉偏好记录，更灵活）

**Migration**：`apps/llm_gateway/migrations/0001_userllmpreference.py`

---

### 3.3 `Content`（content/models.py）

当前 Content 表（`db_table="content_content"`，来自 `apps/content/models.py`）无 provider/model 字段。

**新增字段**：

```
provider : CharField(max_length=32, null=True, blank=True)   # 如 "llm_deepseek"
model    : CharField(max_length=64, null=True, blank=True)   # 如 "deepseek-chat"
```

**约束**：
- 均为 nullable，旧数据保持 NULL，向后兼容
- 不加 db_index（审计场景低频查询，无需索引）
- ContentSerializer 不暴露这两个字段（前端列表不展示，决策 Q5-B）

**Migration**：`apps/content/migrations/0002_content_provider_model.py`

---

### 3.4 Migration 执行顺序与回滚

**依赖顺序**（按 Django migration dependencies 声明）：

```
① settings_vault 0004_userserviceconfig_last_tested_at
     depends_on: settings_vault 0003_userserviceconfig_last_validated_at

② llm_gateway 0001_userllmpreference
     depends_on: accounts 0001_initial
     （llm_gateway 目前无 migrations 目录，本次首次创建）

③ content 0002_content_provider_model
     depends_on: content 0001_initial
```

三者互相无依赖，可并行执行，但建议按顺序 ①②③ 逐步迁移，便于逐步回滚。

**零停机保证**：三个 migration 均为"仅加字段"（nullable，无数据回填，无重命名），底层 DDL 为 `ALTER TABLE ADD COLUMN`，PostgreSQL 对 nullable 字段的此操作为元数据修改，不锁表，可在线执行。

**回滚命令**：

```bash
# 回滚 content 审计字段
python manage.py migrate content 0001_initial

# 回滚 llm_gateway preference 表
python manage.py migrate llm_gateway zero

# 回滚 settings_vault last_tested_at 字段
python manage.py migrate settings_vault 0003_userserviceconfig_last_validated_at
```

---

## 4. 后端模块设计

### 4.1 新增 `apps/llm_gateway/selectors.py`

此模块封装所有"读+决策"逻辑，View 只负责解析请求/构建响应，Provider 只负责 LLM 调用。

**白名单常量（OPEN-02 选型：代码常量，本期不做 DB 配置表）**

```
MODEL_WHITELIST = {
    "llm_deepseek": [
        {"id": "deepseek-chat",     "label": "DeepSeek V3"},
        {"id": "deepseek-reasoner", "label": "DeepSeek R1"},
    ],
    "llm_volcano": [
        {"id": "doubao-pro-4k",  "label": "豆包 Pro 4k"},
        {"id": "doubao-pro-32k", "label": "豆包 Pro 32k"},
    ],
}
```

> 说明（OPEN-02 选型理由）：当前 Ark model ID 有日期后缀，频繁变动，DB 配置表需要额外运维工具界面，复杂度高且收益低。选择代码常量，更新时发版，与已有 CI/CD 流程一致。未来如需运维热更新，可迁移到 DB。

**`list_available_providers(user) -> dict`**

伪代码：

```
function list_available_providers(user):
    configs = UserServiceConfig.objects.filter(
        user=user,
        service_type__startswith="llm_",
        is_active=True
    )

    # 计算 user_preference（实时校验偏好是否仍有效）
    try:
        pref = user.llm_preference  # OneToOne，不存在时抛 RelatedObjectDoesNotExist
        pref_valid = configs.filter(
            service_type=pref.service_type,
            last_validated_at__isnull=False   # 曾经验证过
        ).exists()
        user_preference = {"service_type": pref.service_type, "model": pref.model} if pref_valid else null
    except UserLLMPreference.DoesNotExist:
        user_preference = null

    # 并行拉取各 provider 的 model 列表（线程池，800ms 超时）
    providers_payload = []
    warnings = []
    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        futures = {pool.submit(_fetch_models_with_fallback, cfg): cfg for cfg in configs}
        for future, cfg in futures.items():
            models, source, warn = future.result()   # 内部已处理超时
            last_test_ok = (cfg.last_validated_at is not None)
            providers_payload.append({
                "service_type": cfg.service_type,
                "label": PROVIDER_LABELS[cfg.service_type],
                "configured": True,
                "last_test_ok": last_test_ok,
                "models_source": source,
                "models": models,
            })
            if warn:
                warnings.append(warn)

    # 计算系统默认值（决策链，不依赖 user_preference）
    default = _compute_system_default(configs)

    return {
        "default": default,
        "user_preference": user_preference,
        "providers": providers_payload,
        "warnings": warnings,
    }


function _fetch_models_with_fallback(cfg):
    # 实例化 provider，调用 list_models()，超时则 fallback
    try:
        config = decrypt(cfg.encrypted_config)
        provider_instance = get_provider(cfg.service_type, config)
        models = provider_instance.list_models()   # 内部 800ms 超时 + raise on fail
        return models, "dynamic", null
    except (TimeoutError, LLMModelsError):
        label = PROVIDER_LABELS[cfg.service_type]
        return MODEL_WHITELIST[cfg.service_type], "fallback", f"{label}模型列表加载失败，使用默认列表"


function _compute_system_default(configs):
    # 决策链：仅考虑系统默认，不考虑 user_preference
    deepseek_cfg = configs.filter(service_type="llm_deepseek").first()
    if deepseek_cfg and deepseek_cfg.last_validated_at is not None:
        return {"service_type": "llm_deepseek", "model": "deepseek-chat"}
    # deepseek 不可用，找任意可用的（按 -updated_at 取第一个）
    fallback_cfg = configs.filter(last_validated_at__isnull=False).order_by("-updated_at").first()
    if fallback_cfg:
        first_model = MODEL_WHITELIST[fallback_cfg.service_type][0]["id"]
        return {"service_type": fallback_cfg.service_type, "model": first_model}
    return null
```

**`resolve_default(user) -> (service_type, model) | None`**

伪代码：

```
function resolve_default(user):
    # 1. 检查用户偏好
    try:
        pref = user.llm_preference
        cfg = UserServiceConfig.objects.filter(
            user=user,
            service_type=pref.service_type,
            is_active=True,
            last_validated_at__isnull=False
        ).first()
        if cfg:
            return (pref.service_type, pref.model)
    except UserLLMPreference.DoesNotExist:
        pass

    # 2. 默认 deepseek-chat
    configs = UserServiceConfig.objects.filter(
        user=user, service_type__startswith="llm_", is_active=True
    )
    deepseek = configs.filter(
        service_type="llm_deepseek", last_validated_at__isnull=False
    ).first()
    if deepseek:
        return ("llm_deepseek", "deepseek-chat")

    # 3. 降级到 -updated_at 最近的有效 provider
    fallback = configs.filter(
        last_validated_at__isnull=False
    ).order_by("-updated_at").first()
    if fallback:
        first_model = MODEL_WHITELIST[fallback.service_type][0]["id"]
        return (fallback.service_type, first_model)

    # 4. 无可用 provider
    return None
```

> 注意：`resolve_default` 内部对 UserServiceConfig 的查询全部使用 `.filter(...).first()`（加了筛选条件），消除了原 `views.py:69-73` 无序 `.first()` BUG（FR-LLM-SEL-08）。

**`validate_choice(user, service_type, model) -> None | raise ValidationError`**

伪代码：

```
function validate_choice(user, service_type, model):
    # 校验 service_type 在白名单（防枚举攻击，NFR-04）
    if service_type not in MODEL_WHITELIST:
        raise ValidationError(code="INVALID_PROVIDER")

    # 校验用户有该 provider 的有效配置
    cfg = UserServiceConfig.objects.filter(
        user=user,
        service_type=service_type,
        is_active=True
    ).order_by("-updated_at").first()
    if not cfg:
        raise ValidationError(code="PROVIDER_NOT_CONFIGURED")

    # 校验 model 在合法集合（白名单 ∪ 动态拉取，此处仅校验白名单，简化实现）
    valid_model_ids = [m["id"] for m in MODEL_WHITELIST.get(service_type, [])]
    if model not in valid_model_ids:
        raise ValidationError(code="INVALID_MODEL")
```

> 校验 model 时只校验白名单（不在请求路径中再次调用 /models 接口，避免延迟）。用户在前端看到的 model 列表包含动态拉取结果，但后端校验只用白名单做第一道防线，防止恶意构造 model id。动态 model 如需严格校验，可在 selectors 中维护 session 级缓存（future work）。

---

### 4.2 修改 `apps/llm_gateway/providers.py`

**`get_provider(service_type, config, model=None)` 签名扩展**

```
function get_provider(service_type, config, model=None):
    if service_type == "llm_deepseek":
        effective_model = model or config.get("model_name", "deepseek-chat")
        return DeepSeekProvider(api_key=config["api_key"], model=effective_model, ...)
    if service_type == "llm_volcano":
        effective_model = model or config.get("model_name", "doubao-pro-4k")
        return VolcanoProvider(api_key=config["api_key"], model=effective_model, ...)
    raise ValueError(f"Unknown LLM service type: {service_type}")
```

> `model` 参数显式传入时优先于 config 中的 `model_name`（解决原逻辑 model 固化在 config 中无法覆盖的问题）。

**各 Provider 新增 `list_models() -> List[dict]`**

`DeepSeekProvider.list_models()`：

```
function list_models():
    # DeepSeek /v1/models 端点（OpenAI 兼容）
    with httpx.Client(timeout=0.8) as client:  # 800ms 超时
        resp = client.get(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        resp.raise_for_status()
        data = resp.json()
        # 仅返回 id 以 "deepseek-" 开头的 model（过滤噪音）
        return [
            {"id": m["id"], "label": _deepseek_label(m["id"])}
            for m in data.get("data", [])
            if m["id"].startswith("deepseek-")
        ]
    # 若 raise → selectors._fetch_models_with_fallback 捕获，返回白名单
```

`VolcanoProvider.list_models()`：

```
function list_models():
    # Ark /api/v3/models 端点（RISK-01 假阳性风险：见下方说明）
    with httpx.Client(timeout=0.8) as client:
        resp = client.get(
            "https://ark.cn-beijing.volces.com/api/v3/models",
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        resp.raise_for_status()
        data = resp.json()
        # RISK-01 对策：仅展示 id 在 MODEL_WHITELIST["llm_volcano"] 中的 model
        # 这样动态接口只起"验证白名单 id 是否仍存在"的作用，不新增未验证的 id
        whitelist_ids = {m["id"] for m in MODEL_WHITELIST["llm_volcano"]}
        return [
            {"id": m["id"], "label": _volcano_label(m["id"])}
            for m in data.get("data", [])
            if m["id"] in whitelist_ids
        ]
```

> RISK-01 关键对策：VolcanoProvider.list_models() 的返回结果不是"Ark 返回了什么就展示什么"，而是"Ark 确认白名单中的哪些 id 仍然有效"。这样既动态（白名单 id 下线时前端会隐藏），又安全（不展示未经真实业务端点验证的新 id）。

---

### 4.3 修改 `apps/llm_gateway/views.py`

**新增 `ProvidersView`**

```
class ProvidersView(APIView):
    def get(self, request):
        payload = list_available_providers(request.user)
        response = Response(payload)
        response["Cache-Control"] = "no-store"
        return response
```

**`GenerateContentView` 重构**

当前 GET 方法（`views.py:57`）重构为同时支持 GET（向后兼容）和 POST：

```
class GenerateContentView(APIView):
    def _parse_params(self, request):
        # POST: from request.data; GET: from request.query_params
        if request.method == "POST":
            source = request.data
        else:
            source = request.query_params
        return {
            "prompt":    source.get("prompt", "").strip(),
            "platform":  source.get("platform", "general"),
            "style":     source.get("style", "professional"),
            "word_limit": source.get("word_limit"),
            "use_kb":    source.get("use_kb", "true") in (True, "true", "1"),
            "provider":  source.get("provider"),
            "model":     source.get("model"),
        }

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)

    def _handle(self, request):
        params = self._parse_params(request)

        # 1. 校验 prompt
        if not params["prompt"]:
            return Response({"error": "prompt 不能为空"}, status=400)

        # 2. 校验 provider/model 参数互斥
        provider_param = params["provider"]
        model_param = params["model"]
        if bool(provider_param) != bool(model_param):
            return Response({"error": "provider 与 model 必须同时传或同时省略",
                             "error_code": "INVALID_PARAMS"}, status=400)

        # 3. 解析实际使用的 provider/model
        try:
            if provider_param and model_param:
                validate_choice(request.user, provider_param, model_param)
                service_type, model_id = provider_param, model_param
            else:
                result = resolve_default(request.user)
                if result is None:
                    return Response({"error": "无可用 LLM provider，请先在设置页面配置 API Key",
                                     "error_code": "NO_PROVIDER_AVAILABLE"}, status=400)
                service_type, model_id = result
        except ValidationError as e:
            return Response({"error": str(e), "error_code": e.code}, status=400)

        # 4. 加载 provider 配置（修复 .first() BUG：用 service_type 精确查）
        try:
            llm_cfg = UserServiceConfig.objects.filter(
                user=request.user,
                service_type=service_type,
                is_active=True,
            ).order_by("-updated_at").first()
            config = decrypt(bytes(llm_cfg.encrypted_config))
            provider_instance = get_provider(service_type, config, model=model_id)
        except Exception as e:
            logger.exception("LLM provider init failed: provider=%s model=%s", service_type, model_id)
            return Response({"error": f"LLM 配置加载失败：{e}"}, status=500)

        # 5. KB 搜索（不动）
        # ... （与现有逻辑相同）

        # 6. 构建 messages（不动）
        # ...

        # 7. SSE 响应（传入 provider/model，供 generator 写审计日志和偏好）
        response = StreamingHttpResponse(
            _sync_sse_generator(provider_instance, messages, used_doc_ids,
                                service_type=service_type, model=model_id,
                                user=request.user),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
```

**`_sync_sse_generator` 扩展**

在 SSE 流正常结束时（`done=True` 且无 error），额外执行：

```
# 写 Content 审计字段（假设 content_id 已在此函数中创建）
Content.objects.filter(id=content_id).update(provider=service_type, model=model)

# 写用户偏好
UserLLMPreference.objects.update_or_create(
    user=user,
    defaults={"service_type": service_type, "model": model}
)

# done 事件携带 used_provider/used_model
yield f"data: {json.dumps({'done': True, 'used_doc_ids': ..., 'used_provider': service_type, 'used_model': model})}\n\n"
```

> 注意：当前 `_sync_sse_generator` 是纯流函数，不负责创建 Content 记录（Content 创建在前端收到完整文本后调用 `/api/v1/contents/` 接口）。实际实现时，provider/model 信息应通过 SSE done 事件传给前端，前端在创建 Content 记录时一并传入，或后端在 SSE 完成后异步写入。**具体实现方式留给 software-developer 在开发阶段确认**，此处给出两种均可行的路径。

---

### 4.4 新增路由（urls.py）

```
urlpatterns = [
    path("generate/",  GenerateContentView.as_view(), name="llm-generate"),
    path("providers/", ProvidersView.as_view(),        name="llm-providers"),
]
```

> `preference/` 本期不新增（见第 2.3 节选型结论）。

---

### 4.5 日志/可观测性

所有 LLM 调用均通过 `_sync_sse_generator` 执行，在以下位置新增结构化日志：

**成功路径**（SSE 流正常结束）：

```python
logger.info(
    "llm_generate success",
    extra={
        "provider": service_type,
        "model": model_id,
        "latency_ms": round((time.monotonic() - t_start) * 1000),
        "success": True,
    }
)
```

**失败路径**（`views.py:144` 对应的 except 分支）：

```python
logger.error(
    "llm_generate error",
    extra={
        "provider": service_type,
        "model": model_id,
        "latency_ms": round((time.monotonic() - t_start) * 1000),
        "success": False,
        "error_code": type(exc).__name__,
    },
    exc_info=True,
)
```

沿用现有 `logger = logging.getLogger(__name__)` 配置，不引入新依赖。

---

## 5. 前端模块设计

### 5.1 新增组件 `src/components/LlmSelector.vue`

**Props**

```javascript
defineProps({
  modelValueProvider: String,   // v-model:provider
  modelValueModel:    String,   // v-model:model
  providers:          Array,    // ProvidersPayload.providers[]
  userPreference:     Object,   // ProvidersPayload.user_preference
  systemDefault:      Object,   // ProvidersPayload.default
  warnings:           Array,    // ProvidersPayload.warnings[]
  loading:            Boolean,
  disabled:           Boolean,
})
```

**Emits**：`update:provider`、`update:model`

**内部结构**

```
LlmSelector.vue
├── [顶部警告条] v-if="warnings.length > 0"
│     el-alert type="warning" → 展示 warnings[0]（或合并多条）
│
├── [主下拉] el-select（v-model 绑定内部 selectedKey = `{service_type}::{model}`）
│     el-option-group v-for="provider in providers"（仅 configured && last_test_ok 的 provider 展示）
│       el-option v-for="m in provider.models"
│         label = provider.label + " / " + m.label
│         value = `{provider.service_type}::{m.id}`
│         disabled = !provider.last_test_ok
│
└── [空状态] v-if="noAvailableProviders"
      el-empty description="请前往设置页配置 LLM"
      el-button → router-push("/settings")
```

**未配置/测试失败 provider 的展示**：展示但置灰（disabled + el-tooltip 提示"该服务未配置或测试未通过"），不隐藏，便于用户了解有哪些 provider 可以配置。

**自动选中逻辑（组件内部，onMounted）**：

```
priority_1 = user_preference（如果 preference provider 在 providers[] 中且 last_test_ok=true）
priority_2 = system_default
priority_3 = null → emit("update:provider", null)
```

---

### 5.2 修改 `WorkspaceView.vue`

**onMounted**：

```javascript
const llmStore = useLlmStore()
await llmStore.fetchProviders()
```

**表单新增 LlmSelector 一列**（在现有 platform/style/word_limit 之后）：

```html
<LlmSelector
  v-model:provider="form.provider"
  v-model:model="form.model"
  :providers="llmStore.providers"
  :user-preference="llmStore.userPreference"
  :system-default="llmStore.systemDefault"
  :warnings="llmStore.warnings"
  :loading="llmStore.loading"
/>
```

**生成按钮禁用条件**（新增）：

```javascript
const generateDisabled = computed(() =>
  !form.provider || !form.model || llmStore.noAvailableProviders
)
```

**提交时**：POST body 中加入 `provider: form.provider, model: form.model`

**SSE done 事件处理**：收到 `done=true` 后，从 `used_provider`/`used_model` 更新 `llmStore.userPreference`（本地乐观更新，无需额外请求）。

---

### 5.3 Pinia store `src/stores/llm.js`

```javascript
export const useLlmStore = defineStore("llm", {
  state: () => ({
    providers:      [],
    userPreference: null,
    systemDefault:  null,
    warnings:       [],
    loading:        false,
    error:          null,
  }),

  getters: {
    noAvailableProviders: (state) =>
      state.providers.filter(p => p.configured && p.last_test_ok).length === 0,
  },

  actions: {
    async fetchProviders() {
      this.loading = true
      this.error = null
      try {
        const data = await apiClient.get("/api/v1/llm/providers/")
        this.providers      = data.providers
        this.userPreference = data.user_preference
        this.systemDefault  = data.default
        this.warnings       = data.warnings
      } catch (e) {
        this.error = e
      } finally {
        this.loading = false
      }
    },

    // 生成成功后由 WorkspaceView 调用（乐观更新，不发请求）
    updatePreferenceLocally(serviceType, model) {
      this.userPreference = { service_type: serviceType, model }
    },
  },
})
```

---

### 5.4 i18n 文案（中英双语）

| 键名 | 中文 | 英文 |
|------|------|------|
| `llm.selector.label` | 选择模型 | Select Model |
| `llm.selector.loading` | 加载模型列表中… | Loading models… |
| `llm.selector.no_models_fallback` | 模型列表加载失败，使用默认列表 | Model list unavailable, using defaults |
| `llm.selector.not_configured` | 该服务未配置或测试未通过 | Service not configured or test failed |
| `llm.selector.empty_hint` | 请前往设置页配置 LLM | Please configure LLM in Settings |
| `llm.error.no_provider` | 无可用 LLM 服务，请先配置 API Key | No LLM provider available, please configure API Key |
| `llm.error.invalid_model` | 所选模型不可用，请重新选择 | Selected model is unavailable, please reselect |
| `llm.error.upstream_failed` | 模型调用失败，请检查 API Key 是否有效 | Model call failed, please check your API Key |
| `llm.generate.disabled_hint` | 请先配置 DeepSeek 服务，或选择其他已配置的模型 | Please configure DeepSeek or select another configured model |

---

## 6. 错误与边界处理

| 场景 | 触发条件 | 后端响应 | 前端表现 |
|------|----------|---------|---------|
| 用户未登录 | 请求无有效认证 | 401 | 重定向到登录页（现有逻辑） |
| 用户无任何 LLM 配置 | providers 返回空数组 | GET /providers/ 200，providers=[] | 下拉禁用，生成按钮禁用，提示"请先配置 LLM" |
| 用户仅有 DeepSeek 但 last_validated_at=null（从未测试通过） | last_test_ok=false | GET /providers/ 200，provider last_test_ok=false | DeepSeek 选项 disabled+tooltip，生成按钮禁用 |
| /models 双 provider 均 800ms 超时 | list_models() 均 raise TimeoutError | 200，两 provider models_source="fallback"，warnings 含两条 | 两个分组各有橙色 fallback 提示，仍可选择白名单 model |
| /models 仅一方超时 | 如 VolcanoProvider.list_models() 超时 | 200，llm_volcano models_source="fallback"，warnings 含一条 | 仅火山引擎分组提示 fallback，DeepSeek 正常 |
| 生成时 provider/model 与可用列表不匹配（含伪造） | validate_choice 失败 | 400 INVALID_PROVIDER 或 INVALID_MODEL | el-message error，文案来自 i18n llm.error.invalid_model |
| 第三方 API 限流（429） | LLM API 返回 429 | SSE error 事件，含 upstream_status=429 | SSE error 事件解析后 el-message error："模型调用失败" + 提示检查 key |
| 第三方 API 鉴权失败（401/403） | LLM API 返回 401/403 | SSE error 事件，含 upstream_status=401 | 前端展示"API Key 无效，请在设置页更新" |
| 第三方余额不足（通常 402 或特定错误码） | LLM API 返回 402 或含余额错误的消息 | SSE error 事件 | 展示"账户余额不足，请充值" |
| 用户选完后去设置页删除该 key，再回来生成 | UserServiceConfig 已删除或 is_active=False | validate_choice 返回 400 PROVIDER_NOT_CONFIGURED | 前端展示 400 错误；用户刷新页面后 /providers/ 将不再包含该 provider，下拉自动更新 |
| 用户选完后去设置页删除 key，**偏好记录保存失败 OK 还是 FAIL？** | 生成成功后写 UserLLMPreference 时 service_type 对应 config 已不存在 | **OK（静默写入，偏好持久化不是关键路径）**：偏好写入失败不影响文案生成结果，仅记录 warning 日志；下次进入 /providers/ 时偏好实时校验发现失效，自动降级到 system_default | 前端无感知（偏好只是"下次自动选中"，偏好丢失不影响当次生成） |

---

## 7. 测试设计要点

### 7.1 后端单元测试

**决策链 4 条分支（`selectors.py` → `resolve_default`）**：

1. 有有效偏好 + 偏好 provider 仍有效 → 返回偏好值
2. 有偏好但 provider 已失效 + deepseek 有效 → 返回 deepseek-chat
3. 无偏好 + deepseek 有效 → 返回 deepseek-chat
4. 无偏好 + deepseek 无效 + 其他 provider 有效 → 返回 updated_at 最近的 provider + 白名单第一个 model
5. 全部无效 → 返回 None

**`.first()` BUG 修复回归（FR-LLM-SEL-08）**：

- 构造两条 UserServiceConfig（llm_deepseek updated_at 旧，llm_volcano updated_at 新），不传 provider 参数
- 断言 resolve_default 返回 llm_volcano（而非 llm_deepseek）
- 断言 GenerateContentView 使用 service_type=llm_volcano

**Content 审计字段写入**：

- mock SSE 流正常结束
- 断言 Content 记录 provider/model 字段非 null，值与请求一致

**超时 fallback**：

- mock `VolcanoProvider.list_models()` sleep 超过 800ms（或直接 raise TimeoutError）
- 断言 list_available_providers 返回 models_source="fallback" + warnings 含提示文案

**白名单校验防枚举攻击**：

- 传入 service_type="llm_fake" → validate_choice 抛 ValidationError(code="INVALID_PROVIDER")
- 传入合法 service_type + 非白名单 model → ValidationError(code="INVALID_MODEL")

**Canary 守卫测试（防回归）**：

```python
def test_default_model_is_deepseek_chat():
    """Canary: 确保系统默认 model 仍是 deepseek-chat，防止白名单误修改。"""
    from apps.llm_gateway.selectors import MODEL_WHITELIST
    assert MODEL_WHITELIST["llm_deepseek"][0]["id"] == "deepseek-chat"
```

### 7.2 集成测试

- `GET /api/v1/llm/providers/`：有配置用户 → 200 含 providers；无配置用户 → 200 providers=[]
- `POST /api/v1/llm/generate/`：传合法 provider+model → SSE 流 done 含 used_provider/used_model；传非法 provider → 400 PROVIDER_NOT_CONFIGURED

### 7.3 E2E 测试（Playwright）

参考记忆 `feedback_e2e_playwright_patterns.md` 中的 el-select 定位坑：

- **el-select 定位**：不要用 `.locator("el-select")`，应用 `page.locator(".el-select")` 配合父容器约束
- **getByText 多匹配问题**：模型名称可能在 tooltip 和 option 中同时出现，应使用 `page.locator(".el-select-dropdown__item").filter({hasText: "DeepSeek V3"}).first()`
- **el-input-number 延迟**：word_limit 如使用 el-input-number，需 `await page.waitForTimeout(100)` 后再取值断言
- **h1 重复问题**：WorkspaceView 可能存在多个标题元素，用 `page.locator("h1").first()` 或更精确的选择器

E2E 场景：

1. 用户首次进入（有 deepseek 配置）→ 下拉默认选中 DeepSeek V3 → 生成成功
2. 用户切换到火山引擎 → 生成成功 → 关闭页面 → 再次打开 → 下拉默认选中火山引擎（偏好记忆）
3. 无配置用户 → 下拉禁用 → 生成按钮不可点击

### 7.4 提交前测试规则（CLAUDE.md）

```bash
cd project_workspace/content_gen_platform/src/backend
pytest apps/ tests/ -m "not integration" --tb=short -q
```

新增单元测试文件：
- `apps/llm_gateway/tests/test_selectors.py`
- `apps/llm_gateway/tests/test_providers_view.py`

---

## 8. 风险与回滚

### RISK-01：Ark /models 假阳性（已在第 4.2 节给出对策）

**来源**：记忆 `feedback_ark_model_id_format.md`

**对策（本期实现）**：
- VolcanoProvider.list_models() 返回结果限定为"Ark 确认白名单中仍存在的 id"，不新增未验证 id
- 白名单 id 必须是经过真实业务端点验证的 id（开发期必须真调一次 `/chat/completions`）
- 调用失败明确 fallback + 前端可见提示，不静默

**后续 future work（本期不做）**：
- CI 增加冒烟守卫：每周自动以业务端点调一次白名单 model，失败时告警
- 考虑对 list_models() 结果做 dry-run（发一条 1 token 的消息）验证可用性

### RISK-02：用户偏好与 key 撤销不同步

**对策**：selectors.list_available_providers() 每次实时校验 user_preference 是否仍对应有效 provider，失效则返回 `user_preference: null` + 降级到 system_default，前端不预选失效 provider。

### RISK-03：Migration 字段加错

**对策**：全部字段 nullable，迁移可零停机执行，回滚命令见第 3.4 节。

### Feature Flag：`FEATURE_LLM_SELECTOR`

建议在 Django settings 中新增：

```python
FEATURE_LLM_SELECTOR = os.getenv("FEATURE_LLM_SELECTOR", "true") == "true"
```

**关闭时行为**：
- `GET /api/v1/llm/providers/` 返回 404 或 403（前端检测后跳过下拉渲染）
- `POST /api/v1/llm/generate/` 忽略 provider/model 参数，走旧 `.filter(service_type__startswith="llm_").first()` 逻辑（但 BUG 已修复为 order_by）
- 前端 LlmSelector 组件 v-if="featureEnabled"

**灰度策略**：

```
staging 验证（内部测试）→ 对内部用户 uid 白名单开放 → 全量开放
```

---

## 9. 工作量估算与 PR 拆分建议

| PR | 内容 | 涉及文件 | 估算人日 |
|----|------|---------|---------|
| PR-1 | 数据迁移：3 个 migration + 模型定义（UserLLMPreference、Content 审计字段、UserServiceConfig last_tested_at） | models.py x3, migrations x3 | 0.5 天 |
| PR-2 | 后端 selectors.py + providers.py 扩展（list_models、get_provider 扩展、白名单） | selectors.py（新），providers.py | 1.5 天 |
| PR-3 | 后端 views.py + urls.py：ProvidersView + GenerateContentView 改 POST + 日志 + 偏好写入 | views.py, urls.py + 单元测试 | 1.5 天 |
| PR-4 | 前端：LlmSelector.vue + useLlmStore + WorkspaceView 接入 + i18n | LlmSelector.vue, llm.js, WorkspaceView.vue | 2 天 |
| PR-5 | E2E 测试 + CI 守卫 | playwright tests, test_selectors.py Canary | 1 天 |

**总估算：6.5 人天**

**PR 依赖顺序**：PR-1 → PR-2 → PR-3（后端可先合并） → PR-4 → PR-5

---

## 10. 开发就绪自检表（Pre-Development Gate）

| 项目 | 状态 | 说明 |
|------|------|------|
| requirements.md 已确认 | ✅ | 阶段 1+2 APPROVED |
| user_stories.md 已确认 | ✅ | 阶段 1+2 APPROVED |
| design.md（本文档）已完成 | ✅ 待用户确认 | 阶段 3 产出 |
| 无未决架构开放问题 | ✅ | OPEN-01（UserLLMPreference 独立表）、OPEN-02（代码常量白名单）均已决断 |
| GET→POST 向后兼容策略已明确 | ✅ | 保留 GET 路由，同一 View 双入口，GET 在 v2 才废弃 |
| 偏好写入时机已决断 | ✅ | 后端生成成功后自动写入，不新增 PUT /preference/ |
| CLAUDE.md 提交前测试规则 | ✅ | 开发阶段每次 commit 前：`cd .../backend && pytest apps/ tests/ -m "not integration" --tb=short -q` |
| 记忆 feedback_ark_model_id_format.md 已纳入 RISK-01 | ✅ | list_models() 限定白名单 id，开发期必须真调业务端点 |
| 记忆 feedback_e2e_playwright_patterns.md 已纳入测试设计 | ✅ | el-select 定位方式、getByText 多匹配、延迟断言均已在第 7.3 节标注 |
| 记忆 feedback_ci_coverage_guards.md — pytest 扫描 apps/ | ✅ | 新增测试文件放 apps/llm_gateway/tests/，pytest 命令已包含 apps/ |
| Migration 零停机保证已验证 | ✅ | 全部 nullable 加字段，PostgreSQL ADD COLUMN 不锁表 |
| Feature Flag 方案已设计 | ✅ | FEATURE_LLM_SELECTOR 环境变量开关 |
| Content.serializers.py 不暴露 provider/model | ✅ 待开发确认 | 需在 PR-1 合并后确认 ContentSerializer 的 fields 列表不含新字段 |
