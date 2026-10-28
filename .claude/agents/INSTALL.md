# SDLC Agent Suite v3.6 — 安装

1. 把 `.claude/agents/`、`.claude/hooks/` 复制到目标仓库的 `.claude/` 下（已有旧版先备份）。
2. 把 `settings.example.json` 中的 `hooks` 与 `permissions` 合并进目标仓库的 `.claude/settings.json`：
   - `SubagentStop` → `sdlc_subagent_stop.py`：经验收件箱与 agent_response 完整性检查（不合并也能用，PM 会补记）。
   - `PreToolUse`（Agent）→ `sdlc_pre_agent.py`：当前目录不在仓库根时拒绝调用 SDLC 子代理（含 pm-orchestrator），防止子代理记忆目录建错位置。
   - `PreToolUse`（WebFetch / WebSearch）→ `sdlc_webfetch_guard.py`：agent-builder 只能访问 Claude Code 官方文档白名单页（不合并时只靠提示词约束）。
   - `permissions.ask`：远程操作（ssh/scp/git push…）与安装依赖（pip/npm…）前要求确认。
3. 在目标仓库根目录启动 PM，直接提需求。两种方式任选：
   - 主会话模式：`claude --agent pm-orchestrator`。可以当场澄清，也可以授权部署。
   - 子代理模式：在普通会话里 `@pm-orchestrator <需求>`。PM 跑到检查点后返回问题清单，你回答后再 @ 一次续跑；止于部署计划，不执行部署。
   - 从旧版升级：`settings.json` 里 SubagentStop 的 matcher 要加上 `pm-orchestrator`。
   - 没有 `project_profile.md` 时，PM 扫描仓库生成画像初稿，逐项请你确认后再开始。
4. 记忆：每个 agent 的项目记忆在 `.claude/agent-memory/{agent}/MEMORY.md`，首次运行自动创建（需开启 Claude Code 的 auto memory，默认开启）。
5. 知识蒸馏：PM 交付后自动调用 kb-curator；也可以随时 `claude --agent kb-curator`。报告在 `project_workspace/_kb_distillation/`。
6. 评审或生成 agent：`claude --agent agent-builder`，或在主会话中调用。它默认不写文件；需要落盘时在请求里写 `WRITE_TARGET: <路径>`（覆盖已有文件另加 `OVERWRITE_AUTHORIZED: <路径>`）。
7. 建议把项目禁用的工具在 settings.json 里设为 deny。
