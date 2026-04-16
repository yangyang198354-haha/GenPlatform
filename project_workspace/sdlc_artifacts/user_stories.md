# User Stories — GenPlatform KB Extension
# file: user_stories.md
# author_agent: sub_agent_requirement_analyst
# project: genplatform_kb_extension
# phase: GROUP_A / PHASE_02
# status: DRAFT
# created_at: 2026-04-16

---

## Epic 1：目录上传（F-01）

### US-001 — 上传整个目录批量导入文档

**As** 一名需要将大量文档导入知识库的用户，
**I want** 选择一个本地目录（含子目录），一次性将所有受支持的文档上传入库，
**So that** 我不需要逐个文件手动上传，节省操作时间。

**验收标准（Gherkin）**：

```gherkin
Scenario: 成功上传含嵌套子目录的目录
  Given 用户已登录
  And 用户本地有一个目录结构：
        root/
          doc1.pdf
          sub/
            doc2.docx
            sub2/
              doc3.txt
  When 用户点击"上传目录"，选择 root/ 目录并提交
  Then 后端创建 3 条 Document 记录（doc1.pdf, doc2.docx, doc3.txt）
  And 每条记录的 status 初始为 "processing"
  And 3 个 Celery 异步任务被触发
  And 前端显示"成功提交 3 个文件，处理中…"

Scenario: 目录中含不支持格式文件时跳过
  Given 用户已登录
  And 目录中包含 report.pdf, image.jpg, script.exe
  When 用户上传该目录
  Then 仅 report.pdf 被入库（1 条 Document 记录）
  And 响应体中包含被跳过文件列表：["image.jpg", "script.exe"]
  And 前端展示"1 个文件入库，2 个文件格式不支持已跳过"

Scenario: 目录中无受支持文件
  Given 用户已登录
  And 目录中只有 photo.png 和 data.xlsx
  When 用户上传该目录
  Then 返回 HTTP 400
  And 错误信息为"所选目录中未包含受支持的文档"
  And 前端显示对应错误提示
```

**关联需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003

---

### US-002 — 目录上传时按文件名默认命名

**As** 上传目录的用户，
**I want** 批量上传的每个文档默认以其文件名作为显示名称，
**So that** 我无需在上传时逐一填写标题，上传后仍可重命名。

**验收标准（Gherkin）**：

```gherkin
Scenario: 批量上传后文档名默认为文件名
  Given 用户已登录
  And 目录中有 annual_report.pdf 和 meeting_notes.docx
  When 用户上传该目录（不填写任何标题）
  Then annual_report.pdf 对应 Document.name = "annual_report.pdf"
  And meeting_notes.docx 对应 Document.name = "meeting_notes.docx"
  And 两个文档的 original_filename 与 name 相同

Scenario: 嵌套路径中的文件名正确提取
  Given 用户已登录
  And 目录中有 root/docs/2024/report.pdf
  When 用户上传该目录
  Then Document.name = "report.pdf"（仅纯文件名，不含路径）
  And Document.original_filename = "report.pdf"
```

**关联需求**：REQ-FUNC-002, REQ-FUNC-006

---

### US-003 — 目录上传时逐文件检查大小与配额

**As** 系统，
**I want** 在目录批量上传时逐文件校验大小限制和存储配额，
**So that** 超限的文件被跳过而不影响其他文件的入库。

**验收标准（Gherkin）**：

```gherkin
Scenario: 单个文件超过 50MB 被跳过，其余正常入库
  Given 用户已登录，存储空间充足
  And 目录中有 small.txt (1KB) 和 large.pdf (60MB)
  When 用户上传该目录
  Then small.txt 正常入库
  And large.pdf 被跳过，原因标注为"文件超过 50MB 限制"
  And 响应体中包含被拒绝项列表

Scenario: 配额不足时优先入库已遍历到的文件
  Given 用户剩余配额仅 5MB
  And 目录中有 a.txt (3MB), b.txt (3MB), c.txt (1MB)
  When 用户上传该目录
  Then a.txt 入库（已消耗 3MB，剩余 2MB）
  And b.txt 被拒绝（需要 3MB 但仅剩 2MB），标注"配额不足"
  And c.txt 被拒绝，标注"配额不足"
  And 响应体中注明"配额已满，部分文件未能导入"
```

**关联需求**：REQ-FUNC-001, REQ-NFUNC-005

---

## Epic 2：用户隔离（F-02）

### US-004 — 用户只能看到自己的文档

