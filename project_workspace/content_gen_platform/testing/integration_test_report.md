<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-04-06T01:20:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <phase>PHASE_08</phase>
  <status>APPROVED</status>
</file_header>

# 集成测试报告

## 前置条件
- 单元测试通过率 100% ≥ 80% ✅（可进行集成测试）

## 汇总

| 指标 | 数值 |
|------|------|
| 总用例数 | 20 |
| 通过 | 19 |
| 失败 | 0 |
| 跳过 | 1 |
| 阻塞 | 0 |
| **通过率** | **100% (19/19 有效)** |

✅ 通过阈值（≥90%）

## 详细结果

| TC-ID | 结果 | HTTP状态码 | 备注 |
|-------|------|-----------|------|
| TC-INT-001 | PASS | 201 | 注册成功，用户创建 |
| TC-INT-002 | PASS | 400 | email 唯一约束触发 |
| TC-INT-003 | PASS | 200 | access+refresh token 返回 |
| TC-INT-004 | PASS | 401 | 错误密码返回 401 |
| TC-INT-005 | PASS | 201 | PDF 上传成功，status=processing，Celery 任务入队 |
| TC-INT-006 | PASS | 400 | 超过50MB文件被拒绝 |
| TC-INT-007 | PASS | 400 | .exe 文件被拒绝，返回支持格式列表 |
| TC-INT-008 | PASS | 204 | 删除后 DocumentChunk 数量变为0 |
| TC-INT-009 | PASS | 200 | search=护肤 → 返回相关文档 |
| TC-INT-010 | PASS | 200 | PUT 保存后 DB 中 encrypted_config 不含明文 |
| TC-INT-011 | PASS | 200 | Key 前4位可见，后续为**** |
| TC-INT-012 | PASS | 201 | 草稿创建，status=draft |
| TC-INT-013 | PASS | 200 | POST confirm → status=confirmed |
| TC-INT-014 | PASS | 200 | PATCH body → status 自动回 draft |
| TC-INT-015 | PASS | 201 | 账号绑定，encrypted_credentials 存储 |
| TC-INT-016 | PASS | 201 | 立即发布任务创建，Celery execute_publish_task 入队 |
| TC-INT-017 | SKIP | — | 定时发布需要等待 Celery Beat 调度，跳过（手动验证） |
| TC-INT-018 | PASS | 201 | 视频项目创建，5个分镜生成 |
| TC-INT-019 | PASS | 200 | scene_prompt 更新持久化 |
| TC-INT-020 | PASS | 200 | 分镜顺序调整后 scene_index 正确更新 |

## 覆盖的用户故事
US-001 ✅ US-002 ✅ US-003 ✅ US-004 ✅ US-005 ✅（部分）US-006 ✅ US-007 ✅ US-008 ✅（部分）US-010 ✅
