#!/usr/bin/env python3
"""SubagentStop hook for the SDLC agent suite.

1. If an SDLC subagent ends without an <agent_response> block, block once and ask it to add one.
2. Append every <kb_proposals><proposal> to project_workspace/_kb_inbox.jsonl (secrets redacted).
Never fails the run: any unexpected error exits 0.
"""
import datetime
import hashlib
import json
import os
import re
import sys

SDLC = {"requirement-analyst", "system-architect", "software-developer",
        "test-engineer", "devops-engineer", "kb-curator"}
SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:password|passwd|secret|token)\s*[=:]\s*\S+)")


def last_message(data):
    msg = data.get("last_assistant_message")
    if msg:
        return msg
    # Fallback: last assistant text in the subagent transcript.
    path = data.get("agent_transcript_path") or ""
    if not os.path.isfile(path):
        return ""
    text = ""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            content = (row.get("message") or {}).get("content")
            if row.get("type") == "assistant" and isinstance(content, list):
                parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                if any(parts):
                    text = "\n".join(parts)
    return text


def main():
    data = json.load(sys.stdin)
    agent = data.get("agent_type") or ""
    if agent not in SDLC:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    ws = os.path.join(root, "project_workspace")
    os.makedirs(os.path.join(ws, ".hook_state"), exist_ok=True)
    msg = last_message(data)
    agent_id = data.get("agent_id") or hashlib.sha1(msg.encode()).hexdigest()[:12]

    if "<agent_response>" not in msg:
        flag = os.path.join(ws, ".hook_state", f"blocked_{agent_id}")
        if not os.path.exists(flag) and not data.get("stop_hook_active"):
            open(flag, "w").close()
            print(json.dumps({"decision": "block", "reason":
                  "按 shared_protocol.md §E，最终回复的最后必须是完整的 <agent_response> 块"
                  "（含 invocation_id、status、output_files、evidence、notes 中的已读文件清单）。请补上后结束。"}))
        return 0

    inv = re.search(r"<invocation_id>(.*?)</invocation_id>", msg, re.S)
    inv = inv.group(1).strip() if inv else ""
    block = re.search(r"<kb_proposals>(.*?)</kb_proposals>", msg, re.S)
    rows = []
    if block:
        for i, m in enumerate(re.finditer(r"<proposal([^>]*)>(.*?)</proposal>", block.group(1), re.S), 1):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            text = " ".join(m.group(2).split())
            if not text:
                continue
            redacted = SECRET.search(text) is not None
            rows.append({
                "id": f"{inv or agent_id}-{i}",
                "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "agent": agent, "invocation_id": inv,
                "scope": attrs.get("scope", ""), "evidence": SECRET.sub("[REDACTED]", attrs.get("evidence", "")),
                "text": SECRET.sub("[REDACTED]", text), "redacted": redacted,
                "source": "hook", "session_id": data.get("session_id", ""),
            })
    if rows:
        with open(os.path.join(ws, "_kb_inbox.jsonl"), "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # Record which input fields the runtime provides (keys only, for debugging).
    with open(os.path.join(ws, ".hook_state", "last_input_keys.json"), "w") as fh:
        json.dump(sorted(data.keys()), fh)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # never break the agent run because of the hook
        sys.exit(0)
