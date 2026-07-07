#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell) hook: git push / gh pr merge 強制 user 確認。

鐵則 H(push 前列 commit 清單給 user 確認)的機械後盾:permissionDecision
"ask" 無視 session permission mode 強制跳 prompt — 模型忘了列清單,user 也
必然看到 push 指令本身。Fail-closed(design §4):內部錯誤仍回 ask。

2026-07-07 修訂(harness-pr-lifecycle design):流程分支 push(嚴格 fullmatch
單獨指令)放行;gh pr merge 的 ask 框升格為 PR 收尾單一確認點。
"""

from __future__ import annotations

import json
import re
import sys

SHELL_TOOLS = {"Bash", "PowerShell"}

PUSH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bgit\b[^|;&]*\bpush\b"),
]

FLOW_BRANCH_PUSH: re.Pattern[str] = re.compile(
    r"^git\s+push\s+-u\s+origin\s+(?:feat|fix|mod|refactor|perf)/[a-z0-9][a-z0-9-]*$"
)
MERGE_PATTERN: re.Pattern[str] = re.compile(r"\bgh\s+pr\s+merge\b")

ASK_REASON = (
    "鐵則 H:push main / --force / 非流程分支 push 需 user 本人確認。"
    "若尚未列出 origin/<branch>..HEAD commit 清單與目標 branch,先列給 user。"
)
MERGE_ASK_REASON = (
    "PR 收尾單一確認點:試用完功能按 allow 即 merge 到底(rebase merge + 刪分支 + 拉回 main);"
    "deny 則流程停下收 feedback。"
)
ALLOW_REASON = "流程分支 push(PR 收尾自動步驟)— 鐵則 H 2026-07-07 修訂放行。"


def is_push(command: str) -> bool:
    return any(p.search(command) for p in PUSH_PATTERNS)


def emit_decision(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    try:
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        tool_name = payload.get("tool_name") or payload.get("toolName") or ""
        if tool_name not in SHELL_TOOLS:
            return 0
        tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        if not isinstance(command, str) or not command:
            return 0
        if FLOW_BRANCH_PUSH.fullmatch(command.strip()):
            emit_decision("allow", ALLOW_REASON)
        elif MERGE_PATTERN.search(command):
            emit_decision("ask", MERGE_ASK_REASON)
        elif is_push(command):
            emit_decision("ask", ASK_REASON)
        return 0
    except Exception:  # fail-closed(design §4 顯式決策):錯誤時仍要求確認
        emit_decision(
            "ask", "harness-push-gate 內部錯誤(fail-closed)— 仍需 user 確認。"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