**As** 登录用户，
**I want** 知识库只展示我自己上传的文档，
**So that** 其他用户的私有文档对我不可见，保护数据隐私。

**验收标准（Gherkin）**：

```gherkin
Scenario: 文档列表只返回当前用户的文档
  Given 用户 Alice 有文档 doc_alice.pdf
  And 用户 Bob 有文档 doc_bob.pdf
  When Alice 调用 GET /api/v1/knowledge/documents/
  Then 响应中只包含 doc_alice.pdf
  And 不包含 doc_bob.pdf

Scenario: 未认证用户无法访问文档列表
  Given 请求未携带 Authorization 头
  When 调用 GET /api/v1/knowledge/documents/
  Then 返回 HTTP 401
```

**关联需求**：REQ-FUNC-004, REQ-NFUNC-001

---

### US-005 — 用户无法访问他人的文档详情

**As** 系统管理员，
**I want** 确保用户 B 无法通过猜测 ID 访问或删除用户 A 的文档，
**So that** 系统不会发生数据泄露或越权破坏。

**验收标准（Gherkin）**：

```gherkin
Scenario: 访问他人文档详情返回 404
  Given Bob 知道 Alice 的文档 ID 为 42
  When Bob 调用 GET /api/v1/knowledge/documents/42/
  Then 返回 HTTP 404（不暴露资源存在）

Scenario: 尝试删除他人文档返回 404
  Given Bob 知道 Alice 的文档 ID 为 42
  When Bob 调用 DELETE /api/v1/knowledge/documents/42/
  Then 返回 HTTP 404
  And 文档 42 在数据库中仍然存在

Scenario: 尝试重命名他人文档返回 404
  Given Bob 知道 Alice 的文档 ID 为 42
  When Bob 调用 PATCH /api/v1/knowledge/documents/42/ {"name": "hacked"}
  Then 返回 HTTP 404
  And 文档 42 的 name 未改变
```

**关联需求**：REQ-FUNC-004, REQ-FUNC-005, REQ-NFUNC-001

---

### US-006 — 语义检索不返回他人的内容

**As** 使用 AI 问答功能的用户，
**I want** 语义检索（RAG）只在我的知识库中搜索，
**So that** 不会检索到其他用户上传的敏感文档。

**验收标准（Gherkin）**：

```gherkin
Scenario: search() 不返回其他用户的 DocumentChunk
  Given 用户 Alice 有 DocumentChunk：content="Alice的机密报告"
  And 用户 Bob 有 DocumentChunk：content="Bob的机密报告"
  When 以 Alice 的 user_id 调用 search(user_id=Alice.id, query="机密报告")
  Then 结果中包含 "Alice的机密报告"
  And 结果中不包含 "Bob的机密报告"
```

**关联需求**：REQ-FUNC-005, REQ-NFUNC-001

---

## Epic 3：文件名默认 + 重命名（F-03）

### US-007 — 单文件上传默认使用文件名

**As** 上传单个文件的用户，
**I want** 不填写文档标题时系统自动使用文件名，
**So that** 我可以快速上传而无需每次手动命名。

**验收标准（Gherkin）**：

```gherkin
Scenario: 不填写标题时 name 默认为文件名
  Given 用户已登录
  When 用户上传 financial_report.pdf，不填写标题
  Then Document.name = "financial_report.pdf"
  And Document.original_filename = "financial_report.pdf"

Scenario: 填写标题时 name 使用用户输入
  Given 用户已登录
  When 用户上传 financial_report.pdf，填写标题为"2024财报"
  Then Document.name = "2024财报"
  And Document.original_filename = "financial_report.pdf"
```

**关联需求**：REQ-FUNC-006

---

### US-008 — 上传后重命名文档

**As** 希望整理知识库的用户，
**I want** 对已上传的文档进行重命名，
**So that** 文档列表更整洁易读，而不影响原始文件或已生成的向量分块。

**验收标准（Gherkin）**：

```gherkin
Scenario: 成功重命名自己的文档
  Given 用户已登录，拥有文档 ID=5，当前 name="旧名称"
  When 用户调用 PATCH /api/v1/knowledge/documents/5/ {"name": "新名称"}
  Then 返回 HTTP 200
  And Document(id=5).name = "新名称"
  And Document(id=5).original_filename 不变
  And DocumentChunk 数量和内容不变

Scenario: 重命名后前端列表即时更新
  Given 用户在知识库页面
  And 文档"旧名称"显示在列表中
  When 用户点击"重命名"并输入"新名称"，确认
  Then 列表中该行名称变为"新名称"

Scenario: 不能重命名他人的文档
  Given Bob 知道 Alice 的文档 ID 为 42，name="Alice文档"
  When Bob 发送 PATCH /api/v1/knowledge/documents/42/ {"name": "Bob改名"}
  Then 返回 HTTP 404
  And Document(id=42).name 仍为 "Alice文档"
```

