#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit hook: inject active /feat state into context.

弱模型長對話後會遺忘流程位置 — 每回合重新錨定(protocol-model-dependency 的
soft reminder 機制)。無進行中 feature 時零輸出,不污染一般 session。
stdout(exit 0)在兩種 event 都會被加進 context。
Fail-open(design §4):內部錯誤 → stderr 警告 + exit 0。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness_lib  # noqa: E402


def main() -> int:
    harness_lib.force_utf8_stdio()
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    cwd = payload.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd:
        return 0
    try:
        found = harness_lib.find_active_feature(cwd)
        if found is None:
            return 0
        state_path, state = found
        phase = state.get("current_phase")
        try:
            gate = harness_lib.gate_for_phase(float(phase))
        except (TypeError, ValueError):
            gate = harness_lib.gate_for_phase(-999.0)
        lines = [
            f"[harness] 進行中 /feat:{state.get('slug')}(branch {state.get('branch')})",
            f"目前 phase:{phase} — 此 phase 的 gate:{gate}",
            f"state.json 上次回寫:{state.get('last_updated')}",
        ]
        if harness_lib.state_is_lagging(cwd, state_path, state):
            lines.append("⚠ state.json 已落後最新 commit — 先回寫再繼續其他工作。")
        print("\n".join(lines))
        return 0
    except Exception as e:  # fail-open(design §4 顯式決策):降級 + 印原因
        print(f"harness-context: internal error (fail-open): {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
