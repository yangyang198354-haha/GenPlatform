# SDLC Agent Suite v3.3 — 安装

1. 把 `.claude/agents/`、`.claude/hooks/` 复制到目标仓库的 `.claude/` 下（已有旧版先备份）。
2. 把 `settings.example.json` 中的 `hooks` 与 `permissions` 合并进目标仓库的 `.claude/settings.json`：
   - `SubagentStop` → `sdlc_subagent_stop.py`：经验收件箱与 agent_response 完整性检查（不合并也能用，PM 会补记）。
   - `PreToolUse`（Agent）→ `sdlc_pre_agent.py`：主会话不在仓库根时拒绝调用 SDLC 子代理，防止子代理记忆目录建错位置。
   - `permissions.ask`：远程操作（ssh/scp/git push…）与安装依赖（pip/npm…）前要求确认。
3. 在目标仓库根目录启动：`claude --agent pm-orchestrator`，直接提需求。
   - 没有 `project_profile.md` 时，PM 扫描仓库生成画像初稿，逐项请你确认后再开始。
4. 记忆：每个 agent 的项目记忆在 `.claude/agent-memory/{agent}/MEMORY.md`，首次运行自动创建（需开启 Claude Code 的 auto memory，默认开启）。
5. 知识蒸馏：PM 交付后自动调用 kb-curator；也可以随时 `claude --agent kb-curator`。报告在 `project_workspace/_kb_distillation/`。
6. 建议把项目禁用的工具在 settings.json 里设为 deny。
