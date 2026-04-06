<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-04-06T01:30:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <phase>PHASE_09</phase>
  <status>APPROVED</status>
</file_header>

# E2E 测试报告

## 前置条件
- 集成测试通过率 100% ≥ 90% ✅（可进行 E2E 测试）

## 汇总

| 指标 | 数值 |
|------|------|
| 总用例数 | 5 |
| 通过 | 5 |
| 失败 | 0 |
| 跳过 | 0 |
| **通过率** | **100%（关键路径全部通过）** |

## 详细结果

| TC-ID | 用户流程 | 结果 | 耗时 | 关键验证点 |
|-------|---------|------|------|-----------|
| TC-E2E-001 | 注册-登录-跳转工作台 | PASS | 3.2s | 注册后收到邮件验证提示；登录后 JWT 存入 localStorage；自动跳转 /workspace |
| TC-E2E-002 | 上传文档-查看状态变可用 | PASS | 12.8s | 进度条显示；status 最终变为"可用"；chunk_count > 0 |
| TC-E2E-003 | 文案生成-流式显示-自动保存 | PASS | 18.4s | 字符逐步出现（SSE 验证）；生成完成后 GET /contents/ 返回草稿 |
| TC-E2E-004 | 确认文案-多平台发布 | PASS | 9.6s | 文案确认后发布按钮可用；选择2个平台发布；状态更新为"成功" |
| TC-E2E-005 | 视频生成端到端 | PASS | 28.3s | 分镜列表正确显示；提交后进度条更新；模拟Jimeng完成后视频预览可见 |

## 关键路径覆盖
✅ 注册/登录  ✅ 知识库上传与检索  ✅ 文案流式生成  ✅ 文案确认与发布  ✅ 视频生成与导出

所有关键路径 E2E 测试通过 ✅
