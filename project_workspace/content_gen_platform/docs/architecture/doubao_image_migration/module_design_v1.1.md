# 模块设计文档增量补丁：API Key 配置 UX 修复

**文档编号**：ARCH-MOD-IMG-001-PATCH  
**基准版本**：v1.0（ARCH-MOD-IMG-001，已决稿，2026-05-13）  
**本补丁版本**：v1.1  
**创建日期**：2026-05-14  
**最后更新**：2026-05-14  
**状态**：DRAFT — 等待 PM 门控评审  
**输入文档**：ARCH-DES-IMG-001-PATCH v1.1（ADR-08/ADR-09/ADR-10）、REQ-SPEC-IMG-001-PATCH v0.3（APPROVED）  
**作者**：system-architect 子代理（由 PM 编排）  
**阅读方式**：本文档为**增量补丁**，不重写 v1.0 内容。阅读时须与 ARCH-MOD-IMG-001 v1.0 联合使用。

---

## 一、变更摘要

| 变更类型 | 模块/文件 | 说明 | 关联 ADR |
|---------|---------|------|---------|
| **新增** | `apps/settings_vault/ark_validator.py` | Ark Key 验证函数，调用 `/api/v3/models` | ADR-08 |
| **新增** | `apps/settings_vault/views.py` 中 `ServiceStatusView` | GET 状态查询端点 | ADR-09 |
| **新增** | `apps/settings_vault/views.py` 中 `TestAndSaveView` | POST 原子测试+保存端点 | ADR-10 |
| **新增** | `apps/settings_vault/serializers.py` 中 `ServiceStatusSerializer` | 状态响应序列化 | ADR-09 |
| **新增** | `apps/settings_vault/serializers.py` 中 `TestAndSaveSerializer` | 测试+保存请求校验 | ADR-10 |
| **修改** | `apps/settings_vault/urls.py` | 新增两条路由 | ADR-09/10 |
| **修改** | `apps/settings_vault/models.py` | `_required_keys()` / `_test_connection()` 补 `doubao_image` 分支 | ADR-08 |
| **新增** | `src/views/SettingsView.vue` 中"豆包图片生成"Tab | 含 DoubaoImageKeyPanel 组件 | FR-6.1 |
| **新增** | `src/components/Settings/DoubaoImageKeyPanel.vue` | Key 输入框 + 测试连接按钮 | FR-6.1/6.2 |
| **修改** | `src/views/ImageGeneratorView.vue` | `onMounted` 新增预检逻辑 | FR-7.1 |
| **新增** | `src/components/ImageGenerator/PreflightBanner.vue` | 常驻预检 Banner，无关闭按钮 | FR-7.1、OQ-7=A |
| **修改** | `src/api/index.js` | 新增 service status API + test-and-save API | ADR-09/10 |
| **不变** | v1.0 所有其他模块 | ADR-01 至 ADR-07 范围内的实现不变 | — |

---

## 二、后端新增/修改模块详情

### 2.1 新增文件

#### `apps/settings_vault/ark_validator.py`（新增，ADR-08）

**关联需求**：FR-6.3、US-08 AC-08-3  
**关联 ADR**：ADR-08

```python
"""
Ark API Key 有效性验证模块。

安全约束：
  - api_key 参数禁止出现在任何日志语句中。
  - 异常消息禁止包含 api_key 内容。
  - 本模块不做任何持久化操作（单一职责：仅验证）。
"""
import logging
from typing import Tuple

import httpx

logger = logging.getLogger(__name__)

ARK_MODELS_URL = "https://ark.cn-beijing.volces.com/api/v3/models"
VALIDATE_TIMEOUT = 10.0  # 秒，防止 Ark 不可达时长时阻塞


def validate_doubao_key(api_key: str) -> Tuple[bool, str]:
    """
    调用 Ark GET /api/v3/models 接口验证 API Key 有效性。

    参数：
        api_key: 待验证的 Ark API Key（来自 settings_vault 解密或用户输入；禁止记录到日志）

    返回：
        Tuple[bool, str]
            - (True, "")           — Key 有效
            - (False, "ARK_KEY_INVALID")    — HTTP 401，Key 无效或已吊销
            - (False, "ARK_QUOTA_EXCEEDED") — HTTP 403，账号欠费或权限受限
            - (False, "ARK_UNREACHABLE")    — 网络错误、超时、5xx

    说明：
        本函数不抛出异常，所有错误均映射为返回值。
        关联 ADR-08 中的错误映射表。
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = httpx.get(
            ARK_MODELS_URL,
            headers=headers,
            timeout=VALIDATE_TIMEOUT,
        )
        if response.status_code == 200:
            return True, ""
        elif response.status_code == 401:
            logger.info("Ark key validation failed: 401 Unauthorized (key invalid or revoked)")
            return False, "ARK_KEY_INVALID"
        elif response.status_code == 403:
            logger.info("Ark key validation failed: 403 Forbidden (quota exceeded or permission denied)")
            return False, "ARK_QUOTA_EXCEEDED"
        else:
            logger.warning("Ark key validation failed: HTTP %d", response.status_code)
            return False, "ARK_UNREACHABLE"
    except httpx.TimeoutException:
        logger.warning("Ark key validation timed out after %.1fs", VALIDATE_TIMEOUT)
        return False, "ARK_UNREACHABLE"
    except httpx.ConnectError:
        logger.warning("Ark key validation: connection error (network unreachable)")
        return False, "ARK_UNREACHABLE"
    except Exception as exc:  # noqa: BLE001
        logger.error("Ark key validation: unexpected error: %s", type(exc).__name__)
        return False, "ARK_UNREACHABLE"
```

