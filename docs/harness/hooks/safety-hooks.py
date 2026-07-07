#!/usr/bin/env python3
"""PreToolUse hook: block destructive ops + secrets exposure (customized).

Triggers on Bash + PowerShell(2026-07-07:PowerShell 工具原是繞過面,補齊
matcher 與 PS 專屬 pattern)。Coexists with block-no-verify.py — both run,
either can block.

Blocks:
- rm -rf on dangerous targets (/, ~, $HOME, *, .git, system dirs)
- Bulk git add (`.` / `-A` / `--all` / `*`) — forces selective staging per
  user CLAUDE.md global rule B
- Reading secrets files via cat/head/tail/grep/less/more/xxd/od/strings
- Redirecting output INTO secrets files (overwriting credentials)
- curl|bash / wget|sh (remote code execution)
- chmod 777 / chmod a+rwx

Explicitly allows (covered by negative tests):
- rm -rf node_modules / dist / build / .pytest_cache / __pycache__ (dev hygiene)
- git add <specific path>, git add -u, git add .claude/feat/<slug>/
  (user's /feat workflow)
- cat / head / less of regular source files
- chmod +x / chmod 755
- curl with -o output file (not piped to shell)
"""

from __future__ import annotations

import json
import re
import sys

# ---------------------------------------------------------------------------
# Target patterns shared by multiple rules.
# ---------------------------------------------------------------------------
SECRET_FILE = (
    r"(?:\.env(?:\.\w+)?|\.envrc|credentials(?:\.json)?|secrets(?:\.\w+)?|"
    r"\.npmrc|id_[rd]sa|[\w./\\-]+\.pem|[\w./\\-]+\.p12|[\w./\\-]+\.key|"
    r"\.aws/credentials)"
)

# Paths where `rm -rf` would be catastrophic.
DANGEROUS_RM_TARGET = re.compile(
    r"(?:^|\s)(?:"
    r"/(?:\s|$)|"  # rm -rf /
    r"~(?:/[^\s]*)?(?:\s|$)|"  # rm -rf ~  or  rm -rf ~/x
    r"\$HOME(?:/[^\s]*)?(?:\s|$)|"  # rm -rf $HOME
    r"\*(?:\s|$)|"  # rm -rf *
    r"/\*(?:\s|$)|"  # rm -rf /*
    r"\.\.(?:/[^\s]*)?(?:\s|$)|"  # rm -rf ../  (escapes parent)
    r"\.git(?:/(?!info|hooks/)[^\s]*)?(?:\s|$)|"  # rm -rf .git (allow .git/info, .git/hooks handled by block-no-verify)
    r"/(?:usr|etc|var|bin|sbin|boot|lib|opt|root|home|System|Library|Windows|Program Files)(?:/[^\s]*)?(?:\s|$)|"
    r"[A-Za-z]:[/\\](?:Windows|Users|Program Files)(?:[/\\][^\s]*)?(?:\s|$)"
    r")"
)

# `rm` invocation with both -r and -f flags (or combined -rf/-fr/-Rf).
RM_RF = re.compile(
    r"\brm\s+(?:"
    r"[^|;&]*?-[A-Za-z]*(?:rf|fr|rF|Rf|fR|Fr)[A-Za-z]*\b|"  # combined: -rf, -fr, etc.
    r"[^|;&]*?-[A-Za-z]*[rR][A-Za-z]*\s+[^|;&]*?-[A-Za-z]*[fF][A-Za-z]*\b|"  # separated -r ... -f
    r"[^|;&]*?-[A-Za-z]*[fF][A-Za-z]*\s+[^|;&]*?-[A-Za-z]*[rR][A-Za-z]*\b|"  # separated -f ... -r
    r"[^|;&]*?--recursive\b[^|;&]*?--force\b|"
    r"[^|;&]*?--force\b[^|;&]*?--recursive\b"
    r")"
)

