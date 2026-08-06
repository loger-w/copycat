"""verify 模式支援:fake TXO source + 外部 IO env 壓制(`python -m copycat.server --verify`)。

盤中不可起第二台連 TC4 的後端(CLAUDE.md §8:同 symbol 跨 session 只推一邊,會靜默搶走
prod 的推播)——驗 HTTP 層(route 形狀 / 非行情 endpoint)一律走本模組的 fake source +
另一個 port,整條路不碰 ZMQ。

**本模組刻意不 import fastapi / uvicorn**:tests/conftest.py 全域 import 這裡的 key 清單,
不能因此把 [live] extras 變成整個測試套件的硬依賴;組 app 的那步留在 `__main__`。

**FinMind 兩條路刻意分開處置**:`/api/futures/oi-levels` 照舊**真打**(它的驗證價值
就在那條路上);家數帶(breadth)走本模組的 `fake_breadth_fetchers()` **不打真 FinMind**
—— 每 10 秒一次的輪詢在驗證期間會持續燒配額,而家數帶要驗的是接線與三態形狀,fake
固定快照反而讓斷言變成確定值(失敗注入見該函式的 `VERIFY_BREADTH_FAIL`)。同理由涵蓋
第四支 EOD 日線(R3 連板數):真打的話一輪要抓 10 個交易日的全市場日線。

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


# ---- fake breadth 取數五元組(--verify 模式;market-overview R2 SC-3 / R3 SC-1 / R4)----

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

#: (代號, 收盤, 漲跌價, 漲跌幅%, 最高, 最低)。1101 前收 10.0 → 漲停 11.0(已鎖);
#: 6488 前收 10.0 → 跌停 9.0(已鎖);**3105 前收 79.0 → 漲停 86.9,high 摸到但收
#: 80.0 = 「觸及未鎖」**(R3 列表的第三種狀態,不造這一列就在畫面上看不到那條路);
#: 0050 是 `00` 前綴 → 被 universe filter 剔掉(驗排除路徑也有走到)。
_BREADTH_QUOTES: tuple[tuple[str, float, float, float, float, float], ...] = (
    ("1101", 11.0, 1.0, 10.0, 11.0, 10.2),
    ("2330", 1000.0, 5.0, 0.5, 1005.0, 990.0),
    ("2317", 200.0, 0.0, 0.0, 202.0, 199.0),
    ("2454", 1200.0, -10.0, -0.83, 1215.0, 1195.0),
    ("6488", 9.0, -1.0, -10.0, 9.9, 9.0),
    ("3105", 80.0, 1.0, 1.27, 86.9, 79.5),
    ("0050", 200.0, 1.0, 0.5, 201.0, 199.0),
)

#: (代號, 收盤, 除權息調整價差)—— `TaiwanStockPrice` 的 EOD 造值,**每個掃描日都回
#: 同一份**:`prev_close = close − spread`,1101 = 11.0 − 1.0 → 前收 10.0 → 漲停 11.0,
#: 於是逐日交集後 1101 是唯一的連板檔(其餘皆非漲停)。
_BREADTH_DAILY: tuple[tuple[str, float, float], ...] = (
    ("1101", 11.0, 1.0),
    ("2330", 1000.0, 5.0),
    ("2317", 200.0, 0.0),
    ("2454", 1200.0, -10.0),
    ("6488", 9.0, -1.0),
    ("3105", 80.0, 1.0),
    ("0050", 200.0, 1.0),
)

#: EOD 造值的填充列數。**不是湊數**:`breadth_engine._DAILY_MIN_ROWS`(25,000)把
#: 「非空但列數過少」判成回應被截斷 → 整輪失敗 → verify server 的連板欄整天 null,
#: 與「連板管線壞掉」同形。填充列用 6 位權證碼(`classify_stock_id` 會剃掉),只負責
#: 讓列數像真的全市場單日回應(2026-08-05 實測 42,074 列)。
#: 門檻的耦合由 `tests/server/test_verify.py` 直接對 `_DAILY_MIN_ROWS` 斷言釘住 ——
#: 這裡不 import breadth_engine(本模組刻意不拖 fastapi 進 conftest 的 import 路徑)。
_DAILY_PAD_ROWS = 25_000

#: 產業鏈對照(R4):**必須涵蓋 `_BREADTH_QUOTES` 的股票** —— 對不上的話每個群組都是
#: 0 成員(`compute_sector_rotation` 天然略過)→ industries 空陣列,而那與「rotation
#: 接線壞掉」在畫面上同形。半導體刻意給三個子產業:sub 展開那條路要看得到。
#: 0050 不列(ETF 在 universe 就被剔掉,列了也只是幽靈成員)。
_BREADTH_CHAIN: tuple[tuple[str, str, str], ...] = (
    ("1101", "水泥", "水泥製造"),
    ("2330", "半導體", "晶圓代工"),
    ("2454", "半導體", "IC 設計"),
    ("6488", "半導體", "矽晶圓"),
    ("3105", "半導體", "化合物半導體"),
    ("2317", "電子零組件", "連接器"),
)

#: 設成 `"1"` 時五個取數點全拋 `BreadthFetchError` —— SC-3(FinMind 掛掉只讓家數面板
#: stale,TC4 系零波及)在**真 server** 上的注入通道;單元測試注入 fake 即可,這條
#: 是為了在跑著的 verify server 上取證。
#: **前置**:verify 的 data_dir 必須是隔離空目錄(無 `industry_chain.json`)—— 有快取檔
#: 的話 chain 那支拋不拋都一樣有表,失效注入就漏了一條路(design §8 / R9)。該前置
#: 已由 `__main__` 自動化(這個 key 為 "1" 時改用 `VERIFY_FAIL_DATA_DIR` 並開機清檔),
#: 不靠 operator 記得手動刪(review S-2/C-3)。
FAIL_ENV_KEY = "VERIFY_BREADTH_FAIL"

#: 設成 `"1"` 時 1101 依**牆鐘**分鐘在「鎖漲停 ↔ 非鎖」兩態切換 —— SC-7(廣度事件
#: → hub → WS → 前端時間軸)在真 server 上的唯一取證通道:fake 快照恆定的話一則事件
#: 都不會發,整條鏈路無從目視。
#: 週期取 `minute // 11` 的奇偶 = 11 分鐘,**刻意 > 事件冷卻 600s**(`event_cooldown_secs`)
#: —— 每次翻轉必定發得出事件,不會被冷卻吃掉。
FLIP_ENV_KEY = "VERIFY_BREADTH_FLIP"

#: 翻轉後的 1101(前收仍是 10.0 → 漲停 11.0,但收在 10.5 = **未鎖**;high 仍摸到漲停
#: → 落在「觸及未鎖」那一態)。`close` / `change_price` 都給值是硬要求:缺欄會讓
#: `limit_judged=False`,而那樣的列在事件 diff 被整列跳過 —— 翻了也不發事件。
_FLIP_1101 = ("1101", 10.5, 0.5, 5.0, 11.0, 10.2)


#: engine 的分鐘域(`index_engine.minute_key`:0901–1330;1331–1335 clamp 進 1330)。
#: 域外的時刻不入序列 —— 而 verify server 多半是**盤後**跑的。
_DOMAIN_START = _dt.time(9, 1)
_DOMAIN_END = _dt.time(13, 30)
#: 域外 clamp 的落點:`13:<牆鐘分鐘 % _CLAMP_MINUTE_MOD>`。模數取 29 讓分鐘停在
#: 00–28(域上界 13:30 之內,且避開 clamp 進來就撞邊界的 13:29/13:30)。
_CLAMP_HOUR = 13
_CLAMP_MINUTE_MOD = 29


def _now() -> _dt.datetime:
    """fake 快照的牆上時鐘(模組層一個名字,`breadth_engine._now` 同理由)。

    `datetime.datetime` 是不可變型別、monkeypatch 不上去 —— 沒有這個名字,翻轉的
    分鐘判定就只能靠測試真的等到某一分鐘,那是不可能寫的測試。
    """
    return _dt.datetime.now()


def _flip_locked(now: _dt.datetime) -> bool:
    """這一刻 1101 該不該是鎖漲停態(`FLIP_ENV_KEY` 開啟時)。

    判別子是**牆鐘**分鐘,不是 `_snapshot_stamp` clamp 後的快照時刻 —— 後者在盤後恆為
    13:00,分鐘永遠不動,而 verify server 幾乎都在盤後跑:拿它當判別子等於整條 SC-7
    取證路徑靜默失效(翻轉永遠不發生,畫面上與「事件接線壞掉」同形)。
    """
    return (now.minute // 11) % 2 == 0


def _snapshot_stamp(now: _dt.datetime) -> str:
    """fake 快照時刻:`now` 落在分鐘域外時 clamp 進 **13 時帶**(review SPEC-4)。

    日期一律是當天(`trade_date == today` 才會 append 與落檔,engine design R1);
    時刻若直接用 `datetime.now()`,盤後跑 verify server 的每一輪都落在域外 → 序列恆空,
    而那與「序列接線壞掉」在畫面上完全同形 —— verify 的存在理由正是目視這條路。

    **分鐘跟著牆鐘走**(`% _CLAMP_MINUTE_MOD`)而不是恆定 13:00(review S-1):廣度
    事件 id 含 `time` 欄 = 這個時刻,恆定的話翻轉之後每一則的 id 完全相同 → 前端去重
    把後續全吃掉,SC-7 的時間軸只看得到第一則;當日序列也只長得出一格。相差 29 分的
    兩個牆鐘會撞成同一格 —— 取證無妨(輪詢是 10 秒一次,同格只是 last-wins)。
    """
    if _DOMAIN_START <= now.time() <= _DOMAIN_END:
        stamp = now
    else:
        stamp = now.replace(
            hour=_CLAMP_HOUR,
            minute=now.minute % _CLAMP_MINUTE_MOD,
            second=0,
            microsecond=0,
        )
    return stamp.strftime("%Y-%m-%d %H:%M:%S")


def fake_breadth_fetchers() -> tuple[
    Callable[[str], list[dict]],
    Callable[[str], list[dict]],
    Callable[[str, _dt.date], list[dict]],
    Callable[[str, _dt.date], list[dict]],
    Callable[[str], list[dict]],
]:
    """固定小快照的 breadth 取數五元組(snapshot / stock_info / disposition /
    daily_prices / industry_chain)。

    快照時刻取自**呼叫當下**的 `datetime.now()`,域外 clamp 進盤中(`_snapshot_stamp`):
    `trade_date == today` 且時刻在分鐘域內才會 append 與落檔(engine 的 design R1/R3
    條件),序列因此會隨輪詢長出格子 —— 用固定日期或直接用盤後時刻的話,畫面上永遠
    只有 counts、序列恆空,而那與「序列接線壞掉」長得一模一樣。

    第四支(EOD 日線,R3)每個掃描日回同一份造值 → 1101 逐日皆漲停 → 連板數撞到回看
    窗上限(窗內 10 板 + 盤中今日這根 → 前端顯示「11+ 板」),`streak_capped` 那條路在
    verify 畫面上也走得到。

    第五支(產業鏈,R4)回固定小表且涵蓋本快照的每一檔 → 類股面板 anytime 有畫面;
    `VERIFY_BREADTH_FLIP=1` 時 1101 隨牆鐘翻轉,SC-7 的事件鏈路才有東西可看。
    """

    def _fail_if_injected() -> None:
        if os.environ.get(FAIL_ENV_KEY) == "1":
            raise BreadthFetchError("VERIFY_BREADTH_FAIL=1 注入的取數失敗")

    def _snapshot(_token: str) -> list[dict]:
        _fail_if_injected()
        now = _now()
        stamp = _snapshot_stamp(now)
        quotes = _BREADTH_QUOTES
        if os.environ.get(FLIP_ENV_KEY) == "1" and not _flip_locked(now):
            # 只換 1101 那一列(其餘照舊):翻轉要能與家數帶的其他變化分得開
            quotes = tuple(_FLIP_1101 if q[0] == _FLIP_1101[0] else q for q in quotes)
        return [
            {
                "date": stamp,
                "stock_id": sid,
                "close": close,
                "change_price": chg_price,
                "change_rate": chg_rate,
                "high": high,
                "low": low,
                "total_volume": 1_000,
                "yesterday_volume": 500,
                "total_amount": 12_345_000,
            }
            for sid, close, chg_price, chg_rate, high, low in quotes
        ]

    def _stock_info(_token: str) -> list[dict]:
        _fail_if_injected()
        today = _dt.date.today().isoformat()
        return [{**row, "date": today} for row in _BREADTH_INFO_ROWS]

    def _disposition(_token: str, _today: _dt.date) -> list[dict]:
        _fail_if_injected()
        return []  # 空 = 當下沒有處置中的股票(合法結果,與取數失敗不同)

    def _daily_prices(_token: str, day: _dt.date) -> list[dict]:
        _fail_if_injected()
        stamp = day.isoformat()
        rows = [
            {"date": stamp, "stock_id": sid, "close": close, "spread": spread}
            for sid, close, spread in _BREADTH_DAILY
        ]
        # 填充到全市場量級:低於 `_DAILY_MIN_ROWS` 會被引擎當成回應被截斷 → 整輪失敗
        rows.extend(
            {"date": stamp, "stock_id": f"{300000 + i}", "close": 10.0, "spread": 0.0}
            for i in range(_DAILY_PAD_ROWS)
        )
        return rows

    def _industry_chain(_token: str) -> list[dict]:
        _fail_if_injected()
        today = _dt.date.today().isoformat()
        return [
            {"date": today, "stock_id": sid, "industry": industry, "sub_industry": sub}
            for sid, industry, sub in _BREADTH_CHAIN
        ]

    return (_snapshot, _stock_info, _disposition, _daily_prices, _industry_chain)
