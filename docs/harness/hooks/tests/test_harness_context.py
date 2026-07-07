from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "harness-context.py"

sys.path.insert(0, str(Path(__file__).parent))
from test_harness_lib import make_state, write_state  # noqa: E402


def run_hook(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_no_active_feature_silent(tmp_path):
    res = run_hook({"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path)})
    assert res.returncode == 0
    assert res.stdout.strip() == ""


def test_active_feature_injects_slug_phase_gate(tmp_path):
    write_state(tmp_path, "demo-feature", make_state(current_phase=5))
    res = run_hook({"hook_event_name": "SessionStart", "cwd": str(tmp_path)})
    assert res.returncode == 0
    assert "demo-feature" in res.stdout
    assert "phase:5" in res.stdout.replace(" ", "")
    assert "auto-verify" in res.stdout  # phase 5 的 gate 描述


def test_malformed_stdin_fail_open(tmp_path):
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input="{not json",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 0
    assert res.stdout.strip() == ""
