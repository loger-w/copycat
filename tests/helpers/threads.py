"""TC4 背景執行緒洩漏偵測(root conftest 守門 fixture 與其生效自檢共用的唯一一份)。

住 `tests/helpers/`(有 `__init__.py`)而不住 `tests/conftest.py`:`tests/` 沒有 `__init__.py`,pytest 預設
prepend importmode 把 conftest 載成頂層模組 `conftest`,測試再 `from tests.conftest import` 會得到**第二個**
module 物件(`tests/capital/test_factory.py` 檔頭那條「經 `import tests.conftest` 拿函式會踩雙重 import」警告
講的正是這件事;pr-222 review F-01 實測兩個 function id)。從這裡 import,兩邊拿到同一顆。
"""

from __future__ import annotations

import threading

#: TC4 source 的兩條背景執行緒(`copycat/live/tc4.py` `_start_listener` / `_start_healer` 用預設命名 ——
#: CPython 3.10+ 是 `Thread-N (<target.__name__>)`)。名字比對而不碰 `_target`:那是 Thread 私有欄。
TC4_THREAD_MARKERS = ("(_listen_loop)", "(_heal_loop)")
#: `close()` / `_stop.set()` 之後 listener 最晚在下一個 RCVTIMEO(1 s)醒來退出、healer 立即;
#: 3 s 容許「有 stop 沒 join」的測試,只抓「根本沒 stop」的。
TC4_THREAD_JOIN_SECS = 3.0


def live_threads() -> set[threading.Thread]:
    """測前快照:活著的 Thread **物件**集合。不記 `ident` —— stdlib 明寫 ident「may be recycled when a
    thread exits and another thread is created」,測前那條剛好死、新 listener 剛好撿到同號就被放行
    (pr-222 review F-02);物件身分不重用,單條測試期間多握幾個 dead Thread 參考無害。"""
    return set(threading.enumerate())


def leaked_tc4_threads(
    before: set[threading.Thread], *, join_secs: float = TC4_THREAD_JOIN_SECS
) -> list[str]:
    """`before`(`live_threads()` 的測前快照)之外、名字帶 TC4 標記、join `join_secs` 後仍活著的執行緒名。"""
    leaked = [
        t
        for t in threading.enumerate()
        if t not in before and any(m in t.name for m in TC4_THREAD_MARKERS)
    ]
    for t in leaked:
        t.join(timeout=join_secs)
    return [t.name for t in leaked if t.is_alive()]
