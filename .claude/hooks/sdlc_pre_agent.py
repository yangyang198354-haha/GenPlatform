#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent) for the SDLC agent suite.

Claude Code creates a subagent's project memory directory relative to the current
working directory at spawn time. If the main session has `cd`-ed into a
subdirectory, the subagent gets an empty memory in the wrong place. This hook
denies spawning an SDLC subagent unless the current directory is the repo root.
Never fails the run: any unexpected error allows the call.
"""
import json
import os
import sys

SDLC = {"requirement-analyst", "system-architect", "software-developer",
        "test-engineer", "devops-engineer", "kb-curator",
        "agent-builder"}


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Agent":
        return 0
    if (data.get("tool_input") or {}).get("subagent_type") not in SDLC:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    cwd = data.get("cwd")
    if not root or not cwd or os.path.realpath(root) == os.path.realpath(cwd):
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason":
            f"当前目录 {cwd} 不是仓库根。子代理的项目记忆按当前目录定位，"
            f"请先在 Bash 中执行 cd '{root}'，再重新调用该子代理（pm-orchestrator 规则 13）。",
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
