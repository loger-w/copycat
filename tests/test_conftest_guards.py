"""root conftest 守門 fixture 的生效自檢(two-axis review F-01,refactor/w3-b2)。

`_no_leaked_tc4_threads` 靠執行緒**名字**認 TC4 的 listener / healer;唯一洩漏源修好後它從此恆綠,
名字比對一旦失效(`tc4.py` 給 Thread 加了 `name=`、或改用 `functools.partial` 當 target)守門會
**靜默**轉 vacuous,零訊號。這裡兩條各釘一端:偵測邏輯本身(正向案)與 `tc4.py` 的命名前提(字面 parity)。
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from tests.conftest import leaked_tc4_threads

_TC4_SRC = Path(__file__).resolve().parent.parent / "copycat" / "live" / "tc4.py"


def test_guard_names_a_live_thread_with_tc4_marker_and_clears_once_it_exits() -> None:
    """正向案:起一條名字帶 `(_listen_loop)` 的執行緒卡在 Event 上 → 守門必須點名;放行後必須清空。

    join 上限縮到 50 ms(預設 3 s 是給真 listener 的 RCVTIMEO 尾巴),自檢不等 3 秒。
    """
    before = {t.ident for t in threading.enumerate()}
    release = threading.Event()
    t = threading.Thread(target=release.wait, name="Thread-999 (_listen_loop)", daemon=True)
    t.start()
    try:
        assert leaked_tc4_threads(before, join_secs=0.05) == ["Thread-999 (_listen_loop)"]
    finally:
        release.set()
        t.join(timeout=3.0)
    assert leaked_tc4_threads(before, join_secs=0.05) == []


def test_guard_ignores_threads_alive_before_the_test_and_unmarked_names() -> None:
    """前一條測試留下的執行緒(已在 `before`)與沒帶 TC4 標記的執行緒都不點名。"""
    release = threading.Event()
    older = threading.Thread(target=release.wait, name="Thread-998 (_listen_loop)", daemon=True)
    older.start()
    before = {t.ident for t in threading.enumerate()}  # older 已在快照內
    plain = threading.Thread(target=release.wait, name="Thread-997 (worker)", daemon=True)
    plain.start()
    try:
        assert leaked_tc4_threads(before, join_secs=0.05) == []
    finally:
        release.set()
        older.join(timeout=3.0)
        plain.join(timeout=3.0)


def test_tc4_threads_keep_the_default_name_the_guard_matches_on() -> None:
    """字面 parity:`tc4.py` 起 listener / healer 的兩行不帶 `name=`,CPython 3.10+ 預設命名
    `Thread-N (<target.__name__>)` 才會含 `(_listen_loop)` / `(_heal_loop)`;target 也必須是
    裸的 bound method(`functools.partial` 的 `__name__` 不是 loop 名)。"""
    src = _TC4_SRC.read_text(encoding="utf-8")
    starts = re.findall(r"threading\.Thread\((.*?)\)\n", src)
    loops = [s for s in starts if "_listen_loop" in s or "_heal_loop" in s]
    assert len(loops) == 2, loops
    for args in loops:
        assert "name=" not in args, args
        assert re.search(r"target=self\._(listen|heal)_loop\b", args), args