---

### 2.2 修改文件

#### `apps/settings_vault/views.py`（修改，新增两个视图类）

**关联 ADR**：ADR-09（ServiceStatusView）、ADR-10（TestAndSaveView）

**新增 `ServiceStatusView`**（ADR-09，FR-7.1）：

```python
class ServiceStatusView(generics.GenericAPIView):
    """
    查询当前用户指定服务类型的配置状态。

    GET /api/v1/users/me/services/<service_type>/status/

    安全约束：
      - 响应体不包含 api_key 值、Key 前缀或任何 Key 派生信息。
      - 仅返回 is_configured（bool）和 last_validated_at（datetime | null）。
      - 权限：IsAuthenticated（仅查询当前登录用户数据）。

    关联需求：FR-7.1、US-08 AC-08-1/AC-08-4、ADR-09
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceStatusSerializer

    def get(self, request: HttpRequest, service_type: str) -> Response:
        """
        参数：
            service_type: URL path 参数，如 "doubao_image"

        响应 200：
            {
              "is_configured": true | false,
              "last_validated_at": "2026-05-14T10:00:00Z" | null
            }
        """
        config = UserServiceConfig.objects.filter(
            user=request.user,
            service_type=service_type,
        ).first()

        if config is None:
            data = {"is_configured": False, "last_validated_at": None}
        else:
            data = {
                "is_configured": True,
                "last_validated_at": config.last_validated_at,
            }
        serializer = self.get_serializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
```

**新增 `TestAndSaveView`**（ADR-10，FR-6.3）：

```python
class TestAndSaveView(generics.GenericAPIView):
    """
    原子测试 Ark API Key 并保存（测试即保存，OQ-8=A）。

    POST /api/v1/users/me/services/<service_type>/test-and-save/

    流程：
      1. Serializer 校验 api_key 非空
      2. 调用 validate_doubao_key() 验权（ADR-08）
      3. 验证通过 → with transaction.atomic() 写入加密 UserServiceConfig
      4. 验证失败 → 直接返回 400，不写入数据库

    安全约束：
      - api_key 不出现在任何日志、响应体或异常消息中。
      - 响应体仅含 {"saved": true, "last_validated_at": "..."} 或错误码。
      - 权限：IsAuthenticated。

    关联需求：FR-6.1、FR-6.3、US-08 AC-08-3/AC-08-4、ADR-10
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TestAndSaveSerializer

    def post(self, request: HttpRequest, service_type: str) -> Response:
        """
        请求体：{"api_key": "<用户输入的 Ark API Key>"}

        成功响应 200：
            {"saved": true, "last_validated_at": "2026-05-14T10:00:00Z"}

        失败响应 400：
            {"error": "ARK_KEY_INVALID", "detail": "Key 无效或已吊销"}
          | {"error": "ARK_QUOTA_EXCEEDED", "detail": "账号欠费或权限受限"}
          | {"error": "ARK_UNREACHABLE", "detail": "Ark 服务暂时不可达，请稍后重试"}

        失败响应 502（仅用于 Ark 服务端 5xx 导致的不可达，与 400 error=ARK_UNREACHABLE 等价）：
            {"error": "ARK_UNREACHABLE", "detail": "..."}

        注：service_type 当前仅支持 "doubao_image"，其他类型返回 400。
        """
        if service_type != "doubao_image":
            return Response(
                {"error": "UNSUPPORTED_SERVICE_TYPE", "detail": f"service_type '{service_type}' 暂不支持测试连接"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key: str = serializer.validated_data["api_key"]

        is_valid, error_code = validate_doubao_key(api_key)
        if not is_valid:
            error_detail_map = {
                "ARK_KEY_INVALID":    "Key 无效或已吊销，请检查 Ark 控制台",
                "ARK_QUOTA_EXCEEDED": "账号欠费或权限受限，请检查账户余额",
                "ARK_UNREACHABLE":    "Ark 服务暂时不可达，请稍后重试",
            }
            return Response(
                {"error": error_code, "detail": error_detail_map.get(error_code, "未知错误")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.utils import timezone
        now = timezone.now()
        with transaction.atomic():
            UserServiceConfig.objects.update_or_create(
                user=request.user,
                service_type=service_type,
                defaults={
                    "encrypted_config": encrypt({"api_key": api_key}),
                    "last_validated_at": now,
                },
            )
        # api_key 在此函数作用域结束时由 Python GC 回收，不做任何日志记录
        return Response(
            {"saved": True, "last_validated_at": now.isoformat()},
            status=status.HTTP_200_OK,
        )
```

