# GitHub Branch Protection: 将 E2E 哨兵设为必须通过的 Status Check

## 背景

INC-2026-05-15 根因：`e2e-test` job 被 skipped 时，GitHub PR 照常显示绿色，允许合并。
修复后的哨兵 job `assert-e2e-ran` 在 E2E 被跳过时会主动 exit 1，但只有将其设为
Branch Protection 的 required status check，才能从根本上阻止问题 PR 合并。

## 操作步骤（需要仓库 Admin 权限）

1. 打开仓库页面，进入 **Settings** > **Branches**。
2. 找到 `main` 分支的 Branch protection rule，点击 **Edit**（如不存在则点 **Add rule**，
   Branch name pattern 填 `main`）。
3. 勾选 **Require status checks to pass before merging**。
4. 在搜索框中输入 `Assert E2E Did Not Skip`，从下拉列表中选中（job `assert-e2e-ran` 的
   display name），将其加入 required checks。
5. 同时建议勾选 **Require branches to be up to date before merging**（防止陈旧分支绕过检查）。
6. 点击 **Save changes**。

## 验证

配置生效后，创建一个测试 PR：

- 正常情况：`assert-e2e-ran` 通过 → PR 可以合并。
- E2E 被 skipped：`assert-e2e-ran` 失败（exit 1）→ GitHub 阻止合并，并在 PR 页面
  显示 "Assert E2E Did Not Skip" check 未通过。

## 注意事项

- `assert-e2e-ran` 使用 `if: always()`，无论 `e2e-frontend` 结果如何都会运行。
- 若 `e2e-frontend` 本身失败（测试不通过），`assert-e2e-ran` 会输出 result=failure
  并 exit 0（允许失败），让失败的 E2E 测试直接作为 PR 合并的阻断信号。
- 若将来调整 CI 拓扑导致 `e2e-frontend` 的依赖链变化，必须在修改后验证
  `assert-e2e-ran` 仍然能正确触发（不被 skipped）。

## 关联文件

- `.github/workflows/ci.yml` — `e2e-frontend` + `assert-e2e-ran` job 定义
- `project_workspace/content_gen_platform/src/frontend/playwright.config.ci.ts` — CI 专用 Playwright 配置
- `project_workspace/content_gen_platform/docs/incidents/INC-2026-05-15-e2e-job-skipped.md` — 根因分析
