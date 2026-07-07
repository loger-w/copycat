from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "harness-stop-audit.py"

sys.path.insert(0, str(Path(__file__).parent))
from test_harness_lib import git, make_repo, make_state, write_state  # noqa: E402


def run_hook(payload: dict, inbox: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if inbox is not None:
        env["HARNESS_INBOX"] = str(inbox)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_stop_hook_active_passes_through(tmp_path):
    res = run_hook({"stop_hook_active": True, "cwd": str(tmp_path)})
    assert res.returncode == 0
    assert res.stdout.strip() == ""


def test_no_active_feature_silent(tmp_path):
    res = run_hook({"stop_hook_active": False, "cwd": str(tmp_path)})
    assert res.returncode == 0
    assert res.stdout.strip() == ""


def test_lagging_state_blocks(tmp_path):
    repo = make_repo(tmp_path)
    write_state(
        repo, "demo-feature", make_state(last_updated="2020-01-01T00:00:00+08:00")
    )
    (repo / "code.py").write_text("x = 1")
    git(repo, "add", "code.py")
    git(repo, "commit", "-m", "feat: code only")
    res = run_hook({"stop_hook_active": False, "cwd": str(repo)})
    out = json.loads(res.stdout)
    assert out["decision"] == "block"
    assert "state.json" in out["reason"]


def test_phase85_without_inbox_entry_system_message(tmp_path):
    inbox = tmp_path / "inbox.md"
    inbox.write_text("# empty\n", encoding="utf-8")
    write_state(
        tmp_path,
        "demo-feature",
        make_state(
            current_phase=8.5,
            completed_phases=[-1, 0, 1, 2, 3, 4, 5, 6, 7, 8],
            last_updated="2099-01-01T00:00:00+08:00",
        ),
    )
    res = run_hook({"stop_hook_active": False, "cwd": str(tmp_path)}, inbox=inbox)
    out = json.loads(res.stdout)
    assert "systemMessage" in out
    assert "demo-feature" in out["systemMessage"]


def test_phase85_with_inbox_entry_silent(tmp_path):
    inbox = tmp_path / "inbox.md"
    inbox.write_text(
        "### 2026-07-06 (feature: demo-feature)\n- 無瑕疵\n", encoding="utf-8"
    )
    write_state(
        tmp_path,
        "demo-feature",
        make_state(
            current_phase=8.5,
            completed_phases=[-1, 0, 1, 2, 3, 4, 5, 6, 7, 8],
            last_updated="2099-01-01T00:00:00+08:00",
        ),
    )
    res = run_hook({"stop_hook_active": False, "cwd": str(tmp_path)}, inbox=inbox)
    assert res.stdout.strip() == ""
