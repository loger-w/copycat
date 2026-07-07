from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).parent.parent / "harness-push-gate.py"


def run_hook(command: str, tool_name: str = "Bash") -> subprocess.CompletedProcess:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def ask_decision(res: subprocess.CompletedProcess) -> str | None:
    if not res.stdout.strip():
        return None
    return json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_git_push_asks():
    assert ask_decision(run_hook("git push origin main")) == "ask"


def test_git_push_force_asks():
    assert ask_decision(run_hook("git push --force-with-lease origin feat/x")) == "ask"


def test_git_c_flag_push_asks():
    assert ask_decision(run_hook("git -C C:/side-project/neigui push")) == "ask"


def test_gh_pr_merge_asks():
    assert ask_decision(run_hook("gh pr merge 12 --squash")) == "ask"


def test_powershell_tool_covered():
    assert (
        ask_decision(run_hook("git push origin main", tool_name="PowerShell")) == "ask"
    )


def test_git_status_silent():
    assert ask_decision(run_hook("git status")) is None


def test_compound_command_with_push_asks():
    assert ask_decision(run_hook("git add a.py; git commit -m x; git push")) == "ask"


def test_non_shell_tool_silent():
    assert ask_decision(run_hook("git push", tool_name="Read")) is None


def test_malformed_stdin_fail_closed_asks():
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input="{not json",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


@pytest.mark.parametrize("prefix", ["feat", "fix", "mod", "refactor", "perf"])
def test_flow_branch_push_allowed(prefix):
    assert (
        ask_decision(run_hook(f"git push -u origin {prefix}/pr-lifecycle")) == "allow"
    )


def test_flow_branch_push_with_force_asks():
    assert ask_decision(run_hook("git push -u origin feat/x --force")) == "ask"


def test_non_flow_prefix_push_asks():
    assert ask_decision(run_hook("git push -u origin experiment/x")) == "ask"


def test_bare_push_asks():
    assert ask_decision(run_hook("git push")) == "ask"


def test_compound_flow_branch_push_asks():
    assert ask_decision(run_hook("git commit -m x; git push -u origin feat/x")) == "ask"


def test_uppercase_slug_asks():
    assert ask_decision(run_hook("git push -u origin feat/X")) == "ask"


def test_merge_reason_mentions_confirmation_point():
    res = run_hook("gh pr merge 12 --rebase")
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "ask"
    assert "確認點" in out["permissionDecisionReason"]
