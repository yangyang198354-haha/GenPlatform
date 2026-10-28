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

## P4. 命令（全部在开发机/CI 上运行，严禁连生产；需要仿真器或真实硬件的测试写在 P11-1）
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
| requirement-analyst | |
| system-architect | |
| software-developer | |
| test-engineer | |
| devops-engineer | |

（P11 列出的资料不必在这里重复，PM 会按协议 §E-1 自动分发。）

## P11. 领域与外部依赖（协议 §N）
> 记录模型自身知识靠不住、必须以项目资料为准的事实。三个小节都不涉及时整节写"无"。
> 资料尽量放进仓库（数据手册、寄存器表、规范、OpenAPI / proto、导出的内部文档），这里只写路径。不在仓库里的资料写"无文档"，不要凭印象概括内容。

### P11-1 专用硬件
- 目标硬件：| 名称 | 型号 / 版本 | 工具链（名称与版本） | 资料（数据手册、寄存器表、原理图、引脚表的仓库路径） |
- 测试能力（每类硬件相关测试一行）：
  | 测试类别 | 运行方式 sim / hil / manual | 命令（sim / hil） | 子代理可执行 | 备注（设备占用、前置条件） |
  - `sim`：仿真器或模拟器（QEMU、Renode、厂商模拟器、RTL 仿真）上自动运行。
  - `hil`：连接真实硬件自动运行；只有"子代理可执行=是"时 test-engineer 才能运行。
  - `manual`：只能由人在真机上验证，测试只产出人工验证清单。
- 烧录 / 固件发布：方式（同时登记在 P7 部署方式）、是否可逆、回滚方式（如保留上一版固件镜像、双分区回退）
- 硬件禁止操作（同时登记在 P8）：如修改熔丝位/OTP、写 bootloader、对生产设备烧录

### P11-2 领域算法
- 参考资料：| 主题 | 资料（规范/标准号/论文/内部算法说明，仓库路径） | 参考实现（路径，如 MATLAB/NumPy 原型） | 标准测试数据 golden data（路径与格式） |
- 数值验收：| 指标 | 计算口径 | 阈值 / 容限 | 测试数据 |（如：与参考实现逐点绝对误差 ≤ 1e-9；RMSE ≤ 0.01；单帧处理 ≤ 5 ms）
- 基准 / 精度测试命令（P4 之外的）：
- 数值约定：浮点类型、定点格式（Q 格式）、舍入方式、随机种子

### P11-3 闭源 / 内部 API
- | API | 文档（OpenAPI / proto / WSDL / 导出文档的仓库路径，或"无文档"） | 现有调用代码（`文件`） | 测试替身 mock / 沙箱 / 无 | 凭据位置（不写值） | 调用限制（限流、计费、副作用） |
- 测试中禁止调用的端点或环境（同时登记在 P8）：
- "无文档"的 API：只能使用现有调用代码里已经出现过的用法；需要新用法时，由用户补充文档（协议 §N-2）。