---

#### `apps/settings_vault/serializers.py`（修改，新增两个序列化器）

**新增 `ServiceStatusSerializer`**（ADR-09）：

```python
class ServiceStatusSerializer(serializers.Serializer):
    """
    GET /services/<service_type>/status/ 响应序列化。

    安全约束：响应体不含任何 Key 相关信息（仅 is_configured + last_validated_at）。
    关联需求：FR-7.1、ADR-09
    """
    is_configured: bool = serializers.BooleanField(read_only=True)
    last_validated_at: Optional[datetime] = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        format="%Y-%m-%dT%H:%M:%SZ",
    )
```

**新增 `TestAndSaveSerializer`**（ADR-10）：

```python
class TestAndSaveSerializer(serializers.Serializer):
    """
    POST /services/<service_type>/test-and-save/ 请求体校验。

    安全约束：
      - api_key 字段标记 write_only=True，禁止出现在任何序列化输出中。
      - 最小长度校验 min_length=1 确保空值被拒绝于 Serializer 层（不进入 validate_doubao_key）。

    关联需求：FR-6.3、ADR-10
    """
    api_key: str = serializers.CharField(
        min_length=1,
        max_length=512,
        write_only=True,
        trim_whitespace=True,
        help_text="Ark API Key（仅用于验证和保存，不出现在响应体中）",
    )
```

---

#### `apps/settings_vault/urls.py`（修改，新增两条路由）

```python
# 在现有 urlpatterns 追加：
urlpatterns += [
    path(
        "users/me/services/<str:service_type>/status/",
        ServiceStatusView.as_view(),
        name="service-status",
    ),
    path(
        "users/me/services/<str:service_type>/test-and-save/",
        TestAndSaveView.as_view(),
        name="service-test-and-save",
    ),
]
```

---

#### `apps/settings_vault/models.py`（修改，补 `doubao_image` 分支）

> v1.0 已将 `doubao_image` 加入 `SERVICE_CHOICES`（ADR-06）。本补丁补充 `_required_keys()` 和 `_test_connection()` 两处分支，以及新增 `last_validated_at` 字段。

**新增字段**（追加到 `UserServiceConfig` 模型）：

```python
last_validated_at = models.DateTimeField(
    null=True,
    blank=True,
    help_text="最近一次成功验证 Key 有效性的时间（由 TestAndSaveView 写入）",
)
```

**`_required_keys()` 补充 `doubao_image` 分支**：

```python
def _required_keys(self) -> list[str]:
    """
    返回当前 service_type 的必填配置 Key 列表。
    关联需求：FR-6.3（doubao_image 分支）、ADR-08
    """
    return {
        "doubao_image": ["api_key"],
        "llm_volcano":  ["api_key", "endpoint_id"],
        "llm_deepseek": ["api_key"],
        # ... 其他 service_type 保持不变 ...
    }.get(self.service_type, ["api_key"])
```

**`_test_connection()` 补充 `doubao_image` 分支**：

```python
def _test_connection(self) -> tuple[bool, str]:
    """
    测试当前 service_type 的连通性。
    doubao_image 分支：调用 Ark /api/v3/models（ADR-08，OQ-6=B）。
    安全约束：不在此函数中记录任何 Key 内容。
    """
    if self.service_type == "doubao_image":
        from apps.settings_vault.ark_validator import validate_doubao_key
        from core.encryption import decrypt
        config = decrypt(self.encrypted_config)
        api_key = config.get("api_key", "")
        return validate_doubao_key(api_key)
    # ... 其他 service_type 分支保持不变 ...
```

