#!/usr/bin/env python3
"""PreToolUse hook: block git/hook bypass flags (hardened).

Triggers on Bash tool calls. Exits 2 (with stderr fed back to Claude) when
the command attempts to skip pre-commit / pre-push hooks, commit signing,
the pre-commit framework, or any of the runtime tricks identified by the
adversarial review (var concatenation, printf reconstruction, brace
expansion, plumbing escape, server-side gh api, etc.). Exits 0 otherwise.

Enforces CLAUDE.md global rule E (禁止繞過手段) at process level.
"""

from __future__ import annotations

import json
import re
import sys

# ---------------------------------------------------------------------------
# Literal substring blocks (fastest path).
# ---------------------------------------------------------------------------
SUBSTRING_BLOCKS: list[tuple[str, str]] = [
    ("--no-verify", "--no-verify bypasses pre-commit / pre-push hooks"),
    ("--no-gpg-sign", "--no-gpg-sign bypasses commit signing"),
    ("--skip-hooks", "--skip-hooks bypasses the pre-commit framework"),
    ("commit.gpgsign=false", "-c commit.gpgsign=false bypasses commit signing"),
]

# ---------------------------------------------------------------------------
# Regex blocks (need context / wildcards).
# ---------------------------------------------------------------------------
REGEX_BLOCKS: list[tuple[re.Pattern[str], str]] = [
    # --- core.hooksPath: any value, case-insensitive, both `=` and space form ---
    (
        re.compile(r"(?i)core\.hooksPath\s*[=\s]\s*\S+"),
        "core.hooksPath override (any value) disables git hooks",
    ),
    (
        re.compile(r"(?i)\bgit\s+config\s+(?:--\w+\s+)?core\.hooksPath\b"),
        "git config core.hooksPath persists hook disabling",
    ),
    # --- Plumbing escape: commit-tree + update-ref skip all porcelain hooks ---
    (
        re.compile(r"\bgit\s+commit-tree\b"),
        "git commit-tree (plumbing) bypasses pre-commit / commit-msg hooks",
    ),
    (
        re.compile(r"\bgit\s+update-ref\s+(?:HEAD\b|refs/heads/)"),
        "git update-ref HEAD/refs/heads/* bypasses porcelain hooks",
    ),
    # --- GIT_CONFIG_* env-var injection ---
    (
        re.compile(r"\bGIT_CONFIG_(?:COUNT|KEY_\d+|VALUE_\d+|PARAMETERS)\s*="),
        "GIT_CONFIG_* env vars inject config and can disable hooks",
    ),
    # --- Hook-runner disable env vars ---
    (
        re.compile(r"\bHUSKY\s*=\s*['\"]?(?:0|false|no|off)['\"]?\b"),
        "HUSKY=0/false/no/off disables husky hooks",
    ),
    (
        re.compile(
            r"\b(?:HUSKY_SKIP_HOOKS|HUSKY_SKIP_INSTALL|PRE_COMMIT_ALLOW_NO_CONFIG|"
            r"LEFTHOOK|LEFTHOOK_QUIET)\s*=\s*\S+"
        ),
        "hook-runner disable env var present",
    ),
    # --- git commit -n... (any short-flag bundle starting with -n) ---
    (
        re.compile(r"\bgit\s+commit\b[^&|;#]*?(?<![\w-])-n[A-Za-z]*\b"),
        "git commit -n... (combined short flag) is short for --no-verify",
    ),
    # --- .git/hooks/ write/mutate operations (reads like `cat`/`ls` are allowed) ---
    (
        re.compile(
            r"(?:\b(?:chmod|rm|mv|cp|tee|truncate|ln)\b[^|;&]*\.git/hooks/|"
            r"(?:>{1,2})\s*\.git/hooks/)"
        ),
        ".git/hooks/* write/chmod/rm/mv/redirect is a hook-bypass attempt",
    ),
    # --- gh api server-side commit / refs / contents (skips ALL local hooks) ---
    (
        re.compile(
            r"\bgh\s+api\b[^|;&]*?/repos/[^/\s]+/[^/\s]+/"
            r"(?:contents/|git/(?:refs|commits|blobs|trees))"
        ),
        "gh api server-side commit/ref write skips ALL local pre-commit/pre-push hooks",
    ),
    # --- Shell-time flag reconstruction (defense-in-depth, heuristic) ---
    (
        re.compile(r"--n[A-Za-z]*\{[^}]*\}[A-Za-z-]*verify"),
        "brace expansion reconstructs --no-verify (e.g. --no{,}-verify)",
    ),
    (
        re.compile(r"\bprintf\b[^|;&]*['\"][^'\"]*--no[^'\"]*verify[^'\"]*['\"]"),
        "printf format assembles --no-verify",
    ),
    (
        re.compile(r"\bprintf\b[^|;&]*['\"][^'\"]*--no%s[^'\"]*['\"]"),
        "printf with --no%s template likely yields --no-verify",
    ),
    (
        re.compile(r"\$'[^']*(?:\\x2d|--?no)[^']*verify[^']*'"),
        "ANSI-C $'...' encoding likely smuggles --no-verify",
    ),
    # --- libgit2-family (P2 — soft). Allow `;` inside python -c "..." strings. ---
    (
        re.compile(
            r"\b(?:pygit2|libgit2|nodegit|isomorphic-git|GitPython)\b.{0,200}\b"
            r"(?:create_commit|commit_create|index\.commit|refs\.create|write_tree)\b"
        ),
        "libgit2-family API commit/ref write skips porcelain hooks",
    ),
]

