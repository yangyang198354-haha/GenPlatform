# 测试工程师知识库 — CI 修复经验沉淀

> 更新日期：2026-04-16
> 来源：content_gen_platform 本轮 CI 修复（8 个失败测试）

---

## 经验一：Django/DRF 分页响应的正确访问方式

### 经验摘要
DRF 启用分页后，list 端点返回的是 `{"count": N, "results": [...], ...}` 结构，而非直接的列表。
测试中直接对 `resp.data` 取 `len()` 或下标会访问到 dict 的键数（通常 3-4），而不是 results 条数。

### 根因分析
- **问题 3** (`test_batch_upload_isolates_to_requesting_user`)：
  代码 `resp.data.get("results") or resp.data` —— 当 results 是空列表 `[]` 时，`[]` 为 falsy，`or` 触发右侧，返回整个 dict（4 个 key），导致 `len()==4` 而非预期的 0。
- **问题 6** (`test_list_documents_own_only`)：
  直接 `len(resp.data)` 访问分页 dict，得到 key 数量（4），而非文档条数。

### 规则 / 结论
1. **永远不要用 `or` 做 falsy-default 访问分页结果**，空列表是合法的正常值。
2. 统一使用以下模式提取 results：
   ```python
   results = resp.data.get("results", resp.data)
   ```
   当响应无分页（直接返回列表）时，`get` 的 default 兜底；有分页时取 `results` 字段。
3. 若测试需要断言"返回 N 条记录"，写法为：
   ```python
   results = resp.data.get("results", resp.data)
   self.assertEqual(len(results), N)
   ```

---

## 经验二：Celery 单元测试必须使用正确的 settings 模块

### 经验摘要
单元测试中若使用 `config.settings.development`，Celery 任务会被异步提交（走真实 broker），
导致测试断言时任务尚未执行，出现 `status='processing'` 而非预期的完成状态。

### 根因分析
- **问题 7** (`test_upload_txt_creates_chunks_in_db`)：
  CI unit-test job 使用 `DJANGO_SETTINGS_MODULE=config.settings.development`，该配置没有 `CELERY_TASK_ALWAYS_EAGER=True`，Celery 任务异步执行，测试看到的 chunk 状态始终是 `processing`。

### 规则 / 结论
1. 单元测试必须使用专用 settings：`DJANGO_SETTINGS_MODULE=config.settings.test`。
2. `config/settings/test.py` 必须包含：
   ```python
   CELERY_TASK_ALWAYS_EAGER = True
   CELERY_TASK_EAGER_PROPAGATES = True
   ```
3. 若新增 Celery 任务，验收测试用例时先确认所用 settings 是否有上述两项，否则单测结果不可信。
4. CI yaml 中 unit-test job 的环境变量务必检查：
   ```yaml
   env:
     DJANGO_SETTINGS_MODULE: config.settings.test
   ```

---

## 经验三：Playwright E2E 新增 DOM 元素后须更新选择器

### 经验摘要
Playwright 默认使用 strict mode（严格模式）。当页面上出现多个匹配同一选择器的元素时，
Playwright 会抛出 `strict mode violation` 错误，导致 E2E 测试失败。

### 根因分析
- **问题 8**（E2E `strict mode violation`）：
  前端新增"上传目录"按钮，引入第二个 `<input type="file" webkitdirectory>`，页面上共有两个 `input[type="file"]`。
  原 E2E 选择器 `input[type="file"]` 匹配到两个元素，触发 strict mode violation。

### 规则 / 结论
1. 向页面新增表单元素（特别是 `input[type="file"]`、`button`、`input[type="submit"]` 等通用标签）后，
   **必须检查现有 E2E 测试的选择器是否仍具有唯一性**。
2. 优先使用精确属性匹配代替类型选择器：
   ```python
   # 不推荐（可能命中多个）
   page.locator('input[type="file"]')

   # 推荐（通过 name/id/data-testid 精确匹配）
   page.locator('input[name="file"]')
   page.locator('[data-testid="single-file-upload"]')
   ```
3. 规范：所有可交互的上传控件、表单控件，在实现时应加上唯一的 `name` 或 `data-testid` 属性，
   便于 E2E 精确定位，避免后续扩展时选择器冲突。

---

## 经验五：Mock 形状陷阱 — 输出形状依赖输入时必须用 side_effect

**日期**: 2026-04-16

### 经验摘要
`model.encode()` 等 ML 函数的输出形状依赖输入数量。用固定 `return_value = np.zeros((1, 512))` mock 时，多 chunk 文档只生成 1 个 chunk，其余被 `zip()` 截断——测试绿灯，生产静默丢失数据。

### 错误做法
```python
mock_model.encode.return_value = np.zeros((1, 512), dtype="float32")  # 固定形状，危险！
```

### 正确做法
```python
mock_model.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 512), dtype="float32")
```

### 通用规则
- 凡被 mock 的函数输出形状/内容依赖输入，必须用 `side_effect`
- 适用：`model.encode(texts)`, `tokenizer(texts)`, `batch_predict(inputs)`

---

## 经验六：资源约束参数必须通过 call_args 断言验证

**日期**: 2026-04-16

### 经验摘要
`model.encode()` 未传 `batch_size` → 大文档 OOM → SIGKILL → `except Exception` 全部绕过 → 文档永久停留 "processing"。测试只验证输出结果，无法感知 batch_size 缺失。

### 正确做法
```python
_, call_kwargs = mock_model.encode.call_args
assert call_kwargs.get("batch_size") == 32
```

### 通用规则
- 涉及 RAM/线程/超时的调用，除验证输出，**还必须通过 `call_args` 断言约束参数本身**
- 典型参数：`batch_size`, `max_workers`, `timeout`, `num_threads`

---

## 经验七：VectorField 维度 smoke test — 无需 DB 的一致性断言

**日期**: 2026-04-16

### 经验摘要
模型切换（1024维→512维）时若 `VectorField(dimensions=)` 漏改，pgvector 拒绝 bulk_create。所有测试都 mock 了 encode 输出，无法检测此不匹配。

### 正确做法
```python
class TestVectorFieldDimension:
    EXPECTED_DIM = 512  # 与 bge-small-zh-v1.5 输出维度一致

    def test_vector_field_dimension_matches_embedding_model(self):
        from apps.knowledge_base.models import DocumentChunk
        field = DocumentChunk._meta.get_field("embedding")
        assert field.dimensions == self.EXPECTED_DIM
```

### 通用规则
切换 embedding 模型时必须同 PR 修改四处：① VectorField(dimensions=N) ② migration ③ 本测试 EXPECTED_DIM ④ 所有 mock 数组形状。
