#!/usr/bin/env python3
"""Stop hook: 回合末審計進行中 /feat 的機械義務(design §2.2)。

- state.json 落後最新 commit(且該 commit 未含 state.json)→ block 一次令回寫。
- Phase 8.5 進行中且收件匣無本 slug entry → systemMessage 提醒(不 block,
  「無瑕疵」是合法結果,真偽不可機驗)。
- stop_hook_active 防無限迴圈;fail-open(design §4)。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness_lib  # noqa: E402


def _inbox_path() -> Path:
    override = os.environ.get("HARNESS_INBOX")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "feat-improvements.md"


def main() -> int:
    harness_lib.force_utf8_stdio()
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0
    cwd = payload.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd:
        return 0
    try:
        found = harness_lib.find_active_feature(cwd)
        if found is None:
            return 0
        state_path, state = found

        if harness_lib.state_is_lagging(cwd, state_path, state):
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": (
                            f"[harness-stop-audit] {state_path} 落後最新 commit。"
                            "結束回合前先回寫 current_phase / completed_phases / last_updated。"
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        phase = state.get("current_phase")
        completed = state.get("completed_phases") or []
        slug = state.get("slug") or ""
        if phase == 8.5 and 8.5 not in completed and slug:
            try:
                inbox_text = _inbox_path().read_text(encoding="utf-8")
            except OSError:
                inbox_text = ""
            if slug not in inbox_text:
                print(
                    json.dumps(
                        {
                            "systemMessage": (
                                f"[harness-stop-audit] {slug} 在 Phase 8.5 但"
                                "feat-improvements.md 無本輪 entry — 有瑕疵補 entry,"
                                f"確實無瑕疵補「(feature: {slug})無瑕疵」標記。"
                            ),
                        },
                        ensure_ascii=False,
                    )
                )
        return 0
    except Exception as e:  # fail-open(design §4 顯式決策):降級 + 印原因
        print(f"harness-stop-audit: internal error (fail-open): {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
