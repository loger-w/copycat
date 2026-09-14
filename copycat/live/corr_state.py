"""滾動相關係數狀態機(零 IO;SC-1/3/4;design §5)。

每秒一筆取樣 → 多窗滾動 Pearson。設計要點:

- **增量維護,不整批重算**(perf #244,2026-09-15 改寫):舊版每秒把 1800 筆中價重掃一次
  重建配對報酬、再對每窗 `statistics.correlation`,event loop 每秒同步停 9 ms(X4-02;檔頭原寫
  「不到 1 ms」只量了 `statistics.correlation` 一次,沒量整支)。現版 `push()` 時就把新的一筆
  配對報酬算好,per-(腿, 窗) 維護 deque + running sums `(Σx, Σy, Σxx, Σyy, Σxy)`(n = deque 長度),
  `correlations()` 只做逐出 + 閉式公式 → 每秒 < 0.1 ms。
  舊檔頭的顧慮「增量滑動窗的浮點誤差會隨執行時間累積」實測不成立(T2 §9 意外 1:32,400 次
  push 後 max|Δr| 3.9e-15,比前端 `toFixed(2)` 解析度小 12 個數量級);**真正會咬人的是窗邊界**
  —— 差一筆就是 1e-3 的錯。所以逐出語意**兩道鏡像舊版**(見 `push` / `correlations` 註解),
  守門測試斷 `n{w}` 完全相等而不是 r 在容差內。
- **報酬不跨洞接合**:只有相鄰取樣秒且兩腿皆有中價時才產生一筆報酬。跨洞報酬涵蓋的
  時間長度與其餘不一致,而缺值最常發生在流動性最差的腿(費半),汙染方向與中價取樣
  要防的 Epps 效應同向。
- **時間戳逐出**而非固定長度:每秒 tick 若因 event loop 延遲漏拍,固定長度 deque
  涵蓋的實際時間會超過窗長,窗語意失真。
- 常數序列(窗內零波動)→ None,不是 0 也不是 NaN。閉式公式下「零波動」以 `_SS_FLOOR`
  判中心化**平方和**(Σx² − (Σx)²/n,未除 n;門檻隨 n 放大是刻意的,殘差也隨加減次數累積):
  running sums 加減後的殘差量級 ~1e-21,真實最小一檔報酬單筆平方 ≥ 1e-12,中間留六個數量級;
  deque 清空即把 sums 歸回精確零,稀疏腿不累積殘差。

前提:`push` 的 ts 與 `correlations(now)` 的 now 都單調不減 —— engine 兩者同源 `time.monotonic`
(`corr_engine.CorrelationEngine(now_fn=)` 預設),牆鐘校時回撥(#236 `w32tm /resync`)碰不到;
`correlations()` 的逐窗逐出是破壞性的,now 若倒退,已逐出的配對不會回來(舊版重掃可以)。
同 ts 重複 push 不產生報酬(相鄰判定不成立)。
"""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Mapping, Sequence

from copycat.live.corr_models import log_return

logger = logging.getLogger(__name__)

__all__ = ["CorrState", "SessionKey"]

SessionKey = tuple[str, str]  # (ymd_utc, "day" | "night");copycat.live.session 同型

_DEFAULT_WINDOWS = (60, 300, 1800)
_DEFAULT_MIN_SAMPLES = {60: 30, 300: 100, 1800: 300}

#: 中心化平方和(Σx² − (Σx)²/n)低於此值視為常數序列(回 None)。見檔頭。
_SS_FLOOR = 1e-18

#: (ts, prev_ts, base 報酬, leg 報酬):prev_ts 是逐出用(鏡像舊版「前一筆中價被逐出 → 配不成」)。
_Pair = tuple[float, float, float, float]


