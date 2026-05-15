# INC-2026-05-15: GitHub Actions E2E Job 持续被跳过（skipped，耗时 0s）

**事件 ID**: INC-2026-05-15-e2e-job-skipped
**日期**: 2026-05-15
**严重级别**: HIGH（E2E 防护层完全失效，生产 bug 因此漏网）
**状态**: 调查完成，修复方案待用户 CONFIRM

---

## 1. 症状复现

### 受影响的 CI Run

| Run ID | 触发事件 | 分支 | E2E job 状态 | 耗时 |
|--------|----------|------|-------------|------|
| 25904034448 | push main | main | skipped | 0s |
| 25905840711 | push main | main | skipped | 0s |

**直接后果**: PR-5 实现的 LLM 选择器置灰 bug（INC-2026-05-15）本应被 `e2e/llm_selection.spec.ts` 中 12 个场景拦住，但因 E2E job 被跳过，bug 漏入生产环境。

### 症状特征

- 后端 unit (`test-unit`)、integration (`test-integration`) job 正常运行并通过
- `build-frontend` job 正常运行
- `smoke-test` job 状态取决于物理部署是否成功（两个 run 中均显示 skipped 或 success）
- `e2e-test` job 始终显示 skipped，耗时恒为 0s
- 无任何 Playwright 报告产物上传

---

## 2. 根因分析

### 根因 A（主因）：`e2e-test` job 依赖 `smoke-test`，而 `smoke-test` 在多数情况下被跳过

**ci.yml 第 737-741 行**（`e2e-test` job 定义头部）：

```yaml
# Stage 9: E2E Tests (Playwright against production)
e2e-test:
  name: E2E Tests (Playwright)
  runs-on: ubuntu-latest
  needs: smoke-test                    # <-- 强依赖 smoke-test
  if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
```

**ci.yml 第 719-735 行**（`smoke-test` job 定义）：

```yaml
smoke-test:
  name: Post-deploy Smoke Tests
  runs-on: ubuntu-latest
  needs: [deploy-production, deploy-physical-prod]   # <-- 同时依赖两条部署路径
  if: |
    always() &&
    (needs.deploy-production.result == 'success' || needs.deploy-physical-prod.result == 'success')
```

**GitHub Actions 的 skipped 传播机制**：

当 `needs` 中列出的上游 job 被跳过（skipped）时，下游 job 默认也会被跳过，**即使下游 job 自身的 `if` 条件满足**。这是 GitHub Actions 的核心行为：skipped 会沿依赖链向下传播。

具体传播路径（push main，物理部署模式）：

```
compute-deploy-mode → mode=physical

deploy-production
  if: mode == 'docker'  → 条件不满足 → SKIPPED

validate-image
  needs: [docker-build, ...]
  if: mode == 'docker'  → SKIPPED

docker-build
  if: mode == 'docker'  → SKIPPED

deploy-physical-prod
  needs: [test-integration, build-frontend, compute-deploy-mode]
  if: mode == 'physical' && ref == 'refs/heads/main'  → 条件满足
  → 尝试 SSH 连接 secrets.PROD_HOST 执行物理部署
  → 若部署成功: SUCCESS
  → 若 secrets 未配置 / SSH 失败 / 脚本出错: FAILURE / SKIPPED
```

关键问题：`smoke-test` 的 `if` 条件使用 `always()` 规避了上游 skipped 传播，**但 `e2e-test` 没有 `always()`**：

```yaml
# smoke-test 有 always() 守卫，能在 deploy-production=skipped 时继续运行
smoke-test:
  if: |
    always() &&                            # <-- 这里有 always()
    (needs.deploy-production.result == 'success' || needs.deploy-physical-prod.result == 'success')

# e2e-test 没有 always() 守卫
e2e-test:
  needs: smoke-test
  if: github.ref == 'refs/heads/main' && ...   # <-- 没有 always()
```

结论：当 `smoke-test` 本身因物理部署失败而被跳过，或 `smoke-test` 的结果不是 `success`（而是 `failure`），`e2e-test` 就会被跳过。即使 `smoke-test` 成功，只要 `e2e-test` 的 `needs: smoke-test` 没有用 `always()` 或显式 `result` 过滤，skipped 也会传播下来。

实际观察到的两个 run（25904034448、25905840711）中，`smoke-test` 状态：若物理部署 job 本身对 secrets 有依赖而失败，`smoke-test` 的 `if` 条件中 `deploy-physical-prod.result == 'success'` 为 false，`deploy-production.result == 'success'` 也为 false（它是 skipped，skipped != success），则 `smoke-test` 被跳过 → `e2e-test` 也被跳过。

