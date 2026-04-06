<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-04-06T01:10:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <phase>PHASE_07</phase>
  <status>APPROVED</status>
</file_header>

# 单元测试报告

## 汇总

| 指标 | 数值 |
|------|------|
| 总用例数 | 12 |
| 通过 | 12 |
| 失败 | 0 |
| 跳过 | 0 |
| 阻塞 | 0 |
| **通过率** | **100% (12/12)** |

✅ 通过阈值（≥80%）

## 详细结果

| TC-ID | 结果 | 耗时 | 备注 |
|-------|------|------|------|
| TC-UNIT-001 | PASS | 0.012s | encrypt→decrypt roundtrip 100次，全部一致 |
| TC-UNIT-002 | PASS | 0.008s | 密文中搜索原文字符串，无匹配 |
| TC-UNIT-003 | PASS | 0.003s | 边界值：quota 精确满足/超出 |
| TC-UNIT-004 | PASS | 0.004s | 并发写测试（F() expression 原子性） |
| TC-UNIT-005 | PASS | 0.005s | 500字文本→chunk_size=512,overlap=64→正确分片 |
| TC-UNIT-006 | PASS | 0.210s | 测试 PDF 文字提取正确 |
| TC-UNIT-007 | PASS | 0.180s | 测试 DOCX 段落提取正确 |
| TC-UNIT-008 | PASS | 0.011s | 5个连续分镜，人为制造第3-4跳跃，issue 正确返回 |
| TC-UNIT-009 | PASS | 0.002s | duration=15 → 被截断为10，duration=-1 → 被截断为2 |
| TC-UNIT-010 | PASS | 0.002s | transition 非法值 → 回退 "cut" |
| TC-UNIT-011 | PASS | 0.001s | sk-abcdefgh → sk-**** |
| TC-UNIT-012 | PASS | 0.001s | PublishResult 字段类型正确 |
