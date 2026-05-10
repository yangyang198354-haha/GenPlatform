# GenPlatform 开发规范

## 提交前测试规则

每次 `git commit` 前，必须在 backend 目录下运行本地可执行测试，所有测试通过后才能提交：

```bash
cd project_workspace/content_gen_platform/src/backend
pytest apps/ tests/ -m "not integration" --tb=short -q
```

**规则说明：**

- `-m "not integration"` 跳过需要 DB / Celery 的集成测试（本地通常无 Docker 环境）
- 集成测试由 GitHub Actions CI 负责，在每次 push 后自动运行
- 本地只需保证纯 unit 测试（mock 外部依赖）全部通过
- 若测试失败，先修复再提交，禁止直接 push 带有明显错误的代码

**自动化：** 项目已配置 git pre-commit hook（`.git/hooks/pre-commit`），每次 `git commit` 时会自动执行上述命令。如需临时跳过（紧急情况），使用 `git commit --no-verify`，但应在下次提交前补跑测试。

---

## 项目结构

```
GenPlatform/
├── project_workspace/content_gen_platform/src/
│   ├── backend/          # Django + Celery 后端
│   └── frontend/         # Vue 3 + Element Plus 前端
├── agents/               # SDLC Agent 定义文件
└── .claude/agents/       # Claude Sub-agent 配置
```

## 技术栈

- **后端**：Python 3.12, Django 4.2, Celery, PostgreSQL, Redis
- **前端**：Vue 3, Element Plus, Vite
- **测试**：pytest, Playwright (E2E)
- **CI/CD**：GitHub Actions