### 根因 B（次要，独立于根因 A）：`e2e-test` job 的 working-directory 和 Playwright 配置指向错误位置

即使 `e2e-test` job 成功触发，它也**不会运行 PR-5 写的 `llm_selection.spec.ts`**。

**ci.yml 第 744-746 行**：

```yaml
defaults:
  run:
    working-directory: project_workspace/content_gen_platform/src/tests   # <-- 旧的 tests/ 目录
```

**`src/tests/playwright.config.js` 第 8-9 行**：

```javascript
testDir: '.',
testMatch: ['e2e/**/*.spec.{js,ts}', 'playwright/**/*.spec.{js,ts}'],
```

`src/tests/` 目录下的 E2E 测试文件清单：

```
src/tests/e2e/01_auth.spec.js
src/tests/e2e/02_knowledge_base.spec.js
src/tests/e2e/03_workspace.spec.js
src/tests/e2e/04_settings.spec.js
src/tests/e2e/05_content_publish.spec.js
src/tests/playwright/kb.spec.ts
```

而 PR-5 的 `llm_selection.spec.ts` 位于：

```
src/frontend/e2e/llm_selection.spec.ts
```

两套 Playwright 配置并存：

| 配置文件 | 位置 | testDir | 覆盖范围 |
|---------|------|---------|---------|
| `src/tests/playwright.config.js` | CI job 使用的配置 | `src/tests/` | 旧版 JS spec + kb.spec.ts |
| `src/frontend/playwright.config.ts` | 本地开发使用 | `src/frontend/e2e/` | 所有 TS spec（含 llm_selection.spec.ts） |

**后果**：即使 e2e-test job 正常运行，`llm_selection.spec.ts` 的 12 个场景永远不会被执行，因为 CI job 根本不扫描 `src/frontend/e2e/` 目录。

### 根因 C（辅助）：E2E job 耦合在生产部署后，测试频率极低

`e2e-test` 位于 Stage 9，整条链路为：

```
push → lint → test-unit → test-integration → build-frontend
                                           ↓
                             deploy-physical-prod → smoke-test → e2e-test
```

每次 push 都需要执行一次完整物理部署才能触发 E2E。若 PR 对 pull_request 事件不触发（ci.yml 第 9-10 行明确了 PR 不走 E2E），则 **PR 合并前永远没有 E2E 保护**。

---

## 3. 为什么 a872f44 "声称的修复"没有生效

根据 commit 历史（PR-5 期间），a872f44 声称修复了 E2E 跳过问题，但实际没有生效。

根据对 ci.yml 当前状态的分析，a872f44 大概率只修改了 `e2e-test` job 自身的某个属性（例如修正了 `if:` 条件的触发事件，或修改了 `working-directory`），但**没有解决根本问题**：

1. **没有断开 `e2e-test` 对 `smoke-test` 的强依赖**：`needs: smoke-test` 仍然存在，只要 smoke-test 被 skip，e2e-test 就会被 skip，无论 `if:` 条件如何写。
2. **没有修复 working-directory 问题**：CI job 仍然指向 `src/tests/`，`llm_selection.spec.ts` 仍然在扫描范围之外。
3. **没有在 `if:` 中加 `always()`**：不加 `always()` 时，`needs` 中任何上游 job 的 skipped 状态都会传播到下游，导致下游 skipped。

**关键验证**：ci.yml 第 742 行当前的 `if` 条件：

```yaml
if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
```

这个条件本身是正确的，说明 a872f44 可能修的就是这里（之前可能缺少 `workflow_dispatch`，或多了某个错误条件）。但它修的只是 `if:` 条件，**没有修 `needs: smoke-test` 导致的 skipped 传播**，所以实际上没有生效。

---

## 4. 修复方案（设计，不实施）

### 方案概述

需要同时解决三个层次的问题：

1. 让 `e2e-test` job 在 push main 时**可靠触发**（不依赖生产部署成功）
2. 让 CI 扫描到 `src/frontend/e2e/` 中的 `llm_selection.spec.ts`
3. 防止将来再出现"E2E 静默跳过"的回归

---

### Fix 1：解除 `e2e-test` 对 `smoke-test` 的强依赖，改为直接依赖 `build-frontend`

**当前架构问题**：E2E 测试绑定在生产部署之后，本质上是"部署后集成验证"，而不是"合并前质量门"。

**修复方案 A（推荐）**：将 E2E 拆分为两个独立 job：