REGEX_BLOCKS: list[tuple[re.Pattern[str], str]] = [
    # --- Bulk git add (force selective staging) ---
    (
        re.compile(
            r"\bgit\s+add\s+(?:-[A-Za-z]+\s+)*(?:\.(?:/)?(?:\s|$)|\*(?:\s|$)|-A\b|--all\b)"
        ),
        "bulk git add (. / -A / --all / *) — list specific files instead "
        "(may include .env / large binaries / unintended changes)",
    ),
    # --- Reading secrets files (leaks to conversation context) ---
    (
        re.compile(
            rf"\b(?:cat|head|tail|less|more|view|bat|xxd|od|hexdump|strings|hd)\s+"
            rf"(?:-[A-Za-z0-9_=-]+\s+)*[^|;&]*?{SECRET_FILE}\b"
        ),
        "reading a secrets file leaks credentials into the conversation context",
    ),
    (
        re.compile(rf"\bgrep\b[^|;&]*?{SECRET_FILE}\b"),
        "grep on secrets file leaks matching lines to conversation",
    ),
    # --- Redirecting INTO secrets files (overwrites credentials) ---
    (
        re.compile(rf">{{1,2}}\s*(?:[^\s|;&]+[/\\])?{SECRET_FILE}\b"),
        "redirecting output into secrets file may overwrite credentials",
    ),
    (
        re.compile(rf"\btee\s+(?:-a\s+)?(?:[^\s|;&]+[/\\])?{SECRET_FILE}\b"),
        "tee into secrets file may overwrite credentials",
    ),
    # --- curl | sh / wget | bash etc. (remote code execution) ---
    (
        re.compile(
            r"\b(?:curl|wget|fetch)\b[^|;&]*\|\s*"
            r"(?:bash|sh|zsh|fish|dash|ksh|python\d*|ruby|node|deno|perl)\b"
        ),
        "piping curl/wget output directly to a shell or interpreter is remote code execution",
    ),
    # --- chmod 777 / a+rwx (world-writable) ---
    (
        re.compile(r"\bchmod\s+(?:-[A-Za-z]+\s+)*(?:777|a\+rwx)\b"),
        "chmod 777 / a+rwx makes file world-writable — security risk",
    ),
    # --- PowerShell: reading secrets (Get-Content / gc / type / Select-String) ---
    # PS cmdlet 大小寫不敏感;`type` 只在後面直接接 secrets 檔時才攔。
    (
        re.compile(
            rf"(?i)\b(?:Get-Content|gc|type|Select-String|sls)\s+"
            rf"(?:-\w+(?::\S+)?\s+)*[^|;&]*?{SECRET_FILE}\b"
        ),
        "reading a secrets file (PowerShell) leaks credentials into the conversation context",
    ),
    # --- PowerShell: writing into secrets (Set-Content / Add-Content / Out-File) ---
    (
        re.compile(
            rf"(?i)\b(?:Set-Content|Add-Content|Out-File|sc|ac)\s+"
            rf"(?:-\w+(?::\S+)?\s+)*(?:[^\s|;&]+[/\\])?{SECRET_FILE}\b"
        ),
        "writing into secrets file (PowerShell) may overwrite credentials",
    ),
]


def detect_violation(command: str) -> tuple[str, str] | None:
    """Return (matched_pattern, reason) for any violation, else None."""
    # rm -rf on dangerous target requires both conditions
    if RM_RF.search(command) and DANGEROUS_RM_TARGET.search(command):
        return (
            "rm -rf <dangerous-path>",
            "rm -rf on system root / home / .git / system directories",
        )
    for pattern, reason in REGEX_BLOCKS:
        if pattern.search(command):
            return pattern.pattern, reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"safety-hooks: malformed stdin JSON: {e}", file=sys.stderr)
        return 0

    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    if tool_name not in ("Bash", "PowerShell"):
        return 0

    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        return 0

    command = tool_input.get("command", "")
    if not isinstance(command, str) or not command:
        return 0

    hit = detect_violation(command)
    if hit is None:
        return 0

    matched, reason = hit
    print(
        "BLOCKED by ~/.claude/hooks/safety-hooks.py\n"
        f"Reason : {reason}\n"
        f"Matched: {matched}\n"
        f"Command: {command[:200]}{'...' if len(command) > 200 else ''}\n"
        "If you genuinely need this destructive op, ask the user explicitly. "
        "For secrets, prefer reading values from env (e.g. `os.environ[...]`) "
        "instead of dumping the .env contents to context.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