class CorrState:
    def __init__(
        self,
        leg_keys: Sequence[str],
        base: str,
        *,
        windows: tuple[int, ...] = _DEFAULT_WINDOWS,
        min_samples: Mapping[int, int] | None = None,
        sample_secs: float = 1.0,
    ) -> None:
        self._base = base
        self._legs = [k for k in leg_keys if k != base]
        self._windows = windows
        self._min_samples = (
            dict(min_samples) if min_samples is not None else dict(_DEFAULT_MIN_SAMPLES)
        )
        self._sample_secs = sample_secs
        # 相鄰判定容差 = 半個取樣間隔,吸收 event loop 抖動
        self._adjacent_tol = sample_secs * 0.5
        self._max_window = max(windows)
        self._cap = int(2 * self._max_window / sample_secs) if sample_secs > 0 else 4096
        # 中價序列仍保留:它定義「哪些樣本還活著」(時間逐出 + `_cap`),配對報酬的逐出以它為準
        self._series: dict[str, deque[tuple[float, int | None]]] = {
            k: deque() for k in [base, *self._legs]
        }
        # per-(腿, 窗):配對報酬 deque + running sums(版面 = `_SUMS_LAYOUT`;n 不另存,恆 = len(deque))
        self._pairs: dict[str, dict[int, deque[_Pair]]] = {
            leg: {w: deque() for w in windows} for leg in self._legs
        }
        self._sums: dict[str, dict[int, list[float]]] = {
            leg: {w: [0.0] * _SUMS_LEN for w in windows} for leg in self._legs
        }
        self._session: SessionKey | None = None

    # ---- 寫入 ----

    def push(self, ts: float, mids: Mapping[str, int | None], session: SessionKey) -> None:
        """一次每秒取樣;盤別(含 UTC 日期)變更 → 先清空所有序列再寫入本筆(SC-4)。

        新的一筆配對報酬在這裡算好(舊版在 `correlations()` 重掃時才算):前一筆 = 各序列的
        尾筆(舊版迭代時的 `prev_*` 同義,None 也照推進),相鄰 + 兩端皆有值才成一對。
        逐出第一道:中價序列照舊版逐出(時間 + `_cap`)後,**前一筆中價 ts 早於最老倖存樣本**
        的配對一併丟 —— 舊版那一對是在重掃時「配不到前一筆」而自然消失,這裡顯式做同一件事。
        """
        if self._session is not None and session != self._session:
            self._clear()
        self._session = session
        base_series = self._series[self._base]
        prev_base = base_series[-1] if base_series else None
        base_mid = mids.get(self._base)
        for leg in self._legs:
            leg_series = self._series[leg]
            prev_leg = leg_series[-1] if leg_series else None
            leg_mid = mids.get(leg)
            if (
                prev_base is not None
                and prev_leg is not None
                and prev_base[1] is not None
                and prev_leg[1] is not None
                and base_mid is not None
                and leg_mid is not None
                and abs((ts - prev_base[0]) - self._sample_secs) <= self._adjacent_tol
            ):
                rb = log_return(prev_base[1], base_mid)
                rl = log_return(prev_leg[1], leg_mid)
                if rb is not None and rl is not None:
                    pair: _Pair = (ts, prev_base[0], rb, rl)
                    pairs = self._pairs[leg]
                    sums = self._sums[leg]
                    for w in self._windows:
                        pairs[w].append(pair)
                        _add(sums[w], rb, rl)
        for key, series in self._series.items():
            series.append((ts, mids.get(key)))
            while len(series) > self._cap:
                series.popleft()
        self._evict(ts)
        floor = base_series[0][0]  # 本筆剛 append,非空
        for leg in self._legs:
            pairs = self._pairs[leg]
            sums = self._sums[leg]
            for w in self._windows:
                dq = pairs[w]
                while dq and dq[0][1] < floor:
                    _sub(sums[w], dq.popleft(), len(dq))

    def _clear(self) -> None:
        for series in self._series.values():
            series.clear()
        for leg in self._legs:
            for w in self._windows:
                self._pairs[leg][w].clear()
                self._sums[leg][w] = [0.0] * _SUMS_LEN

    def _evict(self, now: float) -> None:
        cutoff = now - self._max_window
        for series in self._series.values():
            while series and series[0][0] < cutoff:
                series.popleft()

    # ---- 讀出 ----

    def correlations(self, now: float) -> dict[str, dict[str, float | int | None]]:
        """{leg: {"w60": r|None, "n60": int, ...}};樣本不足或常數序列 → None。

        逐出第二道:各窗以 `ts < now − w` 丟(舊版逐窗 `ts >= cutoff` 過濾的補集);`now` 是
        呼叫端此刻的時鐘,與最後一筆 push 的 ts 可能差幾 µs,語意與舊版同(同一個 now 過濾)。
        最長窗與 `push` 的第一道合起來 = 舊版「最長窗實際 1800 筆、短窗 w+1 筆」的邊界語意。
        """
        result: dict[str, dict[str, float | int | None]] = {}
        for leg in self._legs:
            pairs = self._pairs[leg]
            sums = self._sums[leg]
            row: dict[str, float | int | None] = {}
            for w in self._windows:
                dq = pairs[w]
                s = sums[w]
                cutoff = now - w
                while dq and dq[0][0] < cutoff:
                    _sub(s, dq.popleft(), len(dq))
                n = len(dq)
                row[f"n{w}"] = n
                row[f"w{w}"] = _corr(s, n, self._min_samples.get(w, 0))
            result[leg] = row
        return result


#: running sums 版面(list 而非 dataclass:每秒 30 個 (腿, 窗) 各加減一次,索引比屬性存取便宜,
#: 且整份歸零只是一個 slice 指派);n 不在裡面 —— 唯一真相 = 該窗 deque 的長度。
_SUMS_LAYOUT = ("Σx", "Σy", "Σxx", "Σyy", "Σxy")
_SUMS_LEN = len(_SUMS_LAYOUT)
_SX, _SY, _SXX, _SYY, _SXY = range(_SUMS_LEN)


def _add(s: list[float], x: float, y: float) -> None:
    s[_SX] += x
    s[_SY] += y
    s[_SXX] += x * x
    s[_SYY] += y * y
    s[_SXY] += x * y


def _sub(s: list[float], pair: _Pair, remaining: int) -> None:
    """`remaining` = pop 之後 deque 還剩幾筆;歸零時整份回精確零,不讓加減殘差(~1e-21)留給下一批。"""
    if remaining <= 0:
        s[:] = [0.0] * _SUMS_LEN
        return
    _ts, _prev, x, y = pair
    s[_SX] -= x
    s[_SY] -= y
    s[_SXX] -= x * x
    s[_SYY] -= y * y
    s[_SXY] -= x * y


def _corr(s: list[float], n: int, min_n: int) -> float | None:
    if n < max(min_n, 2):
        return None
    sx, sy, sxx, syy, sxy = s
    vx = sxx - sx * sx / n
    vy = syy - sy * sy / n
    if vx <= _SS_FLOOR or vy <= _SS_FLOOR:
        # 任一序列為常數(整窗零波動)→ 分母為零。回 None,不是 0 也不是 NaN。
        return None
    r = (sxy - sx * sy / n) / math.sqrt(vx * vy)
    # 閉式公式的捨入可能讓 |r| 超出 1 一個 ulp;夾回定義域
    return max(-1.0, min(1.0, r))
