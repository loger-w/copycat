from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "block-no-verify.py"


def run_hook(command: str, tool_name: str = "Bash") -> subprocess.CompletedProcess:
    payload = {"tool_name": tool_name, "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# --- core.hooksPath:唯讀查詢放行、設值 / unset 攔下 ---


def test_hookspath_readonly_query_allowed():
    # 2026-07-07 契約掃描實測誤攔:查詢不會 disable hooks
    assert run_hook("git config core.hooksPath").returncode == 0


def test_hookspath_get_allowed():
    assert run_hook("git config --get core.hooksPath").returncode == 0


def test_hookspath_readonly_in_compound_command_allowed():
    assert (
        run_hook('git config core.hooksPath; echo "---"; cat foo.json').returncode == 0
    )


def test_hookspath_set_value_blocked():
    assert run_hook("git config core.hooksPath /tmp/empty").returncode == 2


def test_hookspath_set_equals_form_blocked():
    assert run_hook("git -c core.hooksPath=/dev/null commit -m x").returncode == 2


def test_hookspath_unset_blocked():
    # unset 會拆掉 repo 的 pre-push 防線(core.hooksPath 指向 scripts/git-hooks)
    assert run_hook("git config --unset core.hooksPath").returncode == 2


def test_hookspath_unset_all_blocked():
    assert run_hook("git config --unset-all core.hooksPath").returncode == 2


# --- PowerShell 工具面(2026-07-06 backlog:matcher 只有 Bash 是繞過面) ---


def test_powershell_no_verify_blocked():
    assert (
        run_hook("git commit --no-verify -m x", tool_name="PowerShell").returncode == 2
    )


def test_powershell_hookspath_set_blocked():
    assert (
        run_hook("git config core.hooksPath C:/tmp", tool_name="PowerShell").returncode
        == 2
    )


def test_powershell_plain_commit_allowed():
    assert run_hook('git commit -m "feat: x"', tool_name="PowerShell").returncode == 0


def test_other_tool_ignored():
    assert run_hook("git commit --no-verify -m x", tool_name="Write").returncode == 0


# --- 既有行為不回歸(抽樣) ---


def test_no_verify_blocked():
    assert run_hook("git commit --no-verify -m x").returncode == 2


def test_plain_commit_allowed():
    assert run_hook('git commit -m "feat: x"').returncode == 0
