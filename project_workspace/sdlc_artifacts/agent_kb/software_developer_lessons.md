# 软件开发工程师知识库 — CI 修复经验沉淀

> 更新日期：2026-04-16
> 来源：content_gen_platform 本轮 CI 修复（8 个失败测试）

---

## 经验一：`or` 用于 falsy-default 的隐患

### 经验摘要
Python 的 `a or b` 在 `a` 为任何 falsy 值（空列表、空字符串、0、None）时都会取 `b`。
用它作"字典默认值"兜底会在 value 是空列表时静默出错，应统一使用 `dict.get(key, default)`。

### 根因分析
- **问题 3** (`test_batch_upload_isolates_to_requesting_user`)：
  ```python
  # 错误写法
  results = resp.data.get("results") or resp.data
  ```
  当 `results` 为 `[]` 时，`[]` falsy，`or` 触发右侧，返回整个 dict（含 count/next/previous/results 共 4 key），
  导致调用方得到 dict 而非预期的空列表。

### 规则 / 结论
1. 凡是"key 存在但 value 可能为空集合"的场景，必须用：
   ```python
   value = d.get(key, default)   # 正确：仅 key 不存在时才取 default
   ```
   而不是：
   ```python
   value = d.get(key) or default  # 错误：key 存在且 value=[] 时也取 default
   ```
2. 类似易错模式：
   ```python
   # 同样危险
   value = d[key] if key in d else default   # 等价于 dict.get，但更冗长
   value = d.get(key) or default             # 有 falsy 陷阱，避免使用
   ```

---

## 经验二：batch 上传端点"无文件被接受"时必须返回 400

### 经验摘要
batch 上传接口需要区分以下结果：全部接受、部分接受、全部跳过（重复）、无支持格式。
当没有任何文件被实际写入/处理时（无论是因为格式不支持还是全部重复），应返回 400。

### 根因分析
- **问题 2** (`test_batch_upload_no_supported_files_returns_400`)：
  ```python
  # 原始错误条件：三个条件都为 True 才报错
  if not accepted and not skipped and not rejected:
      return Response(..., status=400)
  ```
  当所有文件都被"跳过"（重复文件）时，`skipped` 非空，条件为 False，返回了 201。

### 规则 / 结论
1. batch 端点的 400 判断应以"是否有文件被实际接受处理"为唯一依据：
   ```python
   if not accepted:
       return Response(
           {"detail": "No files were accepted."},
           status=status.HTTP_400_BAD_REQUEST,
       )
   ```
2. 设计 batch 端点响应逻辑时，先问："调用方能从这次请求中得到任何处理结果吗？"
   若答案是否定的，一律返回 4xx，不要返回 2xx 空结果，避免调用方误判成功。
3. 单测时必须覆盖"全部跳过"场景，而不只是"全部被拒绝"场景，二者行为需明确区分。

---

## 经验三：anchor injection 的 cap 逻辑 — natural top_k vs over-fetch

### 经验摘要
知识库搜索中，anchor chunk 注入逻辑需要区分两种情形：
- anchor 已自然落在 top_k 结果内 → 不需要额外占名额
- anchor 不在 top_k 内 → 作为 extra 注入，总数可超出 top_k

错误地将 anchor 始终视为 extra 注入，会导致结果超出 top_k（问题 5）；
错误地将 anchor 的去重放在 cap 截断之前，会导致 anchor 被截断丢失（问题 4）。

### 根因分析
- **问题 4** (`test_anchor_chunk_always_included`)：
  over-fetch `top_k * 2` 语义结果时，anchor 进入候选集，随后被 `exclude(pk__in=seen_pks)` 去重排除，
  最终 cap=top_k 截断时 anchor 已不在列表中，导致 anchor 丢失。
- **问题 5** (`test_search_respects_top_k`)：
  修复问题 4 时引入了 `semantic_anchor_count` 扩大 cap，但 anchor 自然在 top_k 内时不应额外占名额，
  导致结果数量超出 top_k。

### 规则 / 结论
1. 正确的 anchor injection merge 逻辑（伪代码）：
   ```python
   natural_top_k_pks = set(semantic_results[:top_k].values_list("pk", flat=True))

   if anchor.pk in natural_top_k_pks:
       # anchor 已自然落在结果内，无需额外处理
       extra_anchor_chunks = []
   else:
       # anchor 不在 natural top_k，作为 extra 注入
       extra_anchor_chunks = [anchor_chunk]

   # 最终结果 = natural top_k + extra anchor（若有）+ keyword 补充
   final_results = natural[:top_k] + extra_anchor_chunks + keyword_chunks
   ```
2. 关键原则：
   - **先确定 natural top_k**，再判断 anchor 是否已在其中。
   - **extra anchor 不占 top_k 名额**，允许结果比 top_k 多 1 条（仅此一例外）。
   - **不要用扩大 cap 的方式解决 anchor 丢失**，会破坏 top_k 约束。
3. 测试该逻辑必须同时覆盖两个场景：
   - anchor 自然在 top_k 内（结果数 == top_k，不多不少）
   - anchor 不在 top_k 内（结果数 == top_k + 1）

---

## 经验五：Celery 任务处理文件/ML 推理必须设 soft_time_limit + batch_size

**日期**: 2026-04-16

### 经验摘要
大型 DOCX 上传后 `process_document_task` 一次性编码所有 chunk → OOM → SIGKILL → Python 所有 except 被绕过 → 文档永久停留 "processing"。

### 双重防护

```python
# services.py — 分批编码，峰值内存可控
embeddings = model.encode(chunks, batch_size=32, show_progress_bar=False, normalize_embeddings=True)

# tasks.py — soft_time_limit 发 Python 可捕获的异常，而非 SIGKILL
from celery.exceptions import SoftTimeLimitExceeded

@shared_task(bind=True, max_retries=0, soft_time_limit=300)
def process_document_task(self, document_id):
    try:
        _process_document(document_id)
    except SoftTimeLimitExceeded:
        Document.objects.filter(pk=document_id).update(
            status="error", error_message="处理超时，请重试"
        )
    except Exception as exc:
        Document.objects.filter(pk=document_id).update(
            status="error", error_message=f"Task error: {exc}"
        )
```

### 通用规则
- `except Exception` 挡不住 SIGKILL，只有 `soft_time_limit` 才能提供 graceful timeout
- 处理文件/ML 的 task：① `batch_size` ② `soft_time_limit` ③ `SoftTimeLimitExceeded` 测试 — 三者缺一不可
