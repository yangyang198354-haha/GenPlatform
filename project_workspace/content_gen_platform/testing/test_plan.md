<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-04-06T01:00:00Z</timestamp>
  <project_name>content_gen_platform</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/user_stories.md (APPROVED)</file>
    <file>development/implementation_plan.md (APPROVED)</file>
  </input_files>
  <phase>PHASE_07</phase>
  <status>APPROVED</status>
</file_header>

# 测试计划 — 内容生成平台

## 测试策略

| 测试级别 | 工具 | 覆盖目标 | 通过阈值 |
|---------|------|---------|---------|
| 单元测试 | pytest + pytest-django | 模型、服务、工具函数 | ≥ 80% |
| 集成测试 | pytest + DRF APIClient | API 端到端（含真实 DB） | ≥ 90% |
| E2E 测试 | Playwright | 核心用户流程（浏览器） | 关键路径 100% |

## 测试用例分配

### 单元测试（TC-UNIT）
| TC-ID | 模块 | 测试内容 | 关联 AC |
|-------|------|---------|--------|
| TC-UNIT-001 | core.encryption | encrypt/decrypt 正确性 | REQ-NFUNC-002 |
| TC-UNIT-002 | core.encryption | 密文不含明文 | REQ-NFUNC-002 |
| TC-UNIT-003 | accounts.User | has_storage_quota 边界值 | AC-002-04 |
| TC-UNIT-004 | accounts.User | consume/release_storage 原子性 | REQ-FUNC-002 |
| TC-UNIT-005 | knowledge_base.services | _chunk_text 分块大小正确 | REQ-FUNC-003 |
| TC-UNIT-006 | knowledge_base.services | _extract_text PDF | AC-002-01 |
| TC-UNIT-007 | knowledge_base.services | _extract_text DOCX | AC-002-01 |
| TC-UNIT-008 | knowledge_base.services | validate_scene_continuity issues | REQ-FUNC-017 |
| TC-UNIT-009 | video_generator.scene_generator | _validate_and_normalize_scenes | REQ-FUNC-015 |
| TC-UNIT-010 | video_generator.scene_generator | duration_sec clamped 2-10 | REQ-FUNC-015 |
| TC-UNIT-011 | settings_vault.views | _mask_value 掩码正确 | REQ-NFUNC-002 |
| TC-UNIT-012 | publisher.publishers | PublishResult dataclass | REQ-FUNC-011 |

### 集成测试（TC-INT）
| TC-ID | 端点 | 场景 | 关联 AC |
|-------|------|------|--------|
| TC-INT-001 | POST /auth/register/ | 正常注册 | AC-001-01 |
| TC-INT-002 | POST /auth/register/ | 重复邮箱 400 | AC-001-01 |
| TC-INT-003 | POST /auth/login/ | 正确密码返回 JWT | AC-001-02 |
| TC-INT-004 | POST /auth/login/ | 错误密码 401 | AC-001-03 |
| TC-INT-005 | POST /knowledge/documents/ | 上传 PDF 成功 | AC-002-01 |
| TC-INT-006 | POST /knowledge/documents/ | 超大文件 400 | AC-002-04 |
| TC-INT-007 | POST /knowledge/documents/ | 非法格式 400 | AC-002-03 |
| TC-INT-008 | DELETE /knowledge/documents/{id}/ | 删除后向量清除 | AC-003-02 |
| TC-INT-009 | GET /knowledge/documents/ | 搜索过滤 | AC-003-01 |
| TC-INT-010 | PUT /settings/services/llm_deepseek/ | 保存配置加密 | AC-004-01 |
| TC-INT-011 | GET /settings/services/ | 返回掩码 Key | AC-004-01 |
| TC-INT-012 | POST /contents/ | 创建草稿 | AC-005-04 |
| TC-INT-013 | POST /contents/{id}/confirm/ | 状态变确认 | AC-006-02 |
| TC-INT-014 | PATCH /contents/{id}/ | 修改已确认回草稿 | AC-006-03 |
| TC-INT-015 | POST /publisher/accounts/weibo/bind/ | 绑定账号 | AC-007-01 |
| TC-INT-016 | POST /publisher/tasks/ | 立即发布任务创建 | AC-008-01 |
| TC-INT-017 | POST /publisher/tasks/ | 定时发布任务 | AC-008-04 |
| TC-INT-018 | POST /video/projects/ | 从文案创建项目+分镜 | AC-010-01 |
| TC-INT-019 | PATCH /video/projects/{id}/scenes/{sid}/ | 编辑分镜 | AC-010-03 |
| TC-INT-020 | POST /video/projects/{id}/reorder/ | 重排分镜顺序 | AC-012-02 |

### E2E 测试（TC-E2E）
| TC-ID | 用户流程 | 步骤摘要 | 关联 US |
|-------|---------|---------|--------|
| TC-E2E-001 | 注册-登录-跳转工作台 | 注册→登录→验证重定向 | US-001 |
| TC-E2E-002 | 上传文档-查看状态变可用 | 上传PDF→等待→状态变可用 | US-002 |
| TC-E2E-003 | 文案生成-流式显示-自动保存 | 填写指令→生成→验证逐字显示→草稿保存 | US-005 |
| TC-E2E-004 | 确认文案-发布 | 生成→确认→绑定账号→发布→查看状态 | US-006,US-008 |
| TC-E2E-005 | 视频生成端到端 | 确认文案→创建视频项目→查看分镜→提交生成→导出 | US-010,US-011,US-012 |
