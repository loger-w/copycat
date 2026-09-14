"""回報鏈統計(#234):從 server log 的「balance 鏈」行算**乾淨子集**的落地耗時。

這把尺是 Tier 2-6(回報鏈變快)的驗收判準。V2 §2.3 證明原尺會被開機次數污染(每收一筆成交
就重設起點、開機 backlog 重播集中在前兩分鐘),所以判準寫死成六道排除(**依 `_classify` 的
判定順序列**,一條鏈只記第一個命中的原因):

- `no_start` / `unfinished`:缺庫存段起點(輪詢鏈中途被成交點亮)/ log 在鏈中間結束;
- `partial_chain`:首尾都對但中段缺(pending 8 s watchdog 強制落地只兩段、`get_profit_loss_gw`
  rc≠0 跳損益段三段)—— 不是四段齊全的鏈,不與四段的比(pr-238 review F-03;prod 198 條真語料
  只 1 條乾淨鏈缺段,剔除後 p50/p90/p99 1953/3027/6433,尺沒壞、只是口徑寫實);
- `off_session`:成交回報**到達時刻**(段時刻 − 累積值)不在 09:00–13:30;
- `non_monotonic`:累積值不遞增(計時器被中途歸零的指紋);
- `short_balance`:庫存段 < 500 ms(0.5 s debounce 結構上不可能被跳過)。

同時數 `rc=1019`(群益「查詢處理中」)出現幾次 —— 每次精準 +1,060 ms,是尾巴的唯一來源;
改回報鏈的批次要同時看它有沒有變少。純 stdlib、純函式;CLI `chain-stats` 是薄包裝。
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_STAGE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}),(?P<ms>\d{3}) "
    r"copycat\.capital\.client INFO balance 鏈: "
    r"(?P<stage>庫存段收齊|損益段收齊|期貨部位段收齊|部位落地) .*?"
    r"自成交回報到達起 (?P<elapsed>\d+) ms"
)
_1019_RE = re.compile(r"rc=1019\b")
_STAGES = ("庫存段收齊", "損益段收齊", "期貨部位段收齊", "部位落地")
#: 盤中窗:成交回報到達時刻落在 [09:00:00, 13:30:00)
SESSION_START = _dt.time(9, 0)
SESSION_END = _dt.time(13, 30)
#: 0.5 s debounce 的下界:庫存段短於它 = 計時器被重設,不是鏈快
MIN_BALANCE_MS = 500


@dataclass
class ChainStats:
    total: int = 0
    clean: int = 0
    excluded: dict[str, int] = field(default_factory=dict)
    landed_ms: list[int] = field(default_factory=list)  # 乾淨子集的落地累積值,升冪
    count_1019: int = 0

    def _pct(self, q: float) -> int | None:
        """nearest-rank 百分位(第 ceil(q·n) 小);n=0 → None。"""
        n = len(self.landed_ms)
        if n == 0:
            return None
        return self.landed_ms[max(1, math.ceil(q * n)) - 1]

    @property
    def p50(self) -> int | None:
        return self._pct(0.5)

    @property
    def p90(self) -> int | None:
        return self._pct(0.9)

    @property
    def p99(self) -> int | None:
        return self._pct(0.99)


def _in_session(stamp: _dt.datetime, elapsed_ms: int) -> bool:
    arrived = (stamp - _dt.timedelta(milliseconds=elapsed_ms)).time()
    return SESSION_START <= arrived < SESSION_END


def _classify(chain: list[tuple[str, _dt.datetime, int]]) -> str | None:
    """一條鏈的排除原因;None = 乾淨。順序固定,一條鏈只記第一個命中的原因。"""
    stages = [s for s, _t, _e in chain]
    if stages[0] != _STAGES[0]:
        return "no_start"
    if stages[-1] != _STAGES[-1]:
        return "unfinished"
    if set(stages) != set(_STAGES):
        return "partial_chain"
    _s0, t0, e0 = chain[0]
    if not _in_session(t0, e0):
        return "off_session"
    elapsed = [e for _s, _t, e in chain]
    if any(b < a for a, b in zip(elapsed, elapsed[1:], strict=False)):
        return "non_monotonic"
    if e0 < MIN_BALANCE_MS:
        return "short_balance"
    return None


def summarize(lines: Iterable[str]) -> ChainStats:
    """逐行掃 log:段行依序串成鏈(庫存段開新鏈、部位落地收鏈),1019 逐行計數。"""
    stats = ChainStats()
    current: list[tuple[str, _dt.datetime, int]] = []

    def close(chain: list[tuple[str, _dt.datetime, int]]) -> None:
        if not chain:
            return
        stats.total += 1
        reason = _classify(chain)
        if reason is None:
            stats.clean += 1
            stats.landed_ms.append(chain[-1][2])
        else:
            stats.excluded[reason] = stats.excluded.get(reason, 0) + 1

    for raw in lines:
        line = raw.rstrip("\n")
        if _1019_RE.search(line):
            stats.count_1019 += 1
            continue
        m = _STAGE_RE.match(line)
        if m is None:
            continue
        stage = m.group("stage")
        stamp = _dt.datetime.fromisoformat(f"{m.group('date')} {m.group('time')}.{m.group('ms')}")
        entry = (stage, stamp, int(m.group("elapsed")))
        if stage == _STAGES[0] and current:
            close(current)  # 上一條沒落地就開了新鏈 → 上一條 unfinished
            current = []
        current.append(entry)
        if stage == _STAGES[-1]:
            close(current)
            current = []
    close(current)
    stats.landed_ms.sort()
    return stats


def format_report(stats: ChainStats) -> str:
    def ms(v: int | None) -> str:
        return "-" if v is None else f"{v} ms"

    excluded = "、".join(f"{k} {v}" for k, v in sorted(stats.excluded.items())) or "無"
    return (
        f"回報鏈 {stats.total} 條,乾淨 {stats.clean} 條(排除:{excluded})\n"
        f"乾淨子集落地耗時:p50 {ms(stats.p50)} / p90 {ms(stats.p90)} / p99 {ms(stats.p99)}\n"
        f"群益 1019 × {stats.count_1019}\n"
    )
