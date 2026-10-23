# 知识库（规则见 shared_protocol.md §M）

三层：
- `generic/{agent}.md` —— **通用经验**，与项目无关，随套件分发；agent 开工时必读。只有 kb-curator 在用户确认后写入。
- `.claude/agent-memory/{agent}/MEMORY.md` —— **项目记忆**（agent frontmatter `memory: project`），启动时自动注入。"已验证"区由 kb-curator 维护，agent 只能追加"待验证"区。
- `project_workspace/_kb_inbox.jsonl` —— **经验收件箱**，SubagentStop hook（`.claude/hooks/sdlc_subagent_stop.py`）自动收集子代理的 `<kb_proposals>`。

蒸馏：PM 交付后调用 `kb-curator`（PHASE_12），或手动运行 `claude --agent kb-curator`。报告与日志在 `project_workspace/_kb_distillation/`。

项目事实（目录、命令、环境、禁用项）放 `../project_profile.md`，不放知识库或记忆。