# ---------------------------------------------------------------------------
# AND blocks: both A and B must appear in the same command.
# Avoids false-positives on isolated patterns that are only dangerous together.
# ---------------------------------------------------------------------------
AND_BLOCKS: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    # SKIP=<id> indirection — subshell, env, or export combined with git commit
    (
        re.compile(r"\b(?:env\s+|export\s+)?SKIP\s*=\s*\S+"),
        re.compile(r"\bgit\s+commit\b"),
        "SKIP=... combined with git commit bypasses the pre-commit framework",
    ),
    # Shell var concatenation: VAR=--no near git commit
    (
        re.compile(r"[A-Za-z_]\w*\s*=\s*['\"]?--?no\b"),
        re.compile(r"\bgit\s+commit\b"),
        "shell var assigned --no near git commit — likely reconstructing --no-verify",
    ),
    # Shell var concatenation: VAR=-verify near git commit
    (
        re.compile(r"[A-Za-z_]\w*\s*=\s*['\"]?-verify\b"),
        re.compile(r"\bgit\s+commit\b"),
        "shell var assigned -verify near git commit — likely reconstructing --no-verify",
    ),
    # printf with "no" and "verify" as args (e.g. printf '--%s-%s' no verify),
    # combined with git commit in same command — highly suspicious flag assembly.
    (
        re.compile(
            r"\bprintf\b[^|;&]*?(?:\bno\b[^|;&]*?\bverify\b|\bverify\b[^|;&]*?\bno\b)"
        ),
        re.compile(r"\bgit\s+commit\b"),
        "printf assembling 'no' and 'verify' tokens combined with git commit is reconstructing --no-verify",
    ),
]


def _normalize(command: str) -> str:
    """Strip empty quote pairs that split a flag (e.g. --no""-verify → --no-verify)."""
    return re.sub(r"['\"]{2}", "", command)


def detect_bypass(command: str) -> tuple[str, str] | None:
    """Return (matched_pattern, reason) if the command contains a bypass; else None."""
    norm = _normalize(command)
    for needle, reason in SUBSTRING_BLOCKS:
        if needle in command or needle in norm:
            return needle, reason
    for pattern, reason in REGEX_BLOCKS:
        if pattern.search(command) or pattern.search(norm):
            return pattern.pattern, reason
    for a_pat, b_pat, reason in AND_BLOCKS:
        if (a_pat.search(command) or a_pat.search(norm)) and (
            b_pat.search(command) or b_pat.search(norm)
        ):
            return f"{a_pat.pattern} AND {b_pat.pattern}", reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        # Don't block on parse failure — log and pass through.
        print(f"block-no-verify: malformed stdin JSON: {e}", file=sys.stderr)
        return 0

    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    if tool_name != "Bash":
        return 0

    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        return 0

    command = tool_input.get("command", "")
    if not isinstance(command, str) or not command:
        return 0

    hit = detect_bypass(command)
    if hit is None:
        return 0

    matched, reason = hit
    print(
        "BLOCKED by ~/.claude/hooks/block-no-verify.py (CLAUDE.md global rule E)\n"
        f"Reason : {reason}\n"
        f"Matched: {matched}\n"
        f"Command: {command[:200]}{'...' if len(command) > 200 else ''}\n"
        "Fix the underlying issue (failing hook / bad commit msg / signing problem) "
        "instead of bypassing. If the user explicitly authorized this bypass in the "
        "current conversation, ask them to disable the hook for this session.",
        file=sys.stderr,
    )
    return 2  # Exit 2 = hard block + send stderr back to Claude


if __name__ == "__main__":
    sys.exit(main())
