"""滾動相關係數狀態機(零 IO;SC-1/3/4;design §5)。

每秒一筆取樣 → 多窗滾動 Pearson。設計要點:

- **整批重算,不維護增量統計量**:`statistics.correlation`(stdlib,內部用 fsum)對
  1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms。增量滑動窗的浮點誤差會隨執行時間
  累積,整批重算讓「增量 vs 整批一致」這件事恆真,不必寫測試去追誤差上界。
- **報酬不跨洞接合**:只有相鄰取樣秒且兩腿皆有中價時才產生一筆報酬。跨洞報酬涵蓋的
  時間長度與其餘不一致,而缺值最常發生在流動性最差的腿(費半),汙染方向與中價取樣
  要防的 Epps 效應同向。
- **時間戳逐出**而非固定長度:每秒 tick 若因 event loop 延遲漏拍,固定長度 deque
  涵蓋的實際時間會超過窗長,窗語意失真。
"""

from __future__ import annotations

import logging
import statistics
from collections import deque
from collections.abc import Mapping, Sequence

from copycat.live.corr_models import log_return

logger = logging.getLogger(__name__)

__all__ = ["CorrState", "SessionKey"]

SessionKey = tuple[str, str]  # (ymd_utc, "day" | "night");copycat.live.session 同型

_DEFAULT_WINDOWS = (60, 300, 1800)
_DEFAULT_MIN_SAMPLES = {60: 30, 300: 100, 1800: 300}


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
        self._series: dict[str, deque[tuple[float, int | None]]] = {
            k: deque() for k in [base, *self._legs]
        }
        self._session: SessionKey | None = None

    # ---- 寫入 ----

    def push(self, ts: float, mids: Mapping[str, int | None], session: SessionKey) -> None:
        """一次每秒取樣;盤別(含 UTC 日期)變更 → 先清空所有序列再寫入本筆(SC-4)。"""
        if self._session is not None and session != self._session:
            for series in self._series.values():
                series.clear()
        self._session = session
        for key, series in self._series.items():
            series.append((ts, mids.get(key)))
            while len(series) > self._cap:
                series.popleft()
        self._evict(ts)

    def _evict(self, now: float) -> None:
        cutoff = now - self._max_window
        for series in self._series.values():
            while series and series[0][0] < cutoff:
                series.popleft()

    # ---- 讀出 ----

    def _paired_returns(self, leg: str, now: float) -> list[tuple[float, float, float]]:
        """(ts, base 報酬, leg 報酬) —— 僅取相鄰取樣秒且兩腿皆有中價者。

        回傳含 ts 是為了讓各窗以時間過濾同一份計算結果,不必逐窗重掃序列。
        """
        base_series = self._series[self._base]
        leg_series = self._series.get(leg)
        if leg_series is None or len(base_series) < 2:
            return []
        leg_by_ts = dict(leg_series)
        out: list[tuple[float, float, float]] = []
        prev_ts: float | None = None
        prev_base: int | None = None
        prev_leg: int | None = None
        for ts, base_mid in base_series:
            leg_mid = leg_by_ts.get(ts)
            if (
                prev_ts is not None
                and prev_base is not None
                and prev_leg is not None
                and base_mid is not None
                and leg_mid is not None
                and abs((ts - prev_ts) - self._sample_secs) <= self._adjacent_tol
            ):
                rb = log_return(prev_base, base_mid)
                rl = log_return(prev_leg, leg_mid)
                if rb is not None and rl is not None:
                    out.append((ts, rb, rl))
            prev_ts, prev_base, prev_leg = ts, base_mid, leg_mid
        return [row for row in out if row[0] >= now - self._max_window]

    def correlations(self, now: float) -> dict[str, dict[str, float | int | None]]:
        """{leg: {"w60": r|None, "n60": int, ...}};樣本不足或常數序列 → None。"""
        result: dict[str, dict[str, float | int | None]] = {}
        for leg in self._legs:
            paired = self._paired_returns(leg, now)
            row: dict[str, float | int | None] = {}
            for window in self._windows:
                cutoff = now - window
                xs = [rb for ts, rb, _ in paired if ts >= cutoff]
                ys = [rl for ts, _, rl in paired if ts >= cutoff]
                row[f"n{window}"] = len(xs)
                row[f"w{window}"] = self._corr(xs, ys, self._min_samples.get(window, 0))
            result[leg] = row
        return result

    @staticmethod
    def _corr(xs: list[float], ys: list[float], min_n: int) -> float | None:
        if len(xs) < max(min_n, 2):
            return None
        try:
            return statistics.correlation(xs, ys)
        except statistics.StatisticsError:
            # 任一序列為常數(整窗零波動)→ 分母為零。回 None,不是 0 也不是 NaN。
            return None