- **`e2e-unit`**：对前端组件的 mock E2E（`llm_selection.spec.ts` 这类不依赖真实后端的测试），在 `build-frontend` 之后立即运行，PR 和 push 都触发
- **`e2e-prod`**：保留原有的真实环境 E2E（`src/tests/e2e/` 中的 JS spec），依赖 smoke-test，仅 push main 后运行

**具体 diff（Fix 1A，新增 `e2e-frontend` job）**：

```yaml
# 在 build-frontend job 之后，deploy-physical-prod 之前，新增：

  # Stage 4.5: Frontend E2E Tests (Playwright, mock-based, 无需真实后端)
  # 覆盖 src/frontend/e2e/ 中基于 page.route mock 的场景（如 llm_selection.spec.ts）
  # 对 push 和 pull_request 均运行，是合并前的质量门控。
  e2e-frontend:
    name: Frontend E2E Tests (Playwright, mocked)
    runs-on: ubuntu-latest
    needs: build-frontend            # 仅依赖前端构建，不依赖任何部署
    defaults:
      run:
        working-directory: project_workspace/content_gen_platform/src/frontend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: project_workspace/content_gen_platform/src/frontend/package-lock.json

      - name: Install dependencies
        run: npm install

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium

      - name: Start frontend dev server (background)
        run: npm run dev &
        env:
          CI: "true"

      - name: Wait for dev server
        run: npx wait-on http://localhost:5173 --timeout 60000

      - name: Run frontend E2E tests (mocked)
        run: npx playwright test
        env:
          CI: "true"
          E2E_BASE_URL: "http://localhost:5173"

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-frontend-report
          path: project_workspace/content_gen_platform/src/frontend/playwright-report/
          retention-days: 7
```

**方案 B（最小改动，不新增 job，仅修 e2e-test 的 needs）**：

将 `e2e-test` 的 `needs` 从 `smoke-test` 改为直接依赖 `build-frontend`，并加 `always()` 保护：

```yaml
# 修改前（ci.yml 第 739-742 行）：
  e2e-test:
    name: E2E Tests (Playwright)
    runs-on: ubuntu-latest
    needs: smoke-test
    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')

# 修改后：
  e2e-test:
    name: E2E Tests (Playwright)
    runs-on: ubuntu-latest
    needs: [build-frontend, test-integration]   # 改为依赖测试和构建，不依赖部署
    if: |
      always() &&
      needs.build-frontend.result == 'success' &&
      github.ref == 'refs/heads/main' &&
      (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
```

---

### Fix 2：修正 `e2e-test` job 的 working-directory 和测试范围

**当前（ci.yml 第 744-746 行）**：

```yaml
defaults:
  run:
    working-directory: project_workspace/content_gen_platform/src/tests
```

**问题**：此目录下的 `playwright.config.js` 只扫描 `e2e/**` 和 `playwright/**`，不包含 `src/frontend/e2e/`。

**两种修复路径**：

**路径 2A（推荐，与 Fix 1A 配合）**：新建 `e2e-frontend` job，working-directory 指向 `src/frontend/`，使用 `frontend/playwright.config.ts`，专门运行前端 mock 型 E2E。原有 `e2e-test` job 保留，继续跑 `src/tests/e2e/` 中的真实环境 E2E。

**路径 2B（备选，统一配置）**：在 `src/tests/playwright.config.js` 中增加 `frontend/e2e` 的扫描路径，并相应修改 working-directory：

```javascript
// src/tests/playwright.config.js 修改
testMatch: [
  'e2e/**/*.spec.{js,ts}',
  'playwright/**/*.spec.{js,ts}',
  '../frontend/e2e/**/*.spec.ts',   // 新增：扫描 frontend E2E
],
```

此路径的问题：`src/frontend/playwright.config.ts` 有 `setup` project（auth.setup.ts），与 `src/tests/playwright.config.js` 的无 setup 结构冲突，合并后需要额外处理认证流程。

---

### Fix 3：防止 E2E job 静默跳过的防回归措施

**方案**：在 GitHub 仓库 Settings > Branches > Branch protection rules 中，为 `main` 分支添加 Required status checks：

- 必须包含 `e2e-frontend`（新增 job 名称）或 `E2E Tests (Playwright)`
- 勾选 "Require status checks to pass before merging"
- 勾选 "Require branches to be up to date before merging"

**效果**：若 E2E job 被跳过（skipped）或失败，GitHub 会阻止 PR 合并，而不是静默通过。

**补充：在 ci.yml 中加入 E2E 完整性断言 job**：

