#!/usr/bin/env python3
"""PreToolUse hook (matcher: WebFetch|WebSearch) for the SDLC agent suite.

agent-builder may only fetch the Claude Code official docs pages listed below,
and may not use WebSearch. Other agents are not affected.
Hook input carries `agent_type` when the call comes from a subagent or from a
session started with `--agent`. Never fails the run: unexpected errors exit 0.
"""
import json
import sys
from urllib.parse import urlsplit

GUARDED = {"agent-builder"}
ALLOWED_PAGES = {"sub-agents", "hooks", "settings", "permissions",
                 "memory", "skills", "mcp", "cli-reference"}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


def main():
    data = json.load(sys.stdin)
    if data.get("agent_type") not in GUARDED:
        return
    tool = data.get("tool_name")
    if tool == "WebSearch":
        deny("agent-builder 不允许使用 WebSearch；只能用 WebFetch 访问 Claude Code 官方文档白名单页。")
    if tool != "WebFetch":
        return
    url = str((data.get("tool_input") or {}).get("url", ""))
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    page = path[len("/docs/en/"):] if path.startswith("/docs/en/") else ""
    ok = (parts.scheme == "https" and parts.hostname == "code.claude.com"
          and not parts.query and page in ALLOWED_PAGES)
    if not ok:
        allowed = "、".join("https://code.claude.com/docs/en/" + p for p in sorted(ALLOWED_PAGES))
        deny("agent-builder 只能访问以下官方文档页（不带查询参数）：" + allowed
             + "。该项判定请标【推断】，不扣分。")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