**关联需求**：REQ-FUNC-006, REQ-FUNC-007, REQ-NFUNC-002

---

## 用户故事优先级汇总

| US 编号 | 标题 | Epic | 优先级 | 复杂度 |
|---------|------|------|--------|--------|
| US-001  | 上传整个目录批量导入 | F-01 | P0 | 高 |
| US-002  | 目录上传按文件名命名 | F-01/F-03 | P0 | 低 |
| US-003  | 逐文件检查大小与配额 | F-01 | P0 | 中 |
| US-004  | 用户只能看到自己的文档 | F-02 | P0 | 低（已有实现，需测试补全） |
| US-005  | 用户无法访问他人文档 | F-02 | P0 | 低（已有实现，需测试补全） |
| US-006  | 检索不返回他人内容 | F-02 | P0 | 低（已有实现，需测试补全） |
| US-007  | 单文件上传默认文件名 | F-03 | P1 | 低（已有实现，需前端调整） |
| US-008  | 上传后重命名文档 | F-03 | P1 | 中 |
| US-009  | DeepSeek 模型和参数配置 | F-04 | P0 | 中 |
| US-010  | 火山引擎模型和参数配置 | F-04 | P0 | 中 |

---

## Epic 4：LLM 参数配置扩展（新增 — 2026-04-16）

### US-009 — 为 DeepSeek 选择模型并配置推理参数

**As** 使用 DeepSeek API 的用户，
**I want** 在设置页面选择 DeepSeek 模型并配置 temperature 和 max_tokens，
**So that** 我可以根据任务类型调整模型行为，而无需修改代码。

**验收标准（Gherkin）**：

```gherkin
Scenario: 选择 DeepSeek 模型并保存后能回显
  Given 用户已登录，在"大语言模型"设置页
  And 当前服务商为 DeepSeek
  When 用户从模型下拉框选择 "deepseek-reasoner"
  And 设置 temperature = 0.5，max_tokens = 2048
  And 点击保存
  Then 页面显示"LLM 配置已保存"
  When 用户刷新页面，重新打开设置
  Then 模型下拉框显示 "deepseek-reasoner"
  And temperature 输入框显示 0.5
  And max_tokens 输入框显示 2048

Scenario: 未选择模型时保存使用默认模型
  Given 用户已登录，在"大语言模型"设置页
  And 服务商为 DeepSeek，模型下拉框未选择（默认 deepseek-chat）
  When 用户填写 API Key 并保存
  Then 后端 config 中 model_name = "deepseek-chat"
```

**关联需求**：REQ-FUNC-010, REQ-FUNC-012

---

### US-010 — 为火山引擎选择模型并配置推理参数

**As** 使用火山引擎（豆包）API 的用户，
**I want** 在设置页面选择豆包模型系列、填写 endpoint ID，并配置 temperature 和 max_tokens，
**So that** 我可以灵活控制豆包 API 的调用行为。

**验收标准（Gherkin）**：

```gherkin
Scenario: 选择豆包模型并保存后能回显
  Given 用户已登录，在"大语言模型"设置页
  And 当前服务商为 火山引擎（豆包）
  When 用户从模型下拉框选择 "Doubao-pro-32k"
  And 填写 endpoint ID = "ep-20240101-abc123"
  And 设置 temperature = 0.8，max_tokens = 2000
  And 点击保存
  Then 页面显示"LLM 配置已保存"
  When 用户刷新页面
  Then 豆包模型下拉框显示 "Doubao-pro-32k"
  And endpoint ID 输入框显示 "ep-20240101-abc123"（已脱敏显示）
  And temperature 显示 0.8
  And max_tokens 显示 2000

Scenario: 火山引擎保存时 endpoint ID 必填
  Given 用户已登录，在火山引擎配置区块
  And API Key 已填写，但 endpoint ID 为空
  When 用户点击保存
  Then 显示警告"火山引擎需要填写模型 ID（推理接入点）"
```

**关联需求**：REQ-FUNC-011, REQ-FUNC-012
