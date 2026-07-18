"""回補↔live 交接協定(design.md §2.3 DR-1/DR-11):訂閱先行 buffer → 回補灌入 → flush。"""

from __future__ import annotations

import logging

from copycat.live.aggregate import ChainAggregator
from copycat.live.models import Tick

logger = logging.getLogger(__name__)

DEFAULT_BUFFER_CAP = 200_000


class HandoverBuffer:
    """交接期 live tick 暫存;獨立於穩態 queue(DR-11)。append 回 False = 溢出。"""

    def __init__(self, cap: int = DEFAULT_BUFFER_CAP) -> None:
        self._cap = cap
        self._ticks: list[Tick] = []

    def append(self, tick: Tick) -> bool:
        if len(self._ticks) >= self._cap:
            return False
        self._ticks.append(tick)
        return True

    def __len__(self) -> int:
        return len(self._ticks)

    def drain(self) -> list[Tick]:
        ticks, self._ticks = self._ticks, []
        return ticks


def run_handover(agg: ChainAggregator, backfill_ticks: list[Tick], buffer: HandoverBuffer) -> None:
    """交接步驟 3-4:回補排序灌入(重建 cum)→ flush buffer(只放行 cum 較大者)。

    溢出處理(重跑協定)由呼叫端 engine 負責;本函數只做確定性灌入。
    """
    rebuilt = agg.ingest_backfill(backfill_ticks)
    flushed = 0
    for tick in buffer.drain():
        agg.route(tick)  # _ingest 內建 cum stale-drop:≤ 重建值即丟棄
        flushed += 1
    logger.info(
        "handover done: backfill=%d symbols=%d buffered=%d",
        len(backfill_ticks),
        len(rebuilt),
        flushed,
    )
