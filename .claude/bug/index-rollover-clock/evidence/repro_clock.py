"""Bug 2 重現:把 index_engine 模組的 _dt 換成固定時刻的 shim,跑 test_rollover_two_phase。

用法:python repro_clock.py <hour>   e.g. 0 -> 00:00(< 08:30 門檻)、10 -> 10:00
退出碼 = pytest 退出碼(0 綠 / 1 紅)。
"""

import datetime as _real
import sys
from pathlib import Path

# 腳本直跑時 sys.path[0] = 腳本目錄 → `import copycat` 會被 venv 的 editable install
# 解析到主 tree(不是這個 worktree)。必須顯式把 repo root 插到最前面。
_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))

import copycat.server.index_engine as m  # noqa: E402


def _make_shim(hour: int):
    fixed = _real.datetime(2026, 7, 30, hour, 0, 0)

    class _FakeDateTime(_real.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001 - 只需覆寫測試用到的簽名
            return fixed

    class _Shim:
        date = _real.date
        time = _real.time
        datetime = _FakeDateTime
        timedelta = _real.timedelta

    return _Shim


hour = int(sys.argv[1])
m._dt = _make_shim(hour)  # type: ignore[assignment]
print(f"[repro] index_engine._dt.datetime.now() -> {m._dt.datetime.now()}")

import pytest  # noqa: E402

sys.exit(
    pytest.main(["tests/server/test_index_engine.py::test_rollover_two_phase", "-q", "--no-header"])
)
