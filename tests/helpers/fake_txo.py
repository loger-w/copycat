"""server route 測試共用的 TXO QuoteSource fake。

`create_app` 的 lifespan 一定要一個 `QuoteSource`,但 corr / river / stock / index /
market / health 這六組路由測試都不碰 TXO 行情 —— 六檔各自抄一份逐字相同的 fake 與
`_C` / `_SERIES` 常數,QuoteSource Protocol 一改就要六處同步(漏一處是 pyright 才會
發現的靜默分岔)。這裡是唯一一份。
"""

from __future__ import annotations

from typing import Callable

from copycat.live.models import OptionContract, SeriesInfo, Tick

C = OptionContract(symbol="TC.O.TWF.TXO.202608.C.23000", cp="C", strike_millipts=23_000_000)
SERIES = SeriesInfo(series_id="TXO.202608", name="TXO 202608", expiry="202608", contracts=(C,))


class FakeTxoSource:
    """全部 no-op 的 TXO source;lifespan 需要它,路由測試不碰它。"""

    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        return None

    def unsubscribe(self, series: SeriesInfo) -> None:
        return None

    def close(self) -> None:
        return None
