"""verify 模式支援:fake TXO source + 外部 IO env 壓制(`python -m copycat.server --verify`)。

盤中不可起第二台連 TC4 的後端(CLAUDE.md §8:同 symbol 跨 session 只推一邊,會靜默搶走
prod 的推播)——驗 HTTP 層(route 形狀 / 非行情 endpoint)一律走本模組的 fake source +
另一個 port,整條路不碰 ZMQ。

**本模組刻意不 import fastapi / uvicorn**:tests/conftest.py 全域 import 這裡的 key 清單,
不能因此把 [live] extras 變成整個測試套件的硬依賴;組 app 的那步留在 `__main__`。

env 壓制的必要性(next-time 2026-08-04):app lifespan 無條件呼叫 `get_capital`,
CAPITAL_USER_ID 有值(env 或 repo root .env)即載真 SKCOM DLL;DISCORD_BOT_TOKEN 有值
即真登入 Discord。歷史事故:驗證腳本以真憑證打了一次群益登入(restart_trials.py 的
Popen 無 env= 直接繼承)。
"""

from __future__ import annotations

import os
from typing import Callable

import copycat.capital.factory as _capital_factory
import copycat.notify as _notify
import copycat.server.discord_bot as _discord_bot
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

DISCORD_ENV_KEYS = ("DISCORD_BOT_TOKEN", "SIGNALS_DISCORD_CHANNEL_ID", "DISCORD_WEBHOOK_URL")

#: neutralize 會對其 `_dotenv_values` / `_dotenv_cache` 動手的模組。
#: 測試的 restore point 吃同一份(review T-4:兩處手抄清單會漂移)。
DOTENV_MODULES = (_capital_factory, _discord_bot)


def neutralize_external_env() -> None:
    """把外部 IO 憑證整批中和:群益(SKCOM DLL)、Discord bot、Discord webhook 都不得真連。

    三層處置(單靠 delenv 不夠 —— .env fallback 還在):

    1. 全部 key 設**空字串** —— capital/factory 與 discord_bot 的 `_getenv` 都是
       「`name in os.environ` 即用(含空字串)」的新語意,空字串 = 明確清空、壓制 .env。
    2. 兩個模組的 `_dotenv_values` patch 成空 + cache 復位 —— 防未來有 key 走回
       「僅未設才 fallback」的舊語意時,.env 值靜默復活。
    3. notify.py 是第三條出口(webhook),且是**舊語意**(值空白也 fallback .env)+
       自有 cache —— 空字串壓不住它,直接把 cache 釘成「已解析且為 None」(review R-6)。

    程序生命週期內不還原(verify server 整個 process 都不該碰真憑證);測試要呼叫它時
    自行先用 monkeypatch 登記還原點(tests/server/test_verify.py 示範)。
    """
    for key in (*CAPITAL_ENV_KEYS, *DISCORD_ENV_KEYS):
        os.environ[key] = ""
    for mod in DOTENV_MODULES:
        setattr(mod, "_dotenv_values", lambda: {})
        setattr(mod, "_dotenv_cache", None)
    setattr(_capital_factory, "_client", None)
    setattr(_notify, "_WEBHOOK_URL", None)
    setattr(_notify, "_URL_RESOLVED", True)


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
