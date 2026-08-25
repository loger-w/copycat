"""TC4QuoteSource:達錢 4 ZMQ 介接(唯一碰 ZMQ 的模組;design.md §3)。

實測事實(docs/research/2026-07-18-txo-chain-probe.md):
- QUERYALLINSTRUMENT Type="Opt";symbol 葉子 = TC.O.TWF.<prod>.<expiry>.<C|P>.<strike>
- SUBQUOTE/UNSUBQUOTE(REALTIME)必須帶 StartTime/EndTime(當日 UTC 窗),wrapper 原
  SubQuote 未帶會回 "invalid Date Time Format" → 本模組自帶 raw request。
- 歷史 TICKS 分頁:QryIndex 迴圈 + 停滯防呆(同 backfill_tc4 慣例)。
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, NamedTuple

import zmq

from copycat.live.models import (
    SPOT_SYMBOL,
    OptionContract,
    SeriesInfo,
    Tick,
    parse_history_tick,
    parse_option_symbol,
    parse_realtime,
)
from copycat.live.session import session_key, session_window
from copycat.tc4common import TC4_APPID, TC4_DEFAULT_PORT, TC4_SKEY, iter_qry_pages

__all__ = [
    "SPOT_SYMBOL",
    "TC4_APPID",
    "TC4_SKEY",
    "HistoryTimeoutError",
    "TC4QuoteSource",
    "group_series",
    "parse_stkfut_catalog",
]

logger = logging.getLogger(__name__)

#: K 線路徑的首頁等待預算(秒)。實測有資料標的 <1s 備妥 → 10× 餘裕;誤判為空時由
#: server 層的短 TTL 負向快取在 15s 後自動重試,不是永久釘死。
BARS_POLL_DEADLINE = 10.0
#: 歷史收割的退避輪詢起點;逐次加倍到 poll_wait 封頂(隨 _collect_history 自
#: stock_source 上提 — index-board R-3)
_POLL_BACKOFF_START = 0.15


class HistoryResult(NamedTuple):
    """`_collect_history` 的回傳:rows + 「是否等滿 deadline 仍未備妥」。

    TC4 的 GETHISDATA 空頁無法區分「未備妥」與「無資料」(檔頭),所以 `rows == []`
    這一件事本身沒有原因;`timed_out` 是**唯一**能從協定側正面取得的區分訊號
    —— 逾時路徑之外的空,至少代表首頁備妥、收割跑完了。
    """

    rows: list[dict]
    timed_out: bool


class HistoryTimeoutError(ConnectionError):
    """歷史首頁在預算內未備妥 —— 「現在取不到」,**不是**「沒有這些資料」。

    **為什麼是 `ConnectionError` 子類**(bug/history-timeout-propagation):六處 caller
    的上游都已經有 `except ConnectionError` 的降級/重試網(stock_engine 回補 worker、
    index_engine `_schedule_retry`、futures_engine、corr 訂閱重試)。做成子類 = 那些
    路徑一行不改就自動接手,只有真的需要分辨的地方才寫 `except HistoryTimeoutError`
    **先於** `except ConnectionError`;做成獨立例外或三態回傳則要動五個簽名 + 全部 fake。

    `timed_out` 是 TC4 協定側**唯一**能正面取得的「暫時性」訊號(空頁本身沒有原因)。
    丟掉它 = 逾時被讀成資料面就是沒有 → 全鏈無從重試,而畫面只是一直空著。
    """


_STALE_THRESHOLD_SECS = 30.0
_RECONNECT_BACKOFF_CAP = 60.0
#: 自癒重掛的退避上限(秒):同一 symbol 救不回時最慢每 5 分鐘再試一次
_HEAL_BACKOFF_CAP = 300.0
#: 第幾次重掛起改用新窗(= 新 key)。同一把 key 連兩次沒救回,代表這把 key 還有
#: 別的持有者(TXF.HOT 由 TXO + futures 雙持、外部 probe 也算)—— 自己 UNSUB→SUB
#: 永遠到不了 SumSubCount 0,TC4 就不會 ReqSubQuote 重掛上游 feed(repro.md 實驗 G)。
HEAL_VARIANT_AFTER = 3
#: window variant 的循環長度(1 → 2 → 3 → 1 …;窗開得再寬也回得來)
_HEAL_VARIANT_CYCLE = 3
#: 窗小時的合法值域(TC4 窗字串 = YYYYMMDDHH)
_WINDOW_HOUR_MAX = 23
_WINDOW_HOUR_MIN = 0
#: TXO runtime 的 `TXF.HOT` 常駐窗位移(小時)。futures session 用**原窗**持有同一個
#: symbol,位移之後兩邊是兩把互異的 TC4 refcount key(N050;`subscribe` 登記)。
#:
#: **必須整段落在自癒 variant 階梯之外**(review SP2):總位移 k = variant + offset,
#: 而兩邊的 variant 各自獨立地在 0..`_HEAL_VARIANT_CYCLE` 之間爬 —— offset 取 1 的話,
#: futures 自癒到 variant 1 的窗會**等於** TXO 的 offset 窗,雙持同一把 key 的原病在
#: 「其中一邊正在自癒」這個最需要它不復發的時刻復發。取 cycle+1 讓
#: futures 的 k ∈ [0..3] 與 TXO 的 k ∈ [4..7] 不相交。
SPOT_WINDOW_OFFSET = _HEAL_VARIANT_CYCLE + 1
#: TXO session 的門檻:R1 60s、R2 關 —— 277 檔契約深價外本就整場靜默,R2 收它們
#: 等於無止盡 churn(change-spec §3)。
#:
#: 接線點:`app._default_source`(heal_active = `session.in_txo_session`)。
TXO_HEAL_SILENCE_SECS = 60.0
# context 級 REQ timeout:app 死亡時 Connect/_rt_request 的裸 recv 才可返回、重連迴圈
# 才可被 _stop 中斷。10s = 實測最重呼叫 QUERYALLINSTRUMENT(Opt) 1.93s 的 5 倍裕度;
# GetHistory 分頁實測 max 1.1ms(3,482 次、10.7 萬 rows)不受影響(2026-07-20 probe)。
_REQ_TIMEOUT_MS = 10_000
#: `TC4QuoteSource(lock_timeout_secs=)` 的預設(理由見該參數的註解)。獨立成常數是為了讓
#: `close_worst_secs()` 與建構子吃**同一個值** —— 它是關機預算(`server/shutdown_budget.py`)
#: 的輸入之一,兩處各寫一個 12.0 就會靜默漂開。
DEFAULT_LOCK_TIMEOUT_SECS: float = 12.0
# 回補收割輪數上限與零進展早停(fetch_backfill round 制;空頁無法區分未備妥/無資料)
_HARVEST_ROUNDS = 16
_HARVEST_DRY_LIMIT = 3

#: LOGOUT 專用 recv 上界(fix/tc4-logout review SP3):TC4 對 LOGOUT 會回 reply(零訂閱 probe 實證),
#: 但 prod 是 UNSUB 幾百筆之後才送,若那個情境 TC4 不回,每條 session 會各吃 `_REQ_TIMEOUT_MS` 10 s。
#: 縮到 2 s 讓這一發遠小於 `close_worst_secs()` 已算進的「一發 REQ 逾時」(10 s),關機預算
#: (`server/shutdown_budget.py`,run.ps1 / uvicorn / lifespan 同源)不必為 LOGOUT 另加一項;
#: socket 反正緊接著 close,改它的 RCVTIMEO 沒有後遺症。**必須 < `_REQ_TIMEOUT_MS`**,否則預算低估。
_LOGOUT_TIMEOUT_MS = 2_000


def close_worst_secs() -> float:
    """單條 session `close()` **可計段**的最壞耗時上界(秒)—— 關機預算的產生點之一(review A1)。

    = 等 `_api_lock` + max(REQ 路徑, 毒鎖路徑),每一項都是本檔既有 timeout 的直接後果:

    1. 等 `_api_lock`:在途的 `_ensure_connected` 持鎖跨 `Connect()`,最壞吃滿一個 REQ timeout。
    2. 之後兩條路**互斥**(`_req` 進門先 `api.lock.acquire(timeout=lock_timeout)`):
       - REQ 路徑(拿到鎖):send + recv 各撞一次 SNDTIMEO / RCVTIMEO = 2 × REQ;finally 釋鎖,
         接著的 `_dispose` 立刻拿到 `api.lock`,Disconnect 不再等。
       - 毒鎖路徑(KeepAlive `Pong` 帶著鎖死掉):`_req` 等鎖 + `_dispose` 再等鎖 = 2 × lock,
         `_dispose` 拿不到就**跳過** Disconnect。
       UNSUBQUOTE 迴圈第一發失敗即 break(`_req` 內已 `_dispose`、`_api` 歸 None,`close()` 尾段
       看到 None 直接 return —— **LOGOUT 不會再送**);退訂全過才輪到 LOGOUT 逾時,而它的 recv
       上界 `_LOGOUT_TIMEOUT_MS`(2 s)< REQ。所以不論退訂 / LOGOUT 哪一發撞到,只付**一次** REQ。

    **不計的段(無上界可計)**:`Disconnect()` → KeepAlive `_ctx.term()` 要等 KeepAlive 執行緒
    自己關 SUB socket;wrapper 的 `ThreadProcess` 只 catch ZMQError,decode 類例外殺掉執行緒時
    socket 永不關 → `term()` 無界。那條 lane 卡住正是 run.ps1 到期硬殺要落的對象;並行 lane
    讓它只拖自己一條(改動前它拖後面全部)。
    健康路徑實測 < 1 s;這個數字只在 TC4 半死時才會被吃到,而那正是關機預算要蓋住的情境。
    """
    req_secs = _REQ_TIMEOUT_MS / 1000
    return req_secs + max(2 * req_secs, 2 * DEFAULT_LOCK_TIMEOUT_SECS)


def always_active() -> bool:
    """`heal_active` 預設:不設閘 = 全時段自癒(盤別閘由各 source 建構子帶)。"""
    return True


def always_symbol_active(symbol: str) -> bool:
    """`heal_symbol_active` 預設:每個 symbol 都在母體內(逐字等於逐 symbol 閘之前)。"""
    return True


def build_rt_request(request: str, session: str, symbol: str, window: tuple[str, str]) -> dict:
    """SUBQUOTE/UNSUBQUOTE REALTIME 請求(必帶合法 UTC 時間窗,spike 實測)。"""
    start, end = window
    return {
        "Request": request,
        "SessionKey": session,
        "Param": {
            "Symbol": symbol,
            "SubDataType": "REALTIME",
            "StartTime": start,
            "EndTime": end,
        },
    }


def group_series(symbols: list[str]) -> list[SeriesInfo]:
    """期權葉子 symbol → 序列清單(expiry 近 → 遠,同 expiry 按產品代碼)。

    顯示名 = "<prod> <expiry>"(EndDate 僅 REALTIME 有,清單層拿不到 → fallback,IR-5)。
    """
    groups: dict[tuple[str, str], list[OptionContract]] = {}
    for sym in symbols:
        parsed = parse_option_symbol(sym)
        if parsed is None:
            continue
        prod, expiry, cp, strike = parsed
        groups.setdefault((prod, expiry), []).append(
            OptionContract(symbol=sym, cp=cp, strike_millipts=strike * 1000)
        )
    series = [
        SeriesInfo(
            series_id=f"{prod}.{expiry}",
            name=f"{prod} {expiry}",
            expiry=expiry,
            contracts=tuple(sorted(cs, key=lambda c: (c.strike_millipts, c.cp))),
        )
        for (prod, expiry), cs in groups.items()
    ]
    series.sort(key=lambda s: (s.expiry, s.series_id))
    return series


#: 個股期真合約支(價差支逐字同名 + "(F2)");parser 顯式只走這一支
_STKFUT_BRANCH = "StockFutures"
#: 月份合約:恰四段 + 尾 YYYYMM(裸產品節點 `TC.F.TWF.CDF` 與價差六段形天然排除)
_STKFUT_MONTH_RE = re.compile(r"^TC\.F\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<ym>\d{6})$")
#: 節點名尾綴的標的股號(「台積電(2330)」/「小型元大台灣50(0050)」)
_STKFUT_NAME_RE = re.compile(r"^(?P<name>.+?)\((?P<code>\w{4,6})\)$")
_MINI_PREFIX = "小型"


def _stkfut_months(node: dict) -> list[str]:
    """節點 Contracts → 月份清單(升冪)。

    只收 `TC.F.TWF.<SYMBOL>.<YYYYMM>`,且 prod 必須等於節點自己的 SYMBOL ——
    價差節點的六段形、產品層裸節點、以及 HOT 支借來的別檔合約全部落在外面。
    `InstrumentID` 同索引非 null 為第二判準(真合約才有期交所碼)。
    """
    symbol = node.get("SYMBOL")
    contracts = node.get("Contracts") or []
    ids = node.get("InstrumentID") or []
    months: list[str] = []
    for i, raw in enumerate(contracts):
        if not isinstance(raw, str):
            continue
        m = _STKFUT_MONTH_RE.match(raw)
        if m is None or m.group("prod") != symbol:
            continue
        if i < len(ids) and ids[i] is None:
            continue
        months.append(m.group("ym"))
    return sorted(set(months))


def parse_stkfut_catalog(res: dict) -> dict[str, dict]:
    """QUERYALLINSTRUMENT(Type="Fut2")回應 → `{股號: {name, std, mini}}`。

    樹形實讀(2026-06-30 dump,873KB;fixture 見 tests/fixtures/catalog_fut2_sample.json):
    `Instruments.Node` 有兩支 —— `ENG="StockFutures"`(真合約,節點帶 `SYMBOL`)與
    `ENG="StockFutures(F2)"`(**個股期貨價差**,節點名逐字同名、無 SYMBOL、Contracts
    是六段跨月形)。價差支誤收會讓下拉長出訂不到的合約,而 TC4 對不存在的 symbol
    照回 `Success: OK`(§8)→ 失效樣態是「選了之後一片空白」毫無錯誤訊號,所以這裡
    **顯式**只走真合約支,不用「有沒有解析成功」當過濾。

    std / mini:同一股號可有標準(CDF)與小型(QFF)兩個產品節點,以節點名的「小型」
    前綴判別。另有除權息調整契約(國喬1 = EE1)同樣掛在同一股號下 —— 它們的 SYMBOL
    尾碼不是 "F",不得蓋掉原始契約(調整契約的契約單位非 2,000,下單層另有閘)。
    """
    branches = (res.get("Instruments") or {}).get("Node") or []
    nodes: list[dict] = []
    for branch in branches:
        if isinstance(branch, dict) and branch.get("ENG") == _STKFUT_BRANCH:
            nodes.extend(n for n in (branch.get("Node") or []) if isinstance(n, dict))
    grouped: dict[str, list[tuple[str, str, dict]]] = {}
    for node in nodes:
        symbol = node.get("SYMBOL")
        if not isinstance(symbol, str) or not symbol:
            continue  # HOT(熱門月)節點:Contracts 合法但無 SYMBOL,不是產品
        m = _STKFUT_NAME_RE.match(str(node.get("CHT") or ""))
        if m is None:
            continue
        grouped.setdefault(m.group("code"), []).append((symbol, m.group("name"), node))
    result: dict[str, dict] = {}
    for code, entries in grouped.items():
        minis = [e for e in entries if e[1].startswith(_MINI_PREFIX)]
        stds = [e for e in entries if not e[1].startswith(_MINI_PREFIX)]
        # 原始契約(SYMBOL 尾 "F")優先於除權息調整契約(EE1);同類再以 SYMBOL 定序
        stds.sort(key=lambda e: (not e[0].endswith("F"), e[0]))
        minis.sort(key=lambda e: (not e[0].endswith("F"), e[0]))
        if not stds:
            continue
        std_symbol, std_name, std_node = stds[0]
        months = _stkfut_months(std_node)
        if not months:
            continue
        entry: dict = {
            "name": std_name,
            "std": {"prod": std_symbol, "contracts": months},
            "mini": None,
        }
        if minis:
            mini_symbol, _, mini_node = minis[0]
            mini_months = _stkfut_months(mini_node)
            if mini_months:
                entry["mini"] = {"prod": mini_symbol, "contracts": mini_months}
        result[code] = entry
    return result


def _walk_strings(node: object, acc: list[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _walk_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            _walk_strings(v, acc)
    elif isinstance(node, str):
        acc.append(node)


class TC4QuoteSource:
    """QuoteSource 實作;api/session 可注入(測試),預設 lazy 連線真 TC4。"""

    def __init__(
        self,
        port: str = TC4_DEFAULT_PORT,
        *,
        api: Any | None = None,
        session: str | None = None,
        poll_wait_secs: float = 1.0,
        backfill_date: str | None = None,
        # 等鎖上界**必須大於** `_REQ_TIMEOUT_MS`/1000(X-2a):**健康慢路徑**的持鎖
        # 上界 ≈ 吃滿 RCVTIMEO(send 在 localhost REQ 上只有對端死了才會塞到 SNDTIMEO,
        # 那條路棄連線本來就正確;形式上的持鎖上界是 send+recv = 2×10s,且逾時方
        # `_dispose` 會以同一把 timeout 再等鎖一次 —— 首個輸家最壞 12+12s,但 `_api`
        # 已先 null,後來者拿到的是新鎖,級聯止於一人)。等鎖上界比健康上界小,就代表
        # 「一個正常但慢的 REQ」必然讓其餘等鎖者 `_dispose` 整條連線 —— 三個 REQ
        # 生產者(群組回補 / basis sweep / Fut2 目錄)在 boot 必然重疊,級聯是常態。
        # 取捨:毒鎖(KeepAlive Pong 無 try/finally)的偵測延遲從 5s 拉長到 12s ——
        # 那條路本來就要重建連線,晚 7 秒發現可接受;而誤殺健康連線是每次都發生。
        lock_timeout_secs: float = DEFAULT_LOCK_TIMEOUT_SECS,
        # ---- REALTIME 零推播自癒(預設全關;門檻由各子類建構子帶)----
        #: R1「整條 session 靜默」門檻(秒);None = 自癒整體關閉
        heal_silence_secs: float | None = None,
        #: R2「單 symbol 曾有推播後靜默」門檻(秒);None = R2 關
        heal_symbol_silence_secs: float | None = None,
        #: 只在回 True 時自癒(盤外不 churn)
        heal_active: Callable[[], bool] = always_active,
        #: **逐 symbol** 的自癒閘(N051):同一條 session 上各腿的交易時段不同時,
        #: session 級的 `heal_active` 表達不了 —— 台期交國外指數腿(SXF/UDF/SPF/UNF)
        #: 在自己休市段照樣落進 R2「從未推播」母體,每 300s 一發 UNSUB+SUB。
        #: 回 False 的 symbol 整輪不進母體(R1 的全場靜默判定也扣掉它)。
        heal_symbol_active: Callable[[str], bool] = always_symbol_active,
        heal_poll_secs: float = 5.0,
    ) -> None:
        self._port = port
        self._api = api
        self._session = session
        self._sub_port: str | None = None
        self._poll_wait = poll_wait_secs
        self._lock_timeout = lock_timeout_secs
        self._backfill_date = backfill_date.replace("-", "") if backfill_date else None
        self._on_tick: Callable[[Tick], None] | None = None
        self._subscribed: set[str] = set()
        self._listener: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_msg = time.monotonic()
        self._lock = threading.Lock()
        # _api/_session 指標讀寫專用小鎖:_dispose 的 check-then-clear 與
        # _ensure_connected 的指標發布必須原子,否則 REQ 失敗的 worker 可能清掉
        # _check_stale 剛建好的新連線(round-2 P1)。與 self._lock 分離,
        # _check_stale 持大鎖中經 _req → _dispose 不會自鎖。
        self._api_lock = threading.Lock()
        self.reconnects = 0
        self.on_reconnect: Callable[[], None] | None = None
        self._heal_silence = heal_silence_secs
        self._heal_symbol_silence = heal_symbol_silence_secs
        self._heal_active = heal_active
        self._heal_symbol_active = heal_symbol_active
        self._heal_poll = heal_poll_secs
        #: symbol → 最後一則 REALTIME 推播的 monotonic(`_realtime_msg` 單點記錄)
        self._last_push: dict[str, float] = {}
        #: symbol → 最後一次 SUBQUOTE 成功的 monotonic(剛重掛不算靜默)
        self._sub_at: dict[str, float] = {}
        self._heal_attempts: dict[str, int] = {}
        self._heal_next: dict[str, float] = {}
        #: symbol → 訂閱窗變體序號(0 = 原窗);見 `_apply_variant`
        self._window_variant: dict[str, int] = {}
        #: symbol → **常駐**窗位移(N050)。與 variant 的差別:variant 是自癒的節奏
        #: (會被 `_note_push` / `_unsub` 清),offset 是「這條 session 對這個 symbol
        #: 用哪一把 key」的身分,一經登記就不再變 —— TXO runtime 用它把 `TXF.HOT`
        #: 的訂閱窗與 futures session 的盤別窗錯開成兩把 key(見 `subscribe`)。
        self._window_offset: dict[str, int] = {}
        self._healer: threading.Thread | None = None

    # ---- 連線 ----

    def _ensure_connected(self) -> None:
        """未連線則建立連線;**check + 建立 + 發布整段持 `_api_lock`**(N259)。

        舊碼的 check(指標為 None)在鎖外,只有發布在鎖內 —— `_check_stale` 的重連與
        任何 REQ 生產者同時進來時,兩邊各自看到 None、各自 `QuoteAPI(...)`,後發布的
        那個蓋掉先發布的:**落敗者永遠不會被 `Disconnect()`**,它的 KeepAlive 執行緒
        續跑到 process 結束(§0a:不 Disconnect 則 process 不退),而兩條 session 都
        對同一批 symbol 持著 refcount key,零錯誤訊號。

        持鎖跨越 `Connect()`(最壞 = `_REQ_TIMEOUT_MS`)的代價:同期的 `_connection()`
        / `_req` 讀側要等這段。那條路本來就只能拿到 None → `ConnectionError`,等完拿到
        **新連線**嚴格優於當場失敗。鎖序不變(`self._lock` → `_api_lock`,見 `_dispose`)。

        `_stop` 早退:`close()` 之後在途的 executor 工作項(futures `_retry_subscribe` /
        stock 健檢 timer)不得再把連線建回來 —— 建回來就是一條沒人會關的 KeepAlive。
        """
        with self._api_lock:
            if self._api is not None and self._session is not None:
                return
            if self._stop.is_set():
                raise ConnectionError("TC4 quote source 已收工,不再重建連線")
            sys.path.insert(
                0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY")
            )
            from tcoreapi_mq import QuoteAPI  # type: ignore[import-untyped]

            api = QuoteAPI(TC4_APPID, TC4_SKEY)
            # Connect() 內部裸 recv → context 級 timeout 讓之後建立的 socket 全部繼承;
            # LINGER=0 讓失敗被棄的 api 在 GC term 時不為 pending LOGIN 無限阻塞
            # (同 tc4_trade R2-2 / F-1 防護;timeout 值依據見 _REQ_TIMEOUT_MS 註解)
            api.context.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
            api.context.setsockopt(zmq.SNDTIMEO, _REQ_TIMEOUT_MS)
            api.context.setsockopt(zmq.LINGER, 0)
            try:
                q = api.Connect(self._port)
            except (zmq.ZMQError, OSError) as exc:
                raise ConnectionError(f"TC4 quote connect failed: {exc}") from exc
            if q.get("Success") != "OK":
                raise ConnectionError(f"TC4 login failed: {q}")
            if self._stop.is_set():
                # 收工在 `Connect()` 期間發生(`close()` 第一步就 set `_stop`,接著才
                # 排隊等這把鎖)—— **不得發布**:發布出去的是一條 `close()` 已經看不到
                # 的連線(它拿到鎖時 `_api` 才被填,但那時 UNSUB 迴圈已經跑完),
                # KeepAlive 執行緒續跑到 process 不退(review ST2)。就地收掉 —— 持 `api.lock`
                # 收(review A6):KeepAlive 在 `Connect()` 內就起來了,`Pong` 隨時會拿同一把鎖
                # 用同一顆 socket。
                self._disconnect_locked(api)
                raise ConnectionError("TC4 quote source 已收工,棄置在途連線")
            self._api = api
            self._session = q["SessionKey"]
            self._sub_port = q["SubPort"]
        logger.info("TC4 connected, session=%s", q["SessionKey"][:8])

    def _dispose(self, api: Any) -> None:
        """REQ 失敗即棄連線:timeout 後 REQ EFSM 壞狀態不可重用,若不丟棄,SUB 有 tick
        流動時 _check_stale 永不觸發 → REQ 通道永久壞死(review F2;同 tc4_trade _dispose)。

        不取 self._lock:_check_stale 持鎖中經 _rt_request 走到這裡,取鎖即自鎖。
        """
        with self._api_lock:
            if self._api is not api:
                return
            self._api = None
            self._session = None
        self._disconnect_locked(api)

    def _disconnect_locked(self, api: Any) -> None:
        """持 `api.lock` 才 `Disconnect()`;`_dispose` 與 `_ensure_connected` 的收工分支共用。

        wrapper 的 KeepAlive `Pong` 取同一把鎖、用同一顆 REQ socket —— 不持鎖就 close socket
        等於兩條執行緒同時碰 ZMQ socket(未定義行為)。取不到鎖(`Pong` 毒鎖)→ 跳過實體 close,
        洩漏優於 crash(同 `_dispose` 既有判定)。
        """
        if api.lock.acquire(timeout=self._lock_timeout):
            try:
                api.Disconnect()
            except (zmq.ZMQError, OSError):
                logger.exception("TC4 quote Disconnect failed (best-effort)")
            finally:
                api.lock.release()
        else:
            logger.warning("TC4 quote dispose: api.lock busy,跳過實體 close(洩漏優於 crash)")

    def _connection(self) -> tuple[Any, str]:
        """_api/_session 一致快照(_api_lock,與 _dispose/_ensure_connected 寫側對齊):
        重連瞬間不可拿到「新 api × 舊 session」的錯配對(review P2:讀側也持鎖)。
        未連線 → ConnectionError(不可裸 assert,見 _req)。"""
        with self._api_lock:
            api, session = self._api, self._session
        if api is None or session is None:
            raise ConnectionError("TC4 quote not connected")
        return api, session

    def _session_req(self, build: Callable[[str], dict], *, strip_prefix: bool = False) -> dict:
        """帶 SessionKey 的 REQ:同一把快照取 (api, session) 再送,配對一致。"""
        api, session = self._connection()
        return self._req(build(session), api=api, strip_prefix=strip_prefix)

    def _req(self, obj: dict, *, api: Any | None = None, strip_prefix: bool = False) -> dict:
        """自組電文 REQ:lock timeout + 錯誤收斂 ConnectionError + 失敗棄連線。

        wrapper 方法(QueryAllInstrumentInfo/GetHistory/SubHistory)內部 blocking
        acquire 無 timeout、無 try/finally,毒鎖下永久阻塞、timeout 下裸拋 → 一律
        不直呼 wrapper,REQ 全走這裡(review F1;同 tc4_trade 自組電文模式)。
        strip_prefix:GETHISDATA 回應帶 "<type>:" 前綴(wrapper GetHistory 同語意)。
        """
        if api is None:
            with self._api_lock:
                api = self._api
        if api is None:
            # dispose 後殘存呼叫:收斂 ConnectionError,不可裸 assert 讓
            # AssertionError 逃出 engine 的 except ConnectionError 攔截網
            raise ConnectionError("TC4 quote not connected")
        if not api.lock.acquire(timeout=self._lock_timeout):
            # wrapper KeepAlive Pong 無 try/finally,timeout 毒鎖 → 棄連線重建,
            # 而非永久卡死
            self._dispose(api)
            raise ConnectionError("TC4 quote api.lock timeout")
        error: Exception | None = None
        message = b""
        try:
            api.socket.send_string(json.dumps(obj))
            message = api.socket.recv()[:-1]
        except (zmq.ZMQError, OSError) as exc:
            error = exc
        finally:
            api.lock.release()
        if error is not None:
            self._dispose(api)
            raise ConnectionError(f"TC4 quote request failed: {error}") from error
        if strip_prefix:
            text = message.decode("utf-8")
            idx = text.find(":")
            return json.loads(text[idx + 1 :] if idx >= 0 else text)
        return json.loads(message)

    def _rt_window(self, symbol: str) -> tuple[str, str]:
        """REALTIME 訂閱窗(基底 = 台指盤別窗;子類覆寫這一支,不覆寫 `_rt_request`)。

        窗是**唯一**的覆寫點:`_rt_request` 之後還要套自癒的 window variant,
        子類各自複製一份 `_rt_request` 的話 variant 只會在基底那條路生效
        (失效樣態:個股/海外腿的自癒永遠換不到新 key,零錯誤訊號)。
        """
        return session_window(session_key())

    def _apply_variant(self, symbol: str, window: tuple[str, str]) -> tuple[str, str]:
        """套自癒的窗變體:總位移 k 先加在 EndTime,吃不下的餘量再推 StartTime。

        TC4 的訂閱 refcount 鍵是 `symbol|DataType|StartTime|EndTime`,**換窗 = 換一把
        count 0 的新 key**,才會觸發上游 `ReqSubQuote`(repro.md 實驗 D/G)。所以規則
        唯一的硬要求是「k = 1/2/3 與原窗**恆為四把互異的鍵**」——

        - EndTime += min(k, 23−end);餘量 r = k − 位移量。
        - r > 0 且 StartTime − r ≥ 00 → StartTime −= r(夜盤窗 06–22 走這條)。
        - StartTime 已頂到 00(全天窗 00–23)→ 改 StartTime += r(往前推是 no-op,
          舊實作在這裡整組塌成同一把 key,而失效樣態是自癒照跑但上游永不重掛)。

        **歷史路徑(`_sub_history` / `_get_history`)不吃 variant** —— 回補窗與 REALTIME
        窗是不同 DataType 的兩把鍵,動它只會讓回補改抓別的區間。

        總位移 k = **常駐 offset(`_window_offset`,N050)+ 自癒 variant**:兩者疊在
        同一條階梯上,登記了 offset 的 symbol 其 variant 0/1/2/3 仍是四把互異的鍵。
        """
        k = self._window_variant.get(symbol, 0) + self._window_offset.get(symbol, 0)
        if k <= 0:
            return window
        start, end = window
        start_hour, end_hour = int(start[8:10]), int(end[8:10])
        shift = min(k, _WINDOW_HOUR_MAX - end_hour)
        end_hour += shift
        rest = k - shift
        if rest:
            back = start_hour - rest
            start_hour = back if back >= _WINDOW_HOUR_MIN else start_hour + rest
        return f"{start[:8]}{start_hour:02d}", f"{end[:8]}{end_hour:02d}"

    def _rt_request(self, request: str, symbol: str) -> dict:
        window = self._apply_variant(symbol, self._rt_window(symbol))
        return self._session_req(lambda session: build_rt_request(request, session, symbol, window))

    # ---- REALTIME 零推播自癒(watchdog;root cause 見 repro.md)----

    def _heal_enabled(self) -> bool:
        return self._heal_silence is not None or self._heal_symbol_silence is not None

    def _start_healer(self) -> None:
        """watchdog thread(daemon;`_stop` 為止)。heal 全關時不起。"""
        if self._healer is not None or not self._heal_enabled():
            return
        self._healer = threading.Thread(target=self._heal_loop, daemon=True)
        self._healer.start()
        logger.info(
            "TC4 REALTIME 自癒 watchdog 啟動(R1=%s R2=%s poll=%.0fs)",
            self._heal_silence,
            self._heal_symbol_silence,
            self._heal_poll,
        )

    def _heal_loop(self) -> None:
        while not self._stop.wait(self._heal_poll):
            try:
                self._heal_tick(time.monotonic())
            except Exception:  # noqa: BLE001 - watchdog 邊界:漏接一次 = 自癒從此消失
                # `_heal` 只吞 TC4 通訊類例外;邏輯 bug(KeyError / 型別)逃到這裡
                # 就是 thread 靜靜死掉,而它守的正是「零推播且零錯誤訊號」那條路。
                logger.exception("TC4 自癒 watchdog 巡檢例外(續行)")

    def _heal_tick(self, now: float) -> None:
        """一輪判定(`now` 可注入 → 測試不靠真時鐘)。

        R1(session 級):訂閱非空、**全部** symbol 都靜默超過門檻、且最近一次重掛也
        超過門檻 → 整批重掛,**命中即 return**(同一輪不再走 R2:兩條規則各記一次
        attempts 會讓退避與換窗階梯整條錯位)。09:01 那次事故(reap 殭屍 → 上游整批
        退訂)就是這個形狀。
        R2(symbol 級):靜默超過門檻就重掛,母體 = 「曾有推播」**或**「訂閱已超過
        門檻卻從未推播」—— 後者是 08-18 個股面的實際形狀(部分死亡:同 session 其他
        腿還在流,R1 因此不成立,而那些從未推播的腿舊母體收不到,永遠沒人救)。
        深價外契約那種本來就沒成交的 symbol 由 `heal_symbol_silence_secs=None` 整條
        豁免(TXO session),不靠窄母體擋。
        """
        if not self._heal_active():
            return
        # tuple() 先取快照再排序:巡檢期間 engine 可能訂/退訂(集合的單步操作在 GIL
        # 下原子,但迭代中被改會 RuntimeError)。定序 → log 與重掛順序可預期。
        #
        # 逐 symbol 閘(N051)在**母體形成處**扣除,不是在 R2 迴圈裡 continue ——
        # R1 的「全部 symbol 都靜默」若把休市腿算進去,它們的恆靜默會把還在流動的腿
        # 一起拖進整批重掛(而 R1 命中即 return,R2 那一輪也一起跳過)。
        subs = sorted(s for s in tuple(self._subscribed) if self._heal_symbol_active(s))
        if not subs:
            return
        t1 = self._heal_silence
        if t1 is not None:
            quiet_since = max((self._last_push.get(s, 0.0) for s in subs), default=0.0)
            resub_since = max((self._sub_at.get(s, 0.0) for s in subs), default=0.0)
            if quiet_since < now - t1 and resub_since < now - t1:
                for sym in subs:
                    if self._heal_next.get(sym, 0.0) <= now:
                        self._heal(sym, now, t1)
                return  # R1 已整批重掛,同一輪不再走 R2
        t2 = self._heal_symbol_silence
        if t2 is None:
            return
        for sym in subs:
            silent_since = self._last_push.get(sym, self._sub_at.get(sym))
            if silent_since is None:  # 尚未成功訂閱過 → 沒有可比對的基準
                continue
            if silent_since < now - t2 and self._heal_next.get(sym, 0.0) <= now:
                self._heal(sym, now, t2)

    def _next_variant(self, symbol: str, *, bump: bool) -> int:
        """下一發要用的窗變體序號(1 → 2 → 3 → 1 …;窗開得再寬也回得來)。"""
        variant = self._window_variant.get(symbol, 0)
        return (variant % _HEAL_VARIANT_CYCLE) + 1 if bump else variant

    def _heal_resub(self, symbol: str, *, bump_variant: bool) -> bool:
        """重掛一發(watchdog 與個股健檢共用的基底;回「有沒有真的送出去」)。

        `bump_variant` → **先對舊窗發 UNSUBQUOTE 再換窗**:換窗後才 UNSUB 送的是新窗,
        舊窗那把 key 的 count 就永遠停在 >0(對 count 0 的 key 發 UNSUB 無害 —— TC4 log
        09:00:52 `Remove count:0` 之後 Add 照常,既有的 UNSUB→SUB 冪等路徑天天在做)。

        `symbol in self._subscribed` 的檢查必須**在鎖內**且緊貼 `_resub`:watchdog 取完
        快照到這裡之間 engine 可能已經退訂,重掛會留下沒有任何持有者的幽靈訂閱。

        **不得拋**:watchdog / 健檢 timer 都在自己的 thread 上跑,一次 REQ 例外炸出去
        就等於自癒從此消失,而失效樣態(零推播)恰恰是沒有錯誤訊號的那一種。
        """
        try:
            with self._lock:  # 與 _check_stale 互斥:重連換 session 時不得同時重掛
                if symbol not in self._subscribed:
                    return False
                if bump_variant:
                    self._rt_request("UNSUBQUOTE", symbol)  # 舊窗 key 先歸零
                    self._window_variant[symbol] = self._next_variant(symbol, bump=True)
                self._resub(symbol)
        except (ConnectionError, zmq.ZMQError, OSError, json.JSONDecodeError) as exc:
            logger.warning("TC4 自癒重掛失敗 %s: %s(下輪退避重試)", symbol, exc)
            return False
        return True

    def _heal(self, symbol: str, now: float, base: float) -> None:
        """watchdog 的單一 symbol 重掛 + 記帳(退避 base·2^(n-1),封頂 300s)。

        記帳(`_heal_attempts` / `_heal_next`)是 **watchdog 專屬**:個股健檢(R3)另有
        自己的一組,共用會讓個股的 10/20/40/60s 退避被 watchdog 的階梯推到 300s。
        兩邊只共用 `_window_variant`(那是「這把 key 現在是哪一把」的事實,不是節奏)。
        """
        attempts = self._heal_attempts.get(symbol, 0) + 1
        self._heal_attempts[symbol] = attempts
        self._heal_next[symbol] = now + min(base * 2 ** (attempts - 1), _HEAL_BACKOFF_CAP)
        bump = attempts >= HEAL_VARIANT_AFTER
        silence = now - max(self._last_push.get(symbol, 0.0), self._sub_at.get(symbol, 0.0))
        logger.warning(
            "TC4 REALTIME 零推播自癒:%s 靜默 %.0fs → 重掛(attempt %d, window_variant=%d)",
            symbol,
            silence,
            attempts,
            self._next_variant(symbol, bump=bump),
        )
        if self._heal_resub(symbol, bump_variant=bump):
            self._sub_at[symbol] = now

    def _note_push(self, symbol: str) -> None:
        """收到推播 = 這把 key 是活的:清 attempts/退避,**保留 variant**。"""
        self._last_push[symbol] = time.monotonic()
        if symbol in self._heal_attempts:
            self._heal_attempts.pop(symbol, None)
            self._heal_next.pop(symbol, None)

    # ---- QuoteSource 介面 ----

    def list_series(self) -> list[SeriesInfo]:
        self._ensure_connected()
        res = self._session_req(
            lambda session: {
                "Request": "QUERYALLINSTRUMENT",
                "SessionKey": session,
                "Type": "Opt",
            }
        )
        if res.get("Success") != "OK":
            raise ConnectionError(f"TC4 QUERYALLINSTRUMENT failed: {res.get('ErrMsg')}")
        strings: list[str] = []
        _walk_strings(res, strings)
        leaves = sorted({s for s in strings if s.startswith("TC.O.TWF.")})
        return group_series(leaves)

    def list_stock_futures(self) -> dict[str, dict]:
        """個股期合約清單(Type="Fut2";stkfut-contracts SC-1)。

        `StockSource` Protocol **之外**的能力(個股訂閱面用不到)—— server 以
        `getattr` 接線,fake source 不必為此實作 Protocol 方法。

        ⚠ **秒級同步呼叫且全程持 session 鎖**(`_session_req`;Opt 的同款查詢實測
        1.93s)—— 期間這條 session 上的其他 REQ(訂閱 / SubHistory)全部排隊。呼叫端
        一律走 `StkfutCatalog`(當日 cache + 單飛 + boot 預熱),不要在請求路徑上直呼。
        """
        self._ensure_connected()
        res = self._session_req(
            lambda session: {
                "Request": "QUERYALLINSTRUMENT",
                "SessionKey": session,
                "Type": "Fut2",
            }
        )
        if res.get("Success") != "OK":
            raise ConnectionError(f"TC4 QUERYALLINSTRUMENT(Fut2) failed: {res.get('ErrMsg')}")
        return parse_stkfut_catalog(res)

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        self._ensure_connected()
        if self._backfill_date:
            # TXO_BACKFILL_DATE 休市日回補:指定日期固定日盤窗,不隨當下時段走
            start, end = f"{self._backfill_date}00", f"{self._backfill_date}06"
        else:
            start, end = session_window(session_key())
        # 先對全鏈送 SubHistory 讓 TC4 平行備資料再逐檔收割 —
        # 逐檔「Sub → 等 → 收」實測 280 檔 ~10 分鐘,先全訂可砍掉大部分等待(Phase 4 自評)
        for contract in series.contracts:
            self._sub_history(contract.symbol, start, end)
        # round 制收割:空 symbol 不逐檔空等(舊制每空檔 6 查 + 5 sleep,夜盤深價外
        # 大量無成交會拖到分鐘級),等待改全局輪間 sleep;連續 _HARVEST_DRY_LIMIT 輪
        # 零進展 = 剩餘皆真無資料,早停(GETHISDATA 空頁無法區分「未備妥」與
        # 「無資料」,只能以進展停滯收斂)
        ticks: list[Tick] = []
        pending = [c.symbol for c in series.contracts]
        dry_rounds = 0
        for rnd in range(1, _HARVEST_ROUNDS + 1):
            if rnd > 1 and self._poll_wait:
                time.sleep(self._poll_wait * 0.5)  # 輪間等待放頂端:早停時不多睡尾輪
            still: list[str] = []
            for sym in pending:
                symbol_ticks = self._fetch_symbol_ticks(sym, start, end)
                if symbol_ticks:
                    ticks.extend(symbol_ticks)
                else:
                    still.append(sym)
            progressed = len(still) < len(pending)
            pending = still
            logger.info("backfill round %d: %d pending, %d ticks", rnd, len(pending), len(ticks))
            if not pending:
                break
            dry_rounds = 0 if progressed else dry_rounds + 1
            if dry_rounds >= _HARVEST_DRY_LIMIT:
                break
        logger.info("backfill done: %d ticks from %d symbols", len(ticks), len(series.contracts))
        return ticks

    def _sub_history(self, symbol: str, start: str, end: str, data_type: str = "TICKS") -> dict:
        return self._session_req(
            lambda session: {
                "Request": "SUBQUOTE",
                "SessionKey": session,
                "Param": {
                    "Symbol": symbol,
                    "SubDataType": data_type,
                    "StartTime": start,
                    "EndTime": end,
                },
            }
        )

    def _get_history(
        self, symbol: str, start: str, end: str, qry_index: str, data_type: str = "TICKS"
    ) -> dict:
        return self._session_req(
            lambda session: {
                "Request": "GETHISDATA",
                "SessionKey": session,
                "Param": {
                    "Symbol": symbol,
                    "SubDataType": data_type,
                    "StartTime": start,
                    "EndTime": end,
                    "QryIndex": qry_index,
                },
            },
            strip_prefix=True,
        )

    def _collect_history(
        self,
        sym: str,
        data_type: str,
        start: str,
        end: str,
        deadline_secs: float | None = None,
    ) -> HistoryResult:
        """SubHistory → 首頁 poll → QryIndex 收割;TC4 通訊失敗由 _req 收斂 ConnectionError。

        `deadline_secs` = 首頁備妥的等待預算。預設沿用舊值(`poll_wait*30` ≈ 30s),
        K 線路徑改傳 `_BARS_POLL_DEADLINE` —— 實測有資料的標的首頁 <1s 內就備妥,
        30s 預算只有在「TC4 根本沒有這檔」時才會用滿,而那條路徑一次要付兩段(歷史 +
        當日)= 60s。

        輪詢改**退避**:首輪落空後只睡 0.15s 再問,逐次加倍到原 `poll_wait` 封頂。
        舊制固定睡滿 1.0s,讓所有冷載入無條件多等約 0.9 秒。

        `poll_wait == 0` 是測試組態,語意 = 不等待 → 探測一次就回,不 busy loop。

        回 `HistoryResult(rows, timed_out)`:逾時路徑的空與「首頁備妥但 0 rows」是
        不同的事,呼叫端要能分(bars 三態 status)。
        """
        self._sub_history(sym, start, end, data_type)
        budget = deadline_secs if deadline_secs is not None else max(self._poll_wait * 30, 1.0)
        deadline = time.monotonic() + budget
        wait = min(_POLL_BACKOFF_START, self._poll_wait)
        while True:
            first = self._get_history(sym, start, end, "0", data_type)
            if first.get("HisData"):
                break
            remaining = deadline - time.monotonic()
            if wait <= 0 or remaining <= 0:
                logger.info(
                    "history %s(%s): %.1fs 內首頁未備妥,回空(timeout,非無資料)",
                    sym,
                    data_type,
                    budget,
                )
                return HistoryResult([], True)
            # 夾到 remaining:最後一輪不睡過頭,總等待恆不超過 budget
            time.sleep(min(wait, remaining))
            wait = min(wait * 2, self._poll_wait)

        def _page(qry_index: str) -> list[dict]:
            return self._get_history(sym, start, end, qry_index, data_type).get("HisData", [])

        rows: list[dict] = []
        for page in iter_qry_pages(_page):
            rows.extend(page)
        return HistoryResult(rows, False)

    def _fetch_symbol_ticks(self, symbol: str, start: str, end: str) -> list[Tick]:
        # 單發:首頁空即回空(未備妥的重試由 fetch_backfill 的 round 制統籌,不逐檔等)
        rows: list[dict] = []
        first = self._get_history(symbol, start, end, "0")
        if not first.get("HisData"):
            return []

        def _page(qry_index: str) -> list[dict]:
            return self._get_history(symbol, start, end, qry_index).get("HisData", [])

        for page in iter_qry_pages(_page):
            rows.extend(page)
        ticks = [t for r in rows if (t := parse_history_tick(symbol, r)) is not None]
        if rows and not ticks:
            # N092:「首頁非空即 break」的 ready-check 擋不住凍結 stub(窗內無資料時
            # 建立的 history 訂閱會回一列 Time = 訂閱建立時刻的假列,2026-08-14 實證)。
            # 落到這裡 = rows 非空但一筆都解不出來,呼叫端只看得到空 list,與「這檔
            # 今天真沒成交」無從分辨。**控制流不變**(round 制本來就把「0 tick」當
            # still-pending 再試一輪),只補上這條路上唯一的 grep 判準。
            logger.warning("history %s:%d 列全數解析失敗(疑似凍結 stub)", symbol, len(rows))
        return ticks

    def _resub(self, sym: str) -> None:
        """UNSUB→SUB 冪等重掛(逐 symbol 訂閱路徑共用;stock/futures/corr 三 source)。

        **失敗語意是契約**:`stock_engine._acquire` 靠 ConnectionError 回滾 refcount,
        不可改回傳 bool。下方 TXO 序列版 `subscribe` 刻意是 warn+continue(整條序列
        不因單一 symbol 失敗而全斷),故不走這裡。
        """
        self._rt_request("UNSUBQUOTE", sym)
        r = self._rt_request("SUBQUOTE", sym)
        if r.get("Success") != "OK":
            raise ConnectionError(f"SUBQUOTE fail {sym}: {r.get('ErrMsg')}")
        self._subscribed.add(sym)
        self._sub_at[sym] = time.monotonic()

    def _unsub(self, sym: str) -> None:
        """已訂閱才退訂(未訂閱 = no-op),並清掉這個 symbol 的自癒帳。

        帳留著的話,下一輪訂閱會**帶著上一輪的 variant 與 attempts** 起跑:訂到一把
        沒人知道的窗、第一次靜默就直接換窗,而 `_last_push` 的舊時戳讓它一進場就被
        判成靜默。UNSUBQUOTE 必須先送完再清 —— 送的窗要用當下的 variant。
        """
        if sym in self._subscribed:
            self._rt_request("UNSUBQUOTE", sym)
            self._subscribed.discard(sym)
        for book in (
            self._last_push,
            self._sub_at,
            self._heal_attempts,
            self._heal_next,
            self._window_variant,
        ):
            book.pop(sym, None)

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self._ensure_connected()
        self._on_tick = on_tick
        self._start_listener()
        symbols = [c.symbol for c in series.contracts]
        # TXF 現貨獨立於序列(DR-13);每次都重掛(UNSUB→SUB 冪等)— rollover 重訂閱
        # 必須讓 spot 也換新時段窗,否則其訂閱窗永遠停在最初時段(review F2)
        symbols.append(SPOT_SYMBOL)
        # N050:`TXF.HOT` 同時被 futures session 以**盤別窗**持有。同一把 key 兩個持有者
        # → 單 session 的 UNSUB→SUB 永遠到不了 SumSubCount 0,TC4 就不會 `ReqSubQuote`
        # 重掛上游 feed,要等自癒爬到第 3 次的 window variant 才救得回(多兩輪 backoff)。
        # 這裡把 TXO 這一邊常駐位移一小時 = 兩把互不干擾的 key。**只位移 TXO 這邊**:
        # 兩邊一起位移還是同一把,而期貨面的訂閱窗是它自己的既有行為,不動。
        self._window_offset[SPOT_SYMBOL] = SPOT_WINDOW_OFFSET
        for sym in symbols:
            self._rt_request("UNSUBQUOTE", sym)
            r = self._rt_request("SUBQUOTE", sym)
            if r.get("Success") != "OK":
                logger.warning("SUBQUOTE fail %s: %s", sym, r.get("ErrMsg"))
                continue
            self._subscribed.add(sym)
            self._sub_at[sym] = time.monotonic()
        logger.info("subscribed %d symbols (series=%s)", len(self._subscribed), series.series_id)

    def unsubscribe(self, series: SeriesInfo) -> None:
        for contract in series.contracts:  # 不含 TXF(DR-13)
            if contract.symbol in self._subscribed:
                self._rt_request("UNSUBQUOTE", contract.symbol)
                self._subscribed.discard(contract.symbol)

    def close(self) -> None:
        t0 = time.monotonic()
        self._stop.set()
        with self._api_lock:
            connected = self._api is not None
        lock_wait = time.monotonic() - t0
        if connected:
            total, done = len(self._subscribed), 0
            # 關機預算的可觀測面(review A1):lifespan 那頭只看得到「這條 session 花了 n 秒」,
            # 分不出是等鎖(在途 `Connect()`)還是 REQ 逾時(TC4 半死)—— 處置不同,前者等
            # 它自己走完,後者要去看 TC4;上界推導見 `close_worst_secs`。**進場先印一行**:
            # 卡在 REQ 上被硬殺時,事後只剩這行能指認是哪條 session(review SP3)。
            logger.info("TC4 quote close:等 api 鎖 %.2fs,開始 UNSUBQUOTE %d 檔", lock_wait, total)
            t_unsub = time.monotonic()
            for sym in list(self._subscribed):
                try:
                    self._rt_request("UNSUBQUOTE", sym)
                except (zmq.ZMQError, ConnectionError, OSError, json.JSONDecodeError):
                    # 收工路徑:退訂失敗多半是連線已死,其餘 symbol 也會失敗;
                    # 停止嘗試但仍必須收尾 Disconnect(§0a)
                    logger.exception("UNSUBQUOTE failed during close: %s", sym)
                    break
                done += 1
            logger.info(
                "TC4 quote close:UNSUBQUOTE %d/%d 檔 %.2fs", done, total, time.monotonic() - t_unsub
            )
        # 失敗路徑 _req 內已 _dispose(含 best-effort Disconnect)→ _api 可能已是
        # None,不可無條件 Disconnect(round-2 P0);仍在線才由此關(§0a KeepAlive
        # 生命週期:不關則 process 不退出)
        with self._api_lock:
            api, session = self._api, self._session
        if api is None:
            return
        t_tail = time.monotonic()
        # 只注入 api 沒 session 的建構路徑:跳過 LOGOUT,Disconnect 照走(review SP4)
        if session is not None:
            self._logout(api, session)
        self._dispose(api)
        # 第三行計時:LOGOUT(≤ `_LOGOUT_TIMEOUT_MS`)+ Disconnect(KeepAlive term,無上界)——
        # 這一行**沒印出來**就是卡在 term() 上(`close_worst_secs` 說明的不計段)
        logger.info("TC4 quote close:LOGOUT + Disconnect %.2fs", time.monotonic() - t_tail)

    def _logout(self, api: Any, session: str) -> None:
        """退訂後、Disconnect 前對 TC4 送 LOGOUT(fix/tc4-logout)。

        wrapper 的 `Disconnect()` 只關 KeepAlive 執行緒 + socket,**不送 LOGOUT**;
        TC4 端那張 session 票要等 ~60 s 的 `ExecuteCheckPingTime` 才被 reap
        (2026-08-25 17:15:29 Ctrl+C:708 筆 UNSUB 貼秒,`RemoveLoginInfo` 全在
        17:16:31)。reap 會把該 session 獨持的 refcount key 歸零、連帶帶走 symbol 的
        上游 feed(tc4-market-facts)—— 退訂先做完就沒有東西可帶走,但票留著等 reap
        仍是一個 60 s 的髒窗,run.ps1 的 graceful 判準也對不上。

        TC4 對 LOGOUT 回 `{"Reply":"LOGOUT","Success":"OK"}`(2026-08-26 00:56 零訂閱
        probe 實證),所以走 `_req`(send + recv;lock timeout / 失敗棄連線同其他 REQ),
        但 recv 上界縮到 `_LOGOUT_TIMEOUT_MS`(理由見常數)。
        best-effort:失敗只 log,後續 dispose 照走(`_req` 失敗路徑已 `_dispose`)。
        """
        setsockopt = getattr(api.socket, "setsockopt", None)
        if setsockopt is not None:
            setsockopt(zmq.RCVTIMEO, _LOGOUT_TIMEOUT_MS)
        try:
            reply = self._req({"Request": "LOGOUT", "SessionKey": session}, api=api)
        except ConnectionError as exc:
            # `_req` 失敗路徑已 _dispose(含 Disconnect),這裡只剩告知;與下一分支同嚴重度、
            # 同前綴 "TC4 quote LOGOUT" 供 grep 對帳(review ST5)
            logger.warning("TC4 quote LOGOUT 失敗:%s(session 留到 TC4 reap)", exc)
            return
        if reply.get("Success") != "OK":
            logger.warning("TC4 quote LOGOUT 未被接受:%s(session 留到 TC4 reap)", reply)

    # ---- REALTIME 監聽(thread)----

    def _start_listener(self) -> None:
        if self._listener is not None:
            return
        if self._sub_port is None:
            # 注入 api/session 而未真連線的路徑:收斂 ConnectionError,
            # 不讓 AssertionError 逃出 engine 的 except ConnectionError 攔截網
            raise ConnectionError("TC4 quote listener 需要真連線的 SubPort")
        self._listener = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener.start()
        self._start_healer()

    def _realtime_msg(self, raw: str) -> dict | None:
        """原始電文 → REALTIME 訊息 dict;無 topic 分隔 / 非 JSON / 非 REALTIME → None。

        **回整則 msg 而非 `Quote`**:空 Quote 的現況是照送 `_on_message({})`,
        回 Quote 會讓呼叫端只能用 truthy 判定,把空 Quote 一起吞掉(行為改動)。
        """
        idx = raw.find(":")
        if idx < 0:
            return None
        try:
            msg = json.loads(raw[idx + 1 :])
        except json.JSONDecodeError:
            return None
        if msg.get("DataType") != "REALTIME":
            return None
        # 自癒的推播時鐘記在這裡:四個子類的 handle_raw 都經過本方法,單點記錄
        # (各自在 handle_raw 記 = 下次新增 source 必漏,而漏了完全沒有訊號)
        quote = msg.get("Quote")
        if isinstance(quote, dict):
            symbol = quote.get("Symbol")
            if isinstance(symbol, str) and symbol:
                self._note_push(symbol)
        return msg

    def handle_raw(self, raw: str) -> None:
        """SUB socket 一則原始電文 → TXO Tick 分派(listener 與測試共用)。

        子類覆寫這一支即可共用整個 `_listen_loop`(generation-following 的重連跟隨
        邏輯 2026-07-20 盤中修過一次,四份各自持有等於下次要同步改四處)。
        """
        msg = self._realtime_msg(raw)
        if msg is None:
            return
        tick = parse_realtime(msg.get("Quote", {}))
        if tick is not None and self._on_tick is not None:
            self._on_tick(tick)

    def _listen_loop(self) -> None:
        import zmq

        ctx = zmq.Context()
        sock: zmq.Socket | None = None
        bound_port: str | None = None
        while not self._stop.is_set():
            if sock is None or self._sub_port != bound_port:
                # 重連會換 SubPort(_check_stale → _ensure_connected);listener 不跟隨
                # 則新 session 推播(含 PING)永遠收不到 → 30 秒週期無限重連
                # (2026-07-20 盤中實證 30 次;同 tc4_trade R3-1 的跟隨語意)
                if sock is not None:
                    sock.close(linger=0)
                sock = ctx.socket(zmq.SUB)
                sock.connect(f"tcp://127.0.0.1:{self._sub_port}")
                sock.setsockopt_string(zmq.SUBSCRIBE, "")
                sock.setsockopt(zmq.RCVTIMEO, 1_000)
                bound_port = self._sub_port
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                self._check_stale()
                continue
            self._last_msg = time.monotonic()
            self.handle_raw(raw)
        if sock is not None:
            sock.close(linger=0)
        ctx.term()

    def _check_stale(self) -> None:
        """PING 都收不到超過閾值 → 判斷線,重連 + 重訂閱 + 通知 on_reconnect(補回遺失段)。"""
        if time.monotonic() - self._last_msg < _STALE_THRESHOLD_SECS:
            return
        backoff = 1.0
        while not self._stop.is_set():
            logger.warning("TC4 stale >%ss, reconnecting...", _STALE_THRESHOLD_SECS)
            try:
                with self._lock:
                    old = self._api
                    if old is not None:
                        # 舊 api 拆除統一走 _dispose(round-2 P2:消滅無鎖 Disconnect
                        # 與 _dispose 的雙路徑並發)
                        self._dispose(old)
                    self._ensure_connected()
                    resub = list(self._subscribed)
                    self._subscribed = set()
                    for sym in resub:
                        self._rt_request("UNSUBQUOTE", sym)  # 冪等,與 subscribe 路徑一致(Alt-4)
                        r = self._rt_request("SUBQUOTE", sym)
                        if r.get("Success") == "OK":
                            self._subscribed.add(sym)
                            self._sub_at[sym] = time.monotonic()
                        else:
                            # 掉訂品的復原靠 engine 端 on_reconnect 對帳(futures);
                            # 這裡至少留 grep 判準,不再靜默蒸發(回溯審 P1-3)
                            logger.warning("TC4 reconnect resubscribe %s failed: %s", sym, r)
                self.reconnects += 1
                self._last_msg = time.monotonic()
                if self.on_reconnect is not None:
                    self.on_reconnect()
                logger.info("TC4 reconnected (total=%d)", self.reconnects)
                return
            except (ConnectionError, OSError, zmq.ZMQError):
                # zmq.ZMQError:Disconnect / wrapper 路徑仍可能裸拋,漏接會殺 listener
                logger.exception("reconnect attempt failed, backoff %.0fs", backoff)
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, _RECONNECT_BACKOFF_CAP)