---

## 三、REST API Schema（新增端点）

### 3.1 `GET /api/v1/users/me/services/{service_type}/status/`（新增，ADR-09）

**权限**：`IsAuthenticated`  
**关联需求**：FR-7.1、US-08 AC-08-1/AC-08-4

**请求**：无请求体，通过 Cookie/JWT 鉴权

**成功响应 200 OK**：

```json
{
  "is_configured": true,
  "last_validated_at": "2026-05-14T10:00:00Z"
}
```

或（未配置时）：

```json
{
  "is_configured": false,
  "last_validated_at": null
}
```

**安全自检**：响应体字段穷举如上，不包含 `api_key`、Key 前缀、Key 哈希或任何敏感信息。

**错误响应**：

| 场景 | HTTP 状态码 | 响应体 |
|------|-----------|--------|
| 未登录 | 401 | `{"detail": "Authentication credentials were not provided."}` |

---

### 3.2 `POST /api/v1/users/me/services/{service_type}/test-and-save/`（新增，ADR-10）

**权限**：`IsAuthenticated`  
**关联需求**：FR-6.1、FR-6.3、US-08 AC-08-3/AC-08-4、OQ-8=A

**请求体**（`application/json`）：

```json
{
  "api_key": "<用户输入的 Ark API Key>"
}
```

**成功响应 200 OK**（测试通过，Key 已原子保存）：

```json
{
  "saved": true,
  "last_validated_at": "2026-05-14T10:00:00Z"
}
```

**失败响应 400 Bad Request**（测试失败，Key 未写入数据库）：

```json
{"error": "ARK_KEY_INVALID", "detail": "Key 无效或已吊销，请检查 Ark 控制台"}
```

或：

```json
{"error": "ARK_QUOTA_EXCEEDED", "detail": "账号欠费或权限受限，请检查账户余额"}
```

或：

```json
{"error": "ARK_UNREACHABLE", "detail": "Ark 服务暂时不可达，请稍后重试"}
```

**错误响应**：

| 场景 | HTTP 状态码 | 响应体 |
|------|-----------|--------|
| 未登录 | 401 | `{"detail": "Authentication credentials were not provided."}` |
| api_key 为空 | 400 | `{"api_key": ["该字段不能为空。"]}` |
| service_type 不支持 | 400 | `{"error": "UNSUPPORTED_SERVICE_TYPE", "detail": "..."}` |

**安全自检**：响应体中 `api_key` 字段为 `write_only=True`（`TestAndSaveSerializer`），不出现在任何响应中。成功响应仅含 `saved` 和 `last_validated_at`。

---

## 四、前端新增/修改组件详情

### 4.1 新增文件

#### `src/components/Settings/DoubaoImageKeyPanel.vue`（新增，FR-6.1/6.2）

**关联需求**：FR-6.1（Key 输入 + 测试连接按钮）、FR-6.2（引导文案）  
**关联 ADR**：ADR-10（调用 test-and-save 端点）

**组件职责**：
- 包含带掩码切换的 API Key 输入框（`el-input`，`type="password"`，支持显示/隐藏）
- 包含"测试连接"按钮（调用 `POST .../test-and-save/`，OQ-8=A：测试即保存）
- **不包含**独立"保存"按钮（OQ-8=A 决策）
- 包含引导文案（FR-6.2）："豆包图片生成使用独立 Key，以便单独管理配额和账单。若您已在"大语言模型 — 火山引擎"中配置了 Ark Key，可在此处填写相同的值。"
- 测试连接成功后：显示"连接成功，Key 已自动保存"；组件 emit `configured` 事件通知父级

**Props 接口**：

```typescript
interface DoubaoImageKeyPanelProps {
  initialConfigured: boolean  // 初始是否已配置（来自 ServiceStatusView）
}
```

**Emits**：

```typescript
interface DoubaoImageKeyPanelEmits {
  configured: []  // 测试成功且 Key 已保存后触发
}
```

---

#### `src/components/ImageGenerator/PreflightBanner.vue`（新增，FR-7.1）

**关联需求**：FR-7.1、US-08 AC-08-1/AC-08-2  
**关联 ADR**：ADR-09（`is_configured` 来自 `ServiceStatusView`）

**组件职责**：
- 展示"您尚未配置豆包图片生成 API Key，功能暂不可用"警告 Banner（`el-alert`，`type="warning"`）
- **无关闭按钮**（OQ-7=A：Banner 常驻，通过 `v-if` 控制显隐，不渲染 `el-alert` 的 `closable` prop）
- 含"前往配置"按钮，点击后路由跳转 `/settings?tab=doubao_image`
- `v-if` 绑定父组件传入的 `visible` prop（由 `ImageGeneratorView` 根据 `is_configured` 控制）

