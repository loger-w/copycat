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


_STALE_THRESHOLD_SECS = 30.0
_RECONNECT_BACKOFF_CAP = 60.0
# context 級 REQ timeout:app 死亡時 Connect/_rt_request 的裸 recv 才可返回、重連迴圈
# 才可被 _stop 中斷。10s = 實測最重呼叫 QUERYALLINSTRUMENT(Opt) 1.93s 的 5 倍裕度;
# GetHistory 分頁實測 max 1.1ms(3,482 次、10.7 萬 rows)不受影響(2026-07-20 probe)。
_REQ_TIMEOUT_MS = 10_000
# 回補收割輪數上限與零進展早停(fetch_backfill round 制;空頁無法區分未備妥/無資料)
_HARVEST_ROUNDS = 16
_HARVEST_DRY_LIMIT = 3


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
        lock_timeout_secs: float = 12.0,
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

    # ---- 連線 ----

    def _ensure_connected(self) -> None:
        if self._api is not None and self._session is not None:
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY"))
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
        with self._api_lock:
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

    def _rt_request(self, request: str, symbol: str) -> dict:
        window = session_window(session_key())
        return self._session_req(lambda session: build_rt_request(request, session, symbol, window))

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
                    "history %s(%s): %.1fs 內首頁未備妥,回空", sym, data_type, budget
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
        return [t for r in rows if (t := parse_history_tick(symbol, r)) is not None]

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

    def _unsub(self, sym: str) -> None:
        """已訂閱才退訂(未訂閱 = no-op)。"""
        if sym in self._subscribed:
            self._rt_request("UNSUBQUOTE", sym)
            self._subscribed.discard(sym)

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self._ensure_connected()
        self._on_tick = on_tick
        self._start_listener()
        symbols = [c.symbol for c in series.contracts]
        # TXF 現貨獨立於序列(DR-13);每次都重掛(UNSUB→SUB 冪等)— rollover 重訂閱
        # 必須讓 spot 也換新時段窗,否則其訂閱窗永遠停在最初時段(review F2)
        symbols.append(SPOT_SYMBOL)
        for sym in symbols:
            self._rt_request("UNSUBQUOTE", sym)
            r = self._rt_request("SUBQUOTE", sym)
            if r.get("Success") != "OK":
                logger.warning("SUBQUOTE fail %s: %s", sym, r.get("ErrMsg"))
                continue
            self._subscribed.add(sym)
        logger.info("subscribed %d symbols (series=%s)", len(self._subscribed), series.series_id)

    def unsubscribe(self, series: SeriesInfo) -> None:
        for contract in series.contracts:  # 不含 TXF(DR-13)
            if contract.symbol in self._subscribed:
                self._rt_request("UNSUBQUOTE", contract.symbol)
                self._subscribed.discard(contract.symbol)

    def close(self) -> None:
        self._stop.set()
        with self._api_lock:
            connected = self._api is not None
        if connected:
            for sym in list(self._subscribed):
                try:
                    self._rt_request("UNSUBQUOTE", sym)
                except (zmq.ZMQError, ConnectionError, OSError, json.JSONDecodeError):
                    # 收工路徑:退訂失敗多半是連線已死,其餘 symbol 也會失敗;
                    # 停止嘗試但仍必須收尾 Disconnect(§0a)
                    logger.exception("UNSUBQUOTE failed during close: %s", sym)
                    break
        # 失敗路徑 _req 內已 _dispose(含 best-effort Disconnect)→ _api 可能已是
        # None,不可無條件 Disconnect(round-2 P0);仍在線才由此關(§0a KeepAlive
        # 生命週期:不關則 process 不退出)
        with self._api_lock:
            api = self._api
        if api is not None:
            self._dispose(api)

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