```yaml
  # 确保 E2E job 实际运行（不被 skipped）的哨兵 job
  assert-e2e-ran:
    name: Assert E2E Did Not Skip
    runs-on: ubuntu-latest
    needs: [e2e-frontend]
    if: |
      always() &&
      github.ref == 'refs/heads/main' &&
      github.event_name == 'push'
    steps:
      - name: Fail if E2E was skipped
        run: |
          if [ "${{ needs.e2e-frontend.result }}" = "skipped" ]; then
            echo "ERROR: e2e-frontend job was skipped. This is not allowed on main."
            exit 1
          fi
          echo "E2E result: ${{ needs.e2e-frontend.result }} — OK"
```

---

### 修复方案总表

| 编号 | 问题 | 修复动作 | 优先级 |
|------|------|---------|--------|
| Fix 1A | E2E 依赖 smoke-test 导致 skipped 传播 | 新增独立 `e2e-frontend` job，needs: build-frontend | P0 |
| Fix 2A | working-directory 指向旧 tests/ 目录 | `e2e-frontend` job 使用 `src/frontend/` 目录 | P0 |
| Fix 3 | 无防回归机制，E2E 静默跳过不报警 | GitHub Branch Protection + `assert-e2e-ran` job | P1 |
| Fix 4（可选） | PR 合并前无 E2E 保护 | 在 `pull_request` 事件中也触发 `e2e-frontend` | P2 |

---

## 5. 下一步（待用户 CONFIRM 后进入实施）

### Implementation 任务清单

**Task 1 [P0] — 新增 `e2e-frontend` job（`.github/workflows/ci.yml`）**
- 在 `build-frontend` job 之后插入新 job
- working-directory: `src/frontend/`
- needs: `build-frontend`（不依赖任何部署 job）
- 触发条件：push main + pull_request（两个事件均运行）
- 安装 Node 20 + npm install + playwright install --with-deps chromium
- 启动 vite dev server（后台），用 wait-on 等待就绪
- 运行 `npx playwright test`（使用 `src/frontend/playwright.config.ts`）
- 上传 playwright-report 产物（if: always()）

**Task 2 [P0] — 在 `src/frontend/package.json` 中确认 `wait-on` 依赖**
- 确认或新增 `wait-on` devDependency，供 CI 等待 vite dev server 就绪

**Task 3 [P1] — 新增 `assert-e2e-ran` 哨兵 job（`.github/workflows/ci.yml`）**
- needs: e2e-frontend
- 若 result == 'skipped' 则 exit 1

**Task 4 [P1] — GitHub Branch Protection 配置**
- 在 main 分支 protection rules 中添加 `Frontend E2E Tests (Playwright, mocked)` 为必须通过的 status check
- 需要仓库管理员权限操作 GitHub Settings

**Task 5 [P2] — 补充 `pull_request` 事件下的 E2E 触发**
- 修改 `e2e-frontend` job 的 `if:` 条件，使 PR 也能触发 E2E

**Task 6 [P2] — 清理冗余配置**
- 评估是否将 `src/tests/playwright.config.js` 与 `src/frontend/playwright.config.ts` 合并，或明确各自职责边界
- 在两个 config 文件中各加注释，说明适用范围

---

## 附录 A：关键文件路径

| 文件 | 用途 |
|------|------|
| `.github/workflows/ci.yml` 第 737-770 行 | 现有 `e2e-test` job 定义（有缺陷） |
| `.github/workflows/ci.yml` 第 719-735 行 | `smoke-test` job（`e2e-test` 的上游依赖） |
| `src/tests/playwright.config.js` | CI 实际使用的 Playwright 配置（不扫描 frontend/e2e） |
| `src/frontend/playwright.config.ts` | 本地开发使用的 Playwright 配置（扫描 frontend/e2e） |
| `src/frontend/e2e/llm_selection.spec.ts` | PR-5 写的 12 个场景（CI 从未执行过） |
| `src/tests/e2e/` | 旧版 JS E2E spec（`e2e-test` job 实际运行的测试） |

## 附录 B：GitHub Actions skipped 传播机制说明

GitHub Actions 的官方行为：
- 当 job A 的 `needs` 中包含 job B，且 job B 结果为 `skipped`，则 job A 默认也会被 `skipped`，**即使 job A 自身的 `if:` 条件为 true**
- 唯一的突破方式是在 job A 的 `if:` 中加入 `always()`，或显式检查 `needs.B.result != 'skipped'`
- 这是 GitHub Actions 的设计，不是 bug；但容易被误解为"只要 if 条件对了 job 就会跑"

当前 `e2e-test` 的 `if:` 没有 `always()`，且 `needs: smoke-test` 直接暴露于这个传播机制下，是 skipped 的直接原因。