**Props 接口**：

```typescript
interface PreflightBannerProps {
  visible: boolean  // true = 展示 Banner（is_configured=false 时）
}
```

**关键实现约束**：
- `el-alert` 组件的 `:closable="false"` 属性必须显式设置，防止默认关闭按钮出现
- Banner 不调用任何 API，仅为纯展示组件（状态由父组件 `ImageGeneratorView` 管理）

---

### 4.2 修改文件

#### `src/views/SettingsView.vue`（修改，新增"豆包图片生成"Tab）

**变更内容**：
- 在现有 Tab 列表（大语言模型、即梦 API、存储设置）之后新增"豆包图片生成"Tab
- Tab 内容区域渲染 `DoubaoImageKeyPanel.vue` 组件
- URL query 参数支持 `?tab=doubao_image` 自动激活该 Tab（供 `PreflightBanner.vue` 的"前往配置"跳转使用）

---

#### `src/views/ImageGeneratorView.vue`（修改，新增预检逻辑）

**变更内容**：
- `onMounted` 钩子中调用 `GET /api/v1/users/me/services/doubao_image/status/`
- 将响应中的 `is_configured` 绑定到响应式变量 `doubaoIsConfigured`
- 在模板顶部渲染 `<PreflightBanner :visible="!doubaoIsConfigured" />`（FR-7.1）
- 当从设置页返回时（`onActivated` 或路由 `beforeRouteEnter`），重新调用 `status/` 接口刷新状态，确保 Banner 在配置完成后消失（US-08 AC-08-4）

---

#### `src/api/index.js`（修改，新增两个 API 函数）

```javascript
/**
 * 查询服务配置状态（仅返回 is_configured，不含 Key 内容）
 * 关联需求：FR-7.1、ADR-09
 *
 * @param {string} serviceType - 服务类型，如 "doubao_image"
 * @returns {Promise<{is_configured: boolean, last_validated_at: string|null}>}
 */
export function getServiceStatus(serviceType) {
  return apiClient.get(`/api/v1/users/me/services/${serviceType}/status/`)
}

/**
 * 测试并保存 API Key（原子操作，测试通过即自动保存，OQ-8=A）
 * 关联需求：FR-6.3、ADR-10
 *
 * @param {string} serviceType - 服务类型，如 "doubao_image"
 * @param {string} apiKey - 用户输入的 API Key
 * @returns {Promise<{saved: boolean, last_validated_at: string}>}
 * @throws {AxiosError} 400 - {error: "ARK_KEY_INVALID"|"ARK_QUOTA_EXCEEDED"|"ARK_UNREACHABLE", detail: string}
 */
export function testAndSaveServiceKey(serviceType, apiKey) {
  return apiClient.post(`/api/v1/users/me/services/${serviceType}/test-and-save/`, {
    api_key: apiKey,
  })
}
```

---

## 五、依赖变更

> v1.0 已决策：`httpx` 已在 `requirements.txt`，本补丁不引入任何新的 Python 依赖。

| 依赖 | 状态 | 说明 |
|------|------|------|
| `httpx` | 已存在（requirements.txt） | `ark_validator.py` 使用 `httpx.get()` |
| `django.db.transaction` | Django 内置 | `TestAndSaveView` 使用 `transaction.atomic()` |
| Vue Router | 已存在 | `PreflightBanner.vue` 跳转 `/settings?tab=doubao_image` |

因此 **tech_stack_v1.1.md 无需创建**（v1.0 已完整覆盖，本补丁无新增依赖）。

---

## 六、补丁文档引用关系

```
ARCH-MOD-IMG-001 v1.0（基准，已决稿）
  └── ARCH-MOD-IMG-001-PATCH v1.1（本文档，增量补丁）
        ├── 新增后端模块：ark_validator.py、ServiceStatusView、TestAndSaveView
        ├── 新增后端序列化器：ServiceStatusSerializer、TestAndSaveSerializer
        ├── 修改后端：urls.py（两条路由）、models.py（分支 + 字段）
        ├── 新增前端组件：DoubaoImageKeyPanel.vue、PreflightBanner.vue
        └── 修改前端：SettingsView.vue、ImageGeneratorView.vue、api/index.js
```

---

*文档版本 v1.1，状态 DRAFT，等待 PM 门控评审。*  
*若 PM 门控 PASS，此文档状态升级为 APPROVED，可进入 GROUP_C 开发阶段。*
