# Knowledge Base — devops_engineer
<!-- 记录 CI/CD、部署中遇到的经验教训 -->

---

## DE-L001: CI Stage 顺序 — 集成测试 pytest 路径和 settings

**日期**: 2026-04-10  
**问题**: Stage 3 集成测试运行 `pytest apps/ -m integration` 收集到 0 个测试

**根因**: 
1. 集成测试文件在 `tests/` 目录，不在 `apps/`
2. `DJANGO_SETTINGS_MODULE=config.settings.development` 未禁用 throttle

**正确配置**:
```yaml
env:
  DJANGO_SETTINGS_MODULE: config.settings.test   # 不是 development
steps:
  - name: Run integration tests
    run: pytest tests/ -m integration -v          # tests/ 不是 apps/
```

**关键点**:
- 不要在集成测试步骤加 `continue-on-error: true`，失败应阻断 pipeline
- 集成测试需要 PostgreSQL + Redis service，单元测试只需 PostgreSQL

---

## DE-L002: CI 冒烟测试 — 所有唯一性字段必须动态生成

**日期**: 2026-04-10  
**问题**: 冒烟测试 SM-002 第二次运行时注册失败（username 重复）

**根因**: `smoke_test.sh` 中 username 硬编码为 `smokeuser`，email 用了时间戳但 username 没有。
生产数据库不在部署间清空，第二次运行必然冲突。

**修复**:
```bash
SMOKE_TS="$(date +%s)"
SMOKE_USER="smoke_${SMOKE_TS}"           # 动态 username
SMOKE_EMAIL="${SMOKE_USER}@test.internal" # 动态 email
```

**原则**: 冒烟测试中所有会写入 DB 的数据都必须唯一化。

---

## DE-L003: E2E 阶段 — 需要 Playwright ESM 配置

**日期**: 2026-04-10  
**问题**: E2E 测试报错 `require is not defined in ES module scope`

**根因**: spec 文件用 ES module `import`，但 `playwright.config.js` 用 CommonJS `require()`。
Node.js 看到 import 语法后将整个包视为 ESM，导致 config 文件中 `require()` 报错。

**修复**:
```json
// package.json
{ "type": "module" }
```
```js
// playwright.config.js
import { defineConfig, devices } from '@playwright/test';
export default defineConfig({ ... });
```

---

## DE-L004: CI Pipeline 设计原则

**日期**: 2026-04-10  
**总结**: 本项目 9-stage CI/CD 经验

**Pipeline 结构**（正确顺序）:
1. Lint & Security Scan
2. Unit Tests（`pytest apps/ -m "not integration" --cov-fail-under=80`）
3. Integration Tests（`pytest tests/ -m integration`，需要 PG + Redis）
4. Frontend Build
5. Docker Build & Push（依赖 3 + 4）
6. Validate Production Image（在 CI 中启动容器验证迁移+启动）
7. Deploy to Production
8. **Post-deploy Smoke Tests**（curl 验证真实生产环境）
9. **E2E Tests**（Playwright 对生产 URL 运行）

**关键规则**:
- Stage 8/9 必须在 Stage 7（deploy）成功后才运行
- 冒烟测试超时设 5 分钟，E2E 超时按测试数量调整
- E2E report 作为 artifact 上传，便于失败时排查

---

## DE-L005: 生产环境 API 行为与开发环境的差异

**日期**: 2026-04-10  

| 行为 | 开发/测试环境 | 生产环境 |
|------|------------|---------|
| 错误密码登录 | 可能返回 400 | simplejwt 返回 **401** |
| 限流 | 测试中禁用 | 100次/小时 |
| 媒体文件 | /tmp/test_media | 持久化存储 |
| DB 数据 | 每次测试清空 | **永久保留** |

**影响**: 冒烟测试脚本检查登录端点可用性时应期望 `401`（非 400）。

---

## DE-L006: E2E 调试流程 — 逐步收窄失败范围

**日期**: 2026-04-10  
**总结**: 本次 E2E 调试历经 6 轮迭代，每轮减少失败数：

| 轮次 | 失败数 | 根因 |
|------|--------|------|
| 1 | 全部超时 (18/18) | `require` in ESM scope |
| 2 | 17/18 超时 | placeholder 选择器错误 |
| 3 | 17/18 超时 | 注册按钮名"注册"→实际"创建账号" |
| 4 | 7/20 失败 | strict mode + ElSelect + 验证器 |
| 5 | 1/20 失败 | warning vs error class |
| 6 | **0/20** ✓ | 全部通过 |

**经验**: E2E 测试失败分两类：
1. **超时型**（30s）→ 元素根本找不到，检查选择器/UI 文本
2. **断言型**（快速失败）→ 元素存在但不符合预期，检查 class/属性

超时型优先看 `Call log: waiting for ...`；断言型优先看 `resolved to N elements` 或 `element(s) not found`。

---

## DE-L007: CI 整体通过标准

**日期**: 2026-04-10  
**最终通过的 CI 配置** (run ID: 24253389670):

```
✓ Stage 1: Lint & Security Scan       (17s)
✓ Stage 2: Unit Tests                 (1m)   pytest apps/ -m "not integration"
✓ Stage 3: Integration Tests          (1m)   pytest tests/ -m integration  ← settings.test
✓ Stage 4: Frontend Build             (24s)
✓ Stage 5: Docker Build & Push        (3m32s)
✓ Stage 6: Validate Production Image  (58s)
✓ Stage 7: Deploy to Production       (2m54s)
✓ Stage 8: Post-deploy Smoke Tests    (14s)  smoke_test.sh 10项检查
✓ Stage 9: E2E Tests (Playwright)     (3m24s) 20个测试全通过
```

总耗时约 **16 分钟**。
