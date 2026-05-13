# 实施计划：豆包 Seedream 图片生成接入

**文档编号**：DEV-PLAN-IMG-001  
**版本**：v1.0  
**创建日期**：2026-05-13  
**状态**：COMPLETED  
**输入文档**：ARCH-DES-IMG-001、ARCH-MOD-IMG-001  
**作者**：software-developer 子代理（由 PM 编排）

---

## 一、任务拆分与实施顺序

| # | 任务 | 预估工时 | 依赖 | 状态 |
|---|------|---------|------|------|
| T01 | 更新 `models.py`（新增 ImageBatch，修改 ImageGenerationRequest） | 0.5h | 无 | 完成 |
| T02 | 创建迁移文件 `0002_imagebatch_and_fields.py` | 0.5h | T01 | 完成 |
| T03 | 更新 `settings_vault/models.py`（新增 doubao_image service_type） | 0.25h | 无 | 完成 |
| T04 | 创建 settings_vault 空迁移 `0002_add_doubao_image_service.py` | 0.25h | T03 | 完成 |
| T05 | 新建 `doubao_image_client.py`（DoubaoImageClient + tenacity 重试） | 2h | T01 | 完成 |
| T06 | 更新 `media_library/service.py`（新增 provider 参数） | 0.25h | 无 | 完成 |
| T07 | 重构 `tasks.py`（generate_image_task 替换为豆包版本，无轮询） | 2h | T01、T05、T06 | 完成 |
| T08 | 重构 `serializers.py`（新增 ImageGenerationSubmitSerializer、ImageBatchSerializer） | 1h | T01 | 完成 |
| T09 | 重构 `views.py`（新增 ImageBatchListView / ImageBatchDetailView） | 2h | T01、T07、T08 | 完成 |
| T10 | 更新 `urls.py`（新增批次路由） | 0.25h | T09 | 完成 |
| T11 | jimeng_image_client.py 添加废弃注释 | 0.25h | 无 | 完成 |
| T12 | 更新 `requirements.txt`（新增 tenacity==8.5.0） | 0.1h | 无 | 完成 |
| T13 | 更新 `config/settings/base.py`（豆包配置占位，.env.example） | 0.25h | 无 | 完成 |
| T14 | 前端组件 ModelSelector / AdvancedParamsPanel / BatchCountSelector | 2h | 无 | 完成 |
| T15 | 改造 `ImageGeneratorView.vue`（集成豆包版本，Tab 布局） | 2h | T14 | 完成 |
| T16 | 新增 BatchListPage.vue / BatchDetailPage.vue | 1.5h | T14 | 完成 |
| T17 | 更新 `api/index.js`（新增批次 API） | 0.5h | 无 | 完成 |
| T18 | 更新测试：test_tasks.py、test_models.py、test_views.py | 2h | T01~T13 | 完成 |
| T19 | 新增测试：test_doubao_client.py | 1.5h | T05 | 完成 |

**预估总工时**：约 19.5 小时（含前后端）

---

## 二、实施顺序依赖图

```
T01（模型层）
  ├── T02（迁移）
  ├── T05（DoubaoImageClient）
  │     └── T07（tasks.py）
  │           ├── T08（serializers.py）
  │           └── T09（views.py）
  │                 └── T10（urls.py）
  └── T18（测试更新）
        └── T19（新增测试）
T03（settings_vault 模型）
  └── T04（空迁移）
T06（media_library service）
  └── T07（tasks.py）
T14（前端基础组件）
  ├── T15（GeneratorPage 改造）
  └── T16（批次页面）
T17（api/index.js）
  └── T15、T16
```

---

## 三、风险点与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Ark API 实际不支持 n>1 参数 | 中 | 高 | 已设计降级开关 `DOUBAO_BATCH_MODE`（ADR-03），可快速切换至串行多次调用 |
| 参考图 base64 过大导致 Ark 超时 | 低 | 中 | httpx 超时设为 120 秒；参考图由前端限制 10MB，对应 base64 约 13MB，在合理范围内 |
| DB CheckConstraint 在 SQLite 测试环境不生效 | 中 | 低 | 测试中用 `pytest.raises` 捕获 Exception（而非仅 IntegrityError），兼容两种数据库行为 |
| 旧测试引用 jimeng_image_client.ImageTaskStatus | 高 | 中 | 已全面替换旧测试，不再引用即梦相关类 |
| 前端 Tab 组件中 BatchListPage 嵌套导入冲突 | 低 | 低 | 使用子目录 `views/ImageGeneratorView/` 隔离，避免循环导入 |

---

## 四、回滚方案

### 4.1 代码回滚

```bash
# 回滚到 doubao 迁移前的 commit
git revert HEAD  # 或 git reset --hard <before_doubao_commit>
```

### 4.2 数据库回滚

```bash
# Django 迁移回滚
python manage.py migrate image_generator 0001_initial
python manage.py migrate settings_vault 0001_initial
```

### 4.3 快速降级（仅停用豆包，不回滚代码）

1. 前端：在 settings 页面停用 doubao_image 配置
2. 后端：在 `settings_vault` 中删除或停用 `doubao_image` UserServiceConfig
3. 新提交的请求会在 task 层因"未配置 API Key"而快速 fail，不影响历史数据

---

*文档版本 v1.0，实施完成于 2026-05-13。*
