"""verify 模式支援:fake TXO source + 外部 IO env key 清單(單一 source of truth)。

**本模組刻意不 import fastapi / uvicorn**:tests/conftest.py 全域 import 這裡的 key 清單,
不能因此把 [live] extras 變成整個測試套件的硬依賴;組 app 的那步留在 `__main__`。
"""

from __future__ import annotations

from typing import Callable

from copycat.live.models import OptionContract, SeriesInfo, Tick

#: capital/factory 讀取的全部環境變數 key。tests/conftest.py 與 test_factory 引用同一份
#: (原本住在 conftest;上提到 package 讓 verify 模式與測試隔離不會漂移)。
CAPITAL_ENV_KEYS = (
    "CAPITAL_USER_ID",
    "CAPITAL_PASSWORD",
    "CAPITAL_FULL_ACCOUNT",
    "CAPITAL_ENV",
    "CAPITAL_ORDER_ENABLED",
    "CAPITAL_MAX_QTY",
    "CAPITAL_MAX_AMOUNT",
    "CAPITAL_DLL_DIR",
    "CAPITAL_AUDIT_DIR",
    "TXO_AUDIT_DIR",
)

DISCORD_ENV_KEYS = ("DISCORD_BOT_TOKEN", "SIGNALS_DISCORD_CHANNEL_ID")


# ---- fake TXO source(verify 模式與 server route 測試共用的唯一一份)----

C = OptionContract(symbol="TC.O.TWF.TXO.202608.C.23000", cp="C", strike_millipts=23_000_000)
SERIES = SeriesInfo(series_id="TXO.202608", name="TXO 202608", expiry="202608", contracts=(C,))


class FakeTxoSource:
    """全部 no-op 的 TXO source:lifespan 需要一個 `QuoteSource`,verify 模式與六組
    route 測試(corr / river / stock / index / market / health)都不碰 TXO 行情。
    原住 tests/helpers/fake_txo.py,verify 模式落地後上提;該檔改 re-export 保持
    測試 import 路徑不動。
    """

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
