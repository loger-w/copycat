"""FuturesQuoteSource:TXF/MXF/TMF HOT REALTIME 資料源(capital-order design §10)。

繼承 TC4QuoteSource 複用連線/REQ 全域互斥/_dispose/stale 重連(同 stock_source 案 A:
不動 tc4.py)。REALTIME 窗沿用基底 session 窗 — 期貨與 TXO 同時段(日盤 08:45–13:45 /
夜盤 15:00–05:00,live/session 時區事實),不需個股日盤窗覆寫。

listener 覆寫為原始 Quote dict 分派(book/meta 都要,不能只回 Tick;同 stock_source
手法)。ZMQ session 第 4 條:TXO quote + stock + index + futures(design §13)。
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Callable

from copycat.live.futures_models import PRODUCTS
from copycat.live.river_backfill import collect_1k_minutes
from copycat.live.stock_source import Bar, parse_1k_bars, parse_dk_bars
from copycat.live.tc4 import BARS_POLL_DEADLINE, TC4QuoteSource, always_active
from copycat.tc4common import TC4_DEFAULT_PORT

logger = logging.getLogger(__name__)


#: 台指期日盤分鐘域(08:45 開盤 → 首根終點標記 0846;13:45 收盤,1346–1350 clamp)。
#: 個股那把尺是 0901–1330,套上去會靜默丟掉開盤前 15 分與 13:31–13:45。
#: 夜盤(15:00–05:00)不在本輪 scope,落在域外自然被丟(change-spec §5)。
FUTURES_MINUTE_DOMAIN = ("0846", "1345", "1350")

#: 近全段(日盤 + 夜盤兩半;futures-allday design §1.2)。**段本身不跨午夜** ——
#: 夜盤拆成 1501–2359 與 0000–0500 兩段,台北日期由 `_taipei_dt_key` 的 datetime
#: 轉換決定,段只管 HHMM 的落點與收盤 clamp。
FUTURES_ALLDAY_DOMAIN: tuple[tuple[str, str, str], ...] = (
    ("0846", "1345", "1350"),  # 日盤(= FUTURES_MINUTE_DOMAIN)
    ("1501", "2359", "2359"),  # 夜盤前半(15:00 開盤 → 首根終點標記 1501)
    ("0000", "0500", "0505"),  # 夜盤後半(05:00 收盤,0501–0505 clamp 併入 0500)
)


def futures_symbol(product: str) -> str:
    """產品碼 → TC4 期貨樹熱門月 symbol(台指期產品碼 = TXF,非 FITX;07-20 實證)。"""
    return f"TC.F.TWF.{product}.HOT"


class FuturesQuoteSource(TC4QuoteSource):
    def __init__(
        self,
        port: str = TC4_DEFAULT_PORT,
        *,
        api: Any | None = None,
        session: str | None = None,
        poll_wait_secs: float = 1.0,
        heal_silence_secs: float | None = 30.0,
        heal_symbol_silence_secs: float | None = 60.0,
        heal_active: Callable[[], bool] = always_active,
    ) -> None:
        # 自癒預設不設盤別閘:三檔 HOT 日夜盤都該有推播,盤外最壞 churn = 3 symbol /
        # 300s;而 09:01 事故正是「新 server 沿用殭屍建的 feed」那種盤前/盤初形狀。
        # prod 由 `app._default_futures_source` 補上交易日曆閘(假日整天不 churn)。
        super().__init__(
            port,
            api=api,
            session=session,
            poll_wait_secs=poll_wait_secs,
            heal_silence_secs=heal_silence_secs,
            heal_symbol_silence_secs=heal_symbol_silence_secs,
            heal_active=heal_active,
        )
        self._on_message: Callable[[dict], None] | None = None

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    # ---- 逐品訂閱(UNSUB→SUB 冪等;失敗 raise 供 engine 降級)----

    def subscribe_symbol(self, product: str) -> None:
        self._ensure_connected()
        if self._sub_port is not None:
            # 真連線才有 SubPort;漏啟 listener = 訂閱成功但永收不到推播(07-21 實證)
            self._start_listener()
        self._resub(futures_symbol(product))

    def unsubscribe_symbol(self, product: str) -> None:
        self._unsub(futures_symbol(product))

    def subscribe_leaf(self, product: str, ym: str) -> None:
        """補訂實際月份 leaf 契約(TC.F.TWF.<p>.<YYYYMM>)。

        HOT 與 TXO runtime 的 spot 訂閱同 symbol 時,TC4 只推一邊(2026-07-28 盤中實證,
        同 process 四 session);leaf 字串不同即無衝突。冪等同 subscribe_symbol。"""
        self._ensure_connected()
        if self._sub_port is not None:
            self._start_listener()
        self._resub(f"TC.F.TWF.{product}.{ym}")

    def subscribe_all(self) -> None:
        for product in PRODUCTS:
            self.subscribe_symbol(product)

    # ---- 江波圖當日回補(index-river-chart SC-4)----

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]:
        """當日 1K → [(台北 minute_end, close 毫點)]。

        台指的回補**必須從這條 session 發** —— `TC.F.TWF.TXF.HOT` 的 REALTIME 訂閱在這裡,
        同 symbol 跨 session 只推一邊(CLAUDE.md §8),從別的 session 問同一檔有把推播
        搶走的風險。
        """
        self._ensure_connected()
        return collect_1k_minutes(
            sub_history=self._sub_history,
            get_history=self._get_history,
            symbol=futures_symbol(product),
            poll_wait=self._poll_wait,
        )

    # ---- K 線歷史(index-board N-2)----

    def fetch_bars_range(
        self,
        product: str,
        tf: str,
        start_date: str,
        end_date: str,
        *,
        session: str = "day",
    ) -> list[Bar]:
        """期指 K 線 bar(`tf` = "D" 日 K / "1" 分 K;start/end = YYYY-MM-DD 含端點)。

        **必須從這條 session 發**:`TC.F.TWF.<prod>.HOT` 的 REALTIME 訂閱在這裡,
        TC4 同 symbol 跨 session 只推一邊(CLAUDE.md §8)—— 從別的 session 問同一檔
        有把推播搶走的風險,而失效樣態是「訂閱成功但零推播」,零錯誤訊號。

        窗:**只有 SubHistory 的 start/end** 用 `YYYYMMDDHH` 全天範圍(與 stock_source
        的歷史窗同款)。**不覆寫 `_rt_window`** —— 期貨 REALTIME 訂閱窗維持盤別窗
        (檔頭:期貨與 TXO 同時段),動它會改到期貨 tab 三檔的既有訂閱行為。

        分鐘域走 `FUTURES_MINUTE_DOMAIN`(08:46–13:45),不是個股的 0901–1330:
        套個股的尺會丟掉開盤前 15 分並把 13:31–13:35 錯併進 13:30。

        `session="allday"`(僅 tf="1" 有意義)= 近全段:域換成 `FUTURES_ALLDAY_DOMAIN`,
        且**取數窗前移到 (start_date − 1 日) 的 UTC 16 時** —— 台北日 D 的凌晨段
        (00:00–05:00)落在 UTC 日 D−1 的 16:00–21:00,不前移就整段抓不到,而失效樣態
        是「圖照畫、只是每天凌晨五小時憑空消失」。

        窗兩端各自多收什麼(方向不對稱,TZ-1 更正):

        - **低端**多收 UTC (start−1) 16:00–23:59 = **台北 start_date 的 00:00–07:59**
          —— 正是要救回來的那一段,全部落在 [start_date, end_date] 內,不會被 filter 掉。
          台北 start−1 的夜盤前半(15:01–23:59)= UTC (start−1) 07:01–15:59,**根本不在
          窗內**,不是靠 filter 擋掉的。
        - **高端**多收 UTC end_date 16:00–23:00 = **台北 end_date+1 的 00:00–07:00**
          —— 這才是 filter 真正擋掉的那段(次日凌晨盤)。

        所以 parse 後的台北日期 filter 是**單邊**防線(擋高端);低端不需要它。
        """
        self._ensure_connected()
        sym = futures_symbol(product)
        allday = tf == "1" and session == "allday"
        if allday:
            prev = _dt.date.fromisoformat(start_date) - _dt.timedelta(days=1)
            start = f"{prev:%Y%m%d}16"
        else:
            start = f"{start_date.replace('-', '')}00"
        end = f"{end_date.replace('-', '')}23"
        if tf == "1":
            rows = self._collect_history(sym, "1K", start, end, BARS_POLL_DEADLINE).rows
            if not allday:
                return parse_1k_bars(rows, FUTURES_MINUTE_DOMAIN)
            bars = parse_1k_bars(rows, FUTURES_ALLDAY_DOMAIN)
            return [b for b in bars if start_date <= b["t"][:10] <= end_date]
        return parse_dk_bars(self._collect_history(sym, "DK", start, end, BARS_POLL_DEADLINE).rows)

    # ---- listener:原始分派(覆寫 TXO 的 Tick 解析路徑;同 stock_source)----

    def handle_raw(self, raw: str) -> None:
        """SUB socket 一則原始電文 → REALTIME Quote dict 分派(listener 與測試共用)。"""
        msg = self._realtime_msg(raw)
        if msg is None:
            return
        if self._on_message is not None:
            self._on_message(msg.get("Quote", {}))
