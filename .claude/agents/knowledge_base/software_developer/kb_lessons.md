# Knowledge Base — software_developer
<!-- 记录开发过程中积累的代码实现经验教训 -->

---

## SD-L001: DRF 注册接口 — 必须包含 password2 确认字段

**日期**: 2026-04-10  
**文件**: `apps/accounts/serializers.py`

本项目 `RegisterSerializer` 继承 `ModelSerializer`，明确要求 `password2` 字段。
任何调用注册 API 的代码（前端、测试、脚本）都必须传递。

```python
# serializers.py 摘要
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)  # 必须！

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "两次密码不一致"})
        return attrs
```

---

## SD-L002: 发布任务 API — 返回列表而非单对象

**日期**: 2026-04-10  
**文件**: `apps/publisher/views.py`

`POST /api/v1/publisher/tasks/` 接受 `platform_account_ids`（列表），
可一次对多个平台账号发布，响应是任务列表 `[{id, status, ...}]`。

```python
# 正确调用方式
{
    "content_id": 123,
    "platform_account_ids": [1, 2],  # 复数列表
}
# 响应: [{"id": 10, "status": "pending"}, {"id": 11, "status": "pending"}]
```

---

## SD-L003: 前端 API URL 路径 — knowledge 不是 knowledge-base

**日期**: 2026-04-10  
**问题**: 前端 `kbAPI` 使用 `/knowledge-base/documents/` 导致 404

**根因**: 后端 `config/urls.py` 注册路径是 `path("knowledge/", ...)`，
但前端 API 配置里用了 `/knowledge-base/`。

**已修复** `src/frontend/src/api/index.js`:
```js
export const kbAPI = {
  list: (params) => api.get("/knowledge/documents/", { params }),
  // 正确路径是 /knowledge/ 不是 /knowledge-base/
};
```

**教训**: 修改路由时前后端必须同步检查。

---

## SD-L004: JWT 过期 — 前端主动刷新策略

**日期**: 2026-04-10  
**文件**: `src/frontend/src/App.vue`

`App.vue` onMounted 中主动检查 token 剩余时间，不足 5 分钟则刷新，
避免进入页面后立即出现 401：

```js
onMounted(async () => {
  if (!authStore.accessToken) return;
  try {
    const payload = JSON.parse(atob(authStore.accessToken.split('.')[1]));
    const expiresSoon = Date.now() / 1000 >= payload.exp - 300;
    if (expiresSoon) {
      await authStore.refreshToken();
    }
  } catch {
    // 格式错误的 token — 让拦截器处理 401
  }
  if (!authStore.user) {
    await authStore.fetchProfile();
  }
});
```

---

## SD-L005: SSE 流 — backend 必须捕获异常并发送 done:true

**日期**: 2026-04-10  
**文件**: `apps/llm_gateway/views.py`

SSE stream 如果抛出异常但没有发送 `done:true`，前端 `generating.value` 永远不会置 false，
用户看到无限 "生成中..."。

**修复要点**:
1. `_run()` 内用 `try/except` 捕获异常，发送 `{"done": true, "error": str(exc)}`
2. 外层 while 循环也要 `except Exception` 兜底

**前端同步修复**:  
while 循环结束后检查 `generating.value` 是否仍为 true，是则强制置 false。

---

## SD-L006: ElementPlus 3.x — el-radio 使用 value 不是 label

**日期**: 2026-04-10  
**文件**: `src/frontend/src/views/SettingsView.vue`

ElementPlus 3.x 中 `el-radio` 的 `label` prop 已废弃，应使用 `value`。

```html
<!-- 错误（产生废弃警告）-->
<el-radio label="deepseek">DeepSeek</el-radio>

<!-- 正确 -->
<el-radio value="deepseek">DeepSeek</el-radio>
```

---

## SD-L008: SettingsView 表单验证 — 空字段用 warning 不用 error

**日期**: 2026-04-10  
**文件**: `src/frontend/src/views/SettingsView.vue`

前端验证空必填字段时使用 `ElMessage.warning()`，不是 `ElMessage.error()`：

```js
if (!llmForm.value.api_key) {
  ElMessage.warning("请填写 API Key");  // warning！
  return;
}
```

产生的 DOM class 是 `.el-message--warning`。
任何需要检查此提示的测试/E2E 必须用 `warning` class，不是 `error`。

---

## SD-L007: 测试隔离 — UserRateThrottle 在共享 locmem 缓存中累积

**日期**: 2026-04-10  
**文件**: `config/settings/test.py`, `config/settings/local_test.py`

`UserRateThrottle`（100次/小时）在 locmem 缓存中跨测试累积，当单次测试 session
请求超过阈值时出现 429 错误。

**修复**: 在测试 settings 中禁用 throttle：
```python
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
```
