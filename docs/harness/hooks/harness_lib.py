#!/usr/bin/env python3
"""Shared helpers for harness enforcement hooks (context / stop-audit).

Implements the "active feature" semantics of
docs/specs/harness-enforcement/design.md (neigui repo) §2.1:
- active = paused is null AND final_merge_sha absent AND 8.5 not in completed_phases
- multiple actives -> latest last_updated
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def force_utf8_stdio() -> None:
    """Windows 上 pipe 的預設編碼是 locale(cp950)— hook 輸出繁中必須強制 UTF-8。"""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

PHASE_GATES: list[tuple[float, str]] = [
    (-1.0, "工作區隔離(branch + artifact 目錄 + state.json 初始化)"),
    (0.0, "Brainstorm:SC 可驗證性 gate(SC-N 編號 + 驗證方式 + 單位/量法)"),
    (1.0, "設計 spec review:無 P0 且 P1≤2(max 3 輪)"),
    (2.0, "實作 spec(預設 condensed PLAN.md;L 級高風險檔才 per_file)"),
    (3.0, "TDD:[red] 先於 [green],commit 帶 tag"),
    (4.0, "自評 code-review:雙焦點 + 單輪退場條件"),
    (5.0, "自動化驗證:auto-verify 全綠"),
    (6.0, "真實環境驗證:依 feature shape 分流"),
    (7.0, "回頭核 goal:SC 證據表逐條對,無 N/A"),
    (8.0, "收尾:TDD 序列 git log 機驗 + artifact commit"),
    (8.5, "沉澱:知識分流 + GC + 收件匣回報"),
]


def gate_for_phase(phase: float) -> str:
    for p, gate in PHASE_GATES:
        if p == phase:
            return gate
    return "(未知 phase,查 ~/.claude/commands/feat.md)"


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def load_state(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_active(state: dict) -> bool:
    if state.get("paused") is not None:
        return False
    if state.get("final_merge_sha"):
        return False
    if state.get("archived"):  # 已出貨但 state 未收尾的歷史欠帳,盤點後標記封存
        return False
    completed = state.get("completed_phases") or []
    return 8.5 not in completed


def find_active_feature(cwd: str) -> tuple[Path, dict] | None:
    feat_dir = Path(cwd) / ".claude" / "feat"
    if not feat_dir.is_dir():
        return None
    candidates: list[tuple[datetime, Path, dict]] = []
    for state_path in feat_dir.glob("*/state.json"):
        state = load_state(state_path)
        if state is None or not is_active(state):
            continue
        ts = _parse_ts(state.get("last_updated")) or datetime.min
        candidates.append((_aware(ts), state_path, state))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _, state_path, state = candidates[-1]
    return state_path, state


def _git(repo: Path, *args: str) -> str | None:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def _repo_root(cwd: str) -> Path | None:
    out = _git(Path(cwd), "rev-parse", "--show-toplevel")
    return Path(out) if out else None


def _head_commit_time(repo: Path) -> datetime | None:
    return _parse_ts(_git(repo, "log", "-1", "--format=%cI"))


def _head_touched(repo: Path, rel_posix: str) -> bool:
    # `git show`(對 root commit 也有效;diff-tree 不帶 --root 時對 root commit 輸出空)
    out = _git(repo, "show", "--name-only", "--format=", "HEAD")
    if out is None:
        return False
    return rel_posix in out.splitlines()


def state_is_lagging(cwd: str, state_path: Path, state: dict) -> bool:
    """HEAD 晚於 last_updated 且最近 commit 未含此 state.json(design §2.2)。"""
    root = _repo_root(cwd)
    if root is None:
        return False
    head_ts = _head_commit_time(root)
    last = _parse_ts(state.get("last_updated"))
    if head_ts is None or last is None:
        return False
    if _aware(head_ts) <= _aware(last):
        return False
    try:
        rel = state_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return not _head_touched(root, rel)
