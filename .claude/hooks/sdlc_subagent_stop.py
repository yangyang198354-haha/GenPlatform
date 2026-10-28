#!/usr/bin/env python3
"""SubagentStop hook for the SDLC agent suite.

1. If an SDLC subagent ends without an <agent_response> block, block once and ask it to add one.
   pm-orchestrator running as a subagent must instead end with a <pm_report> block.
2. Append every <kb_proposals><proposal> to project_workspace/_kb_inbox.jsonl (secrets redacted).
Never fails the run: any unexpected error exits 0.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time

SDLC = {"pm-orchestrator", "requirement-analyst", "system-architect",
        "software-developer", "test-engineer", "devops-engineer", "kb-curator",
        "agent-builder"}
SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:password|passwd|secret|token)\s*[=:]\s*\S+)")


def last_message(data):
    """Return the subagent's final report.

    Newer Claude Code versions let a subagent hand its report back through the
    SubagentHandback tool, so the report is not in last_assistant_message.
    Read the last handback message from the transcript and put it first.
    """
    msg = data.get("last_assistant_message") or ""
    path = data.get("agent_transcript_path") or ""
    handback = text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                content = (row.get("message") or {}).get("content")
                if row.get("type") != "assistant" or not isinstance(content, list):
                    continue
                for c in content:
                    if c.get("type") == "tool_use" and c.get("name") == "SubagentHandback":
                        handback = str((c.get("input") or {}).get("message") or "")
                parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                if any(parts):
                    text = "\n".join(parts)
    return "\n".join(p for p in (handback, msg or text) if p)


def wait_for(data, marker, tries=10, delay=0.5):
    """The transcript line holding the handback can land a moment after the hook
    starts; re-read for up to tries*delay seconds before deciding it is missing."""
    msg = last_message(data)
    for _ in range(tries):
        if marker in msg or not os.path.isfile(data.get("agent_transcript_path") or ""):
            break
        time.sleep(delay)
        msg = last_message(data)
    return msg


def count_handbacks(path):
    n = 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if '"name":"SubagentHandback"' in line.replace(" ", "") and '"type":"assistant"' in line.replace(" ", ""):
                    n += 1
    return n


def note_block(ws, agent_id, data, msg):
    """Write a small diagnostic next to the block flag (no message content)."""
    path = data.get("agent_transcript_path") or ""
    info = {"agent_type": data.get("agent_type"), "transcript": path,
            "transcript_exists": os.path.isfile(path),
            "transcript_bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
            "has_last_assistant_message": bool(data.get("last_assistant_message")),
            "handback_rows": count_handbacks(path),
            "report_chars": len(msg)}
    with open(os.path.join(ws, ".hook_state", f"blocked_{agent_id}.json"), "w") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)


def main():
    data = json.load(sys.stdin)
    agent = data.get("agent_type") or ""
    if agent not in SDLC:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    ws = os.path.join(root, "project_workspace")
    os.makedirs(os.path.join(ws, ".hook_state"), exist_ok=True)
    marker = "<pm_report" if agent == "pm-orchestrator" else "<agent_response>"
    msg = wait_for(data, marker)
    agent_id = data.get("agent_id") or hashlib.sha1(msg.encode()).hexdigest()[:12]

    if agent == "pm-orchestrator":
        # PM writes its own kb proposals to the inbox; only check the report block.
        flag = os.path.join(ws, ".hook_state", f"blocked_{agent_id}")
        if "<pm_report" not in msg and not os.path.exists(flag) and not data.get("stop_hook_active"):
            open(flag, "w").close()
            note_block(ws, agent_id, data, msg)
            print(json.dumps({"decision": "block", "reason":
                  "子代理模式下，pm-orchestrator 的最终回复最后必须是完整的 <pm_report> 块（见 pm-orchestrator §9）；"
                  "有待用户决定的问题时，先把检查点写入 phase_status.md（§5.1）。请补上后结束。"}, ensure_ascii=False))
        return 0

    if "<agent_response>" not in msg:
        flag = os.path.join(ws, ".hook_state", f"blocked_{agent_id}")
        if not os.path.exists(flag) and not data.get("stop_hook_active"):
            open(flag, "w").close()
            note_block(ws, agent_id, data, msg)
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
