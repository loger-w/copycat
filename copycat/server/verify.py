"""verify 模式支援:fake TXO source + 外部 IO env 壓制(`python -m copycat.server --verify`)。

盤中不可起第二台連 TC4 的後端(CLAUDE.md §8:同 symbol 跨 session 只推一邊,會靜默搶走
prod 的推播)——驗 HTTP 層(route 形狀 / 非行情 endpoint)一律走本模組的 fake source +
另一個 port,整條路不碰 ZMQ。

**本模組刻意不 import fastapi / uvicorn**:tests/conftest.py 全域 import 這裡的 key 清單,
不能因此把 [live] extras 變成整個測試套件的硬依賴;組 app 的那步留在 `__main__`。

**FinMind 兩條路刻意分開處置**:`/api/futures/oi-levels` 照舊**真打**(它的驗證價值
就在那條路上);家數帶(breadth)走本模組的 `fake_breadth_fetchers()` **不打真 FinMind**
—— 每 10 秒一次的輪詢在驗證期間會持續燒配額,而家數帶要驗的是接線與三態形狀,fake
固定快照反而讓斷言變成確定值(失敗注入見該函式的 `VERIFY_BREADTH_FAIL`)。

env 壓制的必要性(next-time 2026-08-04):app lifespan 無條件呼叫 `get_capital`,
CAPITAL_USER_ID 有值(env 或 repo root .env)即載真 SKCOM DLL;DISCORD_BOT_TOKEN 有值
即真登入 Discord。歷史事故:驗證腳本以真憑證打了一次群益登入(restart_trials.py 的
Popen 無 env= 直接繼承)。
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Callable

import copycat.capital.factory as _capital_factory
import copycat.notify as _notify
import copycat.server.discord_bot as _discord_bot
from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.breadth_fetch import BreadthFetchError

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

    **FinMind(`FINMIND_TOKEN` / `oi_levels`)刻意不在中和清單內**(review LF-4):
    verify server 的存在理由正是「不碰 TC4 也能驗 HTTP 層」,而 `/api/futures/oi-levels`
    要驗的就是**真打 FinMind** 那條路(design §10:「oi-levels 在 fake-source server 上
    直接真打 FinMind(不碰 TC4)」)。中和它等於把該 endpoint 的驗證能力一起關掉,
    而它的失效樣態(降級成空 shape + 200)與「壓制生效」在畫面上完全同形。
    FinMind 也不具備本函式要防的那個風險等級 —— 讀取型 REST,不會像 SKCOM 那樣載 DLL、
    也不會像 bot token 那樣真的登入一個常駐連線。**測試側則相反**:`tests/conftest.py`
    有第三支 autouse fixture 把它中和掉(測試不該有任何真打上游的路徑)。

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


# ---- fake breadth 取數三元組(--verify 模式;market-overview R2 SC-3)----

#: `TaiwanStockInfo` 對照列(代號 / 市場別 / 產業別)—— snapshot 的白名單來源。
_BREADTH_INFO_ROWS: list[dict] = [
    {"stock_id": "1101", "stock_name": "台泥", "type": "twse", "industry_category": "水泥工業"},
    {"stock_id": "2330", "stock_name": "台積電", "type": "twse", "industry_category": "半導體業"},
    {"stock_id": "2317", "stock_name": "鴻海", "type": "twse", "industry_category": "其他電子業"},
    {"stock_id": "2454", "stock_name": "聯發科", "type": "twse", "industry_category": "半導體業"},
    {"stock_id": "6488", "stock_name": "環球晶", "type": "tpex", "industry_category": "半導體業"},
    {"stock_id": "3105", "stock_name": "穩懋", "type": "tpex", "industry_category": "半導體業"},
    {"stock_id": "0050", "stock_name": "元大台灣50", "type": "twse", "industry_category": "ETF"},
]

#: (代號, 收盤, 漲跌價, 漲跌幅%)。1101 前收 10.0 → 漲停 11.0;6488 前收 10.0 →
#: 跌停 9.0;0050 是 `00` 前綴 → 被 universe filter 剔掉(驗排除路徑也有走到)。
_BREADTH_QUOTES: tuple[tuple[str, float, float, float], ...] = (
    ("1101", 11.0, 1.0, 10.0),
    ("2330", 1000.0, 5.0, 0.5),
    ("2317", 200.0, 0.0, 0.0),
    ("2454", 1200.0, -10.0, -0.83),
    ("6488", 9.0, -1.0, -10.0),
    ("3105", 80.0, 1.0, 1.27),
    ("0050", 200.0, 1.0, 0.5),
)

#: 設成 `"1"` 時三個取數點全拋 `BreadthFetchError` —— SC-3(FinMind 掛掉只讓家數面板
#: stale,TC4 系零波及)在**真 server** 上的注入通道;單元測試注入 fake 即可,這條
#: 是為了在跑著的 verify server 上取證。
FAIL_ENV_KEY = "VERIFY_BREADTH_FAIL"


def fake_breadth_fetchers() -> tuple[
    Callable[[str], list[dict]],
    Callable[[str], list[dict]],
    Callable[[str, _dt.date], list[dict]],
]:
    """固定小快照的 breadth 取數三元組(snapshot / stock_info / disposition)。

    快照時刻用**呼叫當下**的 `datetime.now()`:`trade_date == today` 才會 append 與
    落檔(engine 的 design R1 條件),序列因此會隨輪詢長出格子 —— 用固定日期的話
    畫面上永遠只有 counts、序列恆空,而那與「序列接線壞掉」長得一模一樣。
    """

    def _fail_if_injected() -> None:
        if os.environ.get(FAIL_ENV_KEY) == "1":
            raise BreadthFetchError("VERIFY_BREADTH_FAIL=1 注入的取數失敗")

    def _snapshot(_token: str) -> list[dict]:
        _fail_if_injected()
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return [
            {
                "date": stamp,
                "stock_id": sid,
                "close": close,
                "change_price": chg_price,
                "change_rate": chg_rate,
                "total_volume": 1_000,
                "yesterday_volume": 500,
                "total_amount": 12_345_000,
            }
            for sid, close, chg_price, chg_rate in _BREADTH_QUOTES
        ]

    def _stock_info(_token: str) -> list[dict]:
        _fail_if_injected()
        today = _dt.date.today().isoformat()
        return [{**row, "date": today} for row in _BREADTH_INFO_ROWS]

    def _disposition(_token: str, _today: _dt.date) -> list[dict]:
        _fail_if_injected()
        return []  # 空 = 當下沒有處置中的股票(合法結果,與取數失敗不同)

    return (_snapshot, _stock_info, _disposition)
