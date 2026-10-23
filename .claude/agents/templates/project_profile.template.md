# Project Profile — {项目名}

> 复制本模板为 `.claude/agents/project_profile.md` 并填写。这是套件中**唯一**存放项目事实的地方，agent 本体与共享协议保持通用。
> 没有画像时，pm-orchestrator 会扫描仓库生成初稿，请用户确认后再开始流程。
> 不确定的项写"未知"，不要猜；**本文件不得包含任何密码、令牌、私钥**（只写凭据存放位置）。

<file_header>
  <author_agent>human | pm-orchestrator(draft)</author_agent>
  <timestamp>{date -Iseconds}</timestamp>
  <project_name>{项目名}</project_name>
  <version>1.0.0</version>
  <status>APPROVED</status>   <!-- PM 生成的初稿为 DRAFT，用户确认后改为 APPROVED -->
</file_header>

## P1. 项目概况
- 一句话描述：
- 技术栈：| 层 | 技术 | 版本 |
- 运行形态：Web 服务 / CLI / 库 / 移动端 / 嵌入式 / 数据管道 …
- 权威说明文档：CLAUDE.md / README / docs/…

## P2. 文档工作区
- `docs_root`: project_workspace/{project_name}/
- `docs_layout`: nested | flat
- 是否入库: 是 / 否（.gitignore）

## P3. 代码布局
- `code_mode`: in-repo | greenfield
- 代码目录：| 组件 | 目录 | 语言 |
- 测试位置约定：| 组件 | 新测试放在 | 命名 | 测试基类/框架 |
- 不可修改的目录（第三方、生成产物、vendor）：

## P4. 命令（全部在开发机/CI 上运行，严禁连生产）
| 用途 | 工作目录 | 命令 | 备注 |
|---|---|---|---|
| 环境准备 | | | 如需 venv / env 变量 |
| 静态检查 / 编译检查 | | | |
| 单元测试 | | | 分层机制：tag / marker / 目录 |
| 集成测试 | | | |
| E2E 测试 | | | |
| 全量回归 | | | 耗时约 … |
| 构建 | | | |
- 已知既有失败 / 基线来源：（文件或 skill；以实跑为准）
- 缺依赖时的处理：如实标 BLOCKED，不安装

## P5. 质量判定
- FULL_FLOW `gate_mode`: threshold — unit_pass 0.80 / integration_pass 0.90 / critical_path 1.00 / coverage_min 无
- INCREMENTAL `gate_mode`: baseline — 零新增失败
- `inferred_max`: 0.20（需求中 [INFERRED] 占比上限）

## P6. 开发约定
- 数据迁移方式（工具 / 手写 / 禁止自动生成全量 / 已上线迁移不可改）：
- 鉴权与权限模型：
- 代码风格 / lint 规则：
- 依赖管理（锁文件、版本 pin）：
- 其他必须遵守的约定：

## P7. 环境、CI 与部署
- 环境：
  | 环境 | 存在 | 访问方式（不含口令） | 部署需用户确认 | 备注 |
  |---|---|---|---|---|
  | dev/local | 是 | | 否 | |
  | staging | 是/否 | | 否/是 | |
  | production | 是 | | **是** | |
- 部署方式：git pull + 服务重启 / CI 流水线 / 容器 / 包发布 / 手工 …
- 允许的部署策略：recreate / rolling / blue-green / canary（只列基础设施真正支持的）
- 构建产物管理：无 / 制品库 / 镜像仓库 …（存储位置、命名、晋升条件）
- 运行单元（服务/进程/定时任务）与"改什么需重启什么"：
- 目标机上必须保留的本地状态（本地配置、数据目录、未入库文件）：
- 回滚方式偏好：revert 提交后重新部署 / 切回上一版本制品 / …
- 部署后验证：健康检查 URL、日志位置、冒烟请求
- CI 系统与配置文件：（devops 可在需求要求时修改）
- 部署相关配置文件：

## P8. 禁用项（门控时任一出现即 FAIL）
| 禁用的技术 / 操作 | 原因 |
|---|---|

## P9. 版本控制与远程操作权限
- 分支策略：
- 谁执行 commit / push：主会话在用户确认后 / CI / …
- 子代理是否可 ssh / 部署：否（缺省）；E2 授权后 devops 可执行 P7 中的部署命令
- 提交前必须通过的检查：

## P10. 额外必读（PM 填入 required_reading）
| Agent | 额外文件 |
|---|---|
| test-engineer | |
| devops-engineer | |
