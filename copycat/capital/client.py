"""群益下單 client —— 一條專屬 COM 執行緒(訊息幫浦 + 命令佇列),橋回 asyncio。

結構照搬 treading-king backend/services/capital_client.py(COM apartment 親和性:
所有群益呼叫都在 _run() 那條執行緒上),copycat 擴充:

- 期貨/選擇權寫入面:submit_future_order(SendFutureOrder/SendOptionOrder 分流)、
  期貨帳號自動發現(get_user_accounts 選 TF 市場)、期貨部位查詢(GetOpenInterestGW)
  串行接在 balance→profit 之後,證券+期貨合併一次 set_positions(兩段寫入)。
- 寫入紀律(design §3):master 閘 → 各閘(不過 = 審計 blocked 行 + raise
  CapitalGateBlockedError)→ 審計前置(失敗 raise AuditWriteError,錢沒動整筆失敗)
  → COM(10s timeout → 結果未知)→ 審計後置(失敗只 log,不改 OrderResult)。
- 審計走 copycat/server/audit.append_audit;檔名 prefix 耦合點只在 _audit() 一處
  (prefix="capital" → capital-*.jsonl,與 TC4 trade 的 orders-* 分檔)。
- 回報斷線 → degraded、不自動重連、不 clear store(design §8 / review R7)。
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import logging
import queue
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from copycat.capital.balance import (
    BalanceCollector,
    ProfitRow,
    merge_fut_positions,
    parse_open_interest_line,
    parse_profit_line,
)
from copycat.capital.close import build_close_order, build_future_close_order
from copycat.capital.com import CapitalCom
from copycat.capital.mapping import (
    exchange_product_of,
    future_price_str,
    is_option_contract,
    multiplier_of,
    to_futureorder_fields,
    to_stockorder_fields,
)
from copycat.capital.models import (
    BuySell,
    CancelOrderRequest,
    CapitalDownError,
    CapitalGateBlockedError,
    CapitalNotReadyError,
    CorrectPriceRequest,
    DecreaseQtyRequest,
    FutureOrderRequest,
    Market,
    OrderResult,
    Position,
    PositionCloseRequest,
    StockOrderRequest,
)
from copycat.capital.reply import SEC_MARKETS, parse_onnewdata
from copycat.capital.safety import (
    GateResult,
    SafetyConfig,
    check_cancel,
    check_correct_price,
    check_decrease,
    check_future_order,
    check_master,
    check_stock_order,
)
from copycat.capital.store import CapitalStore
from copycat.live.trade_models import BrokerRejectedError
from copycat.server.audit import AuditWriteError, append_audit
from copycat.trading_calendar import WEEKEND_ONLY, TradingCalendar, load_trading_calendar

logger = logging.getLogger(__name__)

#: 關機時 COM 執行緒 join 的上限(秒)。關機預算(`server/shutdown_budget.py`)的輸入之一:
#: lifespan 把 capital 排在 TC4 全部收完之後(N049),這個數字是預算表裡 TC4 之外的唯一一段。
COM_JOIN_TIMEOUT_SECS: float = 5.0

# 寫入命令等 COM 結果的上限:SendStockOrder 是同步呼叫,群益端掛起時 future 永不
# resolve → HTTP 請求永久懸掛,使用者不知道單送出沒、最容易誘發重送
_WRITE_TIMEOUT_S = 10.0

# 平倉 in-flight 窗口:送出後到回報進 store(或部位重查完成)前,擋同 key 再平倉
_CLOSE_INFLIGHT_S = 10.0

# balance→profit→OI 串行鏈的 pending 逾時:任一段卡住(rc!=0 已即時降級,這裡防
# 零事件的靜默卡死)就以已收資料寫入,部位快取不可永久滯留在暫存區
_PENDING_TIMEOUT_S = 8.0

# balance 段(GetRealBalance 發出 → 庫存收齊)的守門 deadline:這段沒有 pending
# 可看,鏈又可能零事件卡死(collector 沒收到任何列就不會 flush)→ 逾期即放行重查
_BALANCE_CHAIN_TIMEOUT_S = 10.0

# reply idx1 期權市場別(cancel/correct/decrease 的 market 交叉驗證用;
# 證券側用 reply.SEC_MARKETS 同一份)
_FUT_REPLY_MARKETS: frozenset[str] = frozenset({"TF", "TO", "OF", "OO"})

def _today_ymd() -> str:
    """價格別記憶的日界 = 本機日曆日(與回報 idx23 同時區;idx23 跨日語意未實證,見 `store.note_price_type`)。
    抽成 module 函式讓測試注入固定值 —— 測試自己也算 `time.strftime` 的話,
    等於拿被測程式的實作驗它自己(review r1 IMPL-5)。"""
    return time.strftime("%Y%m%d")


#: 交易日曆單例(lazy):價格別標籤是唯一讀者,啟動時不必為它做 IO。
#: `None` = 尚未載入;載入失敗降級 `WEEKEND_ONLY` 後就不再重試(每次送單重讀壞檔沒有意義)。
_CALENDAR: TradingCalendar | None = None

#: 夜盤時段界(台灣期交所盤後 15:00–翌 05:00)。用時段而不是精確的商品交易時間表:
#: 這裡只是「標籤該拿哪一天去比對」,多算或少算一小時的後果是標籤缺一個字。
_NIGHT_OPEN_HOUR = 15
_NIGHT_CLOSE_HOUR = 5


def _calendar() -> TradingCalendar:
    """交易日曆(lazy 單例)。載入失敗 → 只擋週末 + WARNING:這條路徑跑在 COM 執行緒的
    送單結果處理上,為了一個顯示標籤炸掉它會讓「單送出去了但結果沒進 store」。
    catch 的是 `load_trading_calendar` 明列會拋的兩類(壞檔 ValueError / 讀檔 OSError),
    不是裸 except —— 其他例外照樣往上。"""
    global _CALENDAR
    if _CALENDAR is None:
        try:
            _CALENDAR = load_trading_calendar()
        except (OSError, ValueError):
            logger.warning("交易日曆載入失敗,價格別標籤的日界降級為只擋週末", exc_info=True)
            _CALENDAR = WEEKEND_ONLY
    return _CALENDAR


def _side_code(buy_sell: object) -> str | None:
    """請求端 `BuySell`("buy"/"sell")→ 回報端 idx6 首碼("B"/"S");其餘(含 None)→ None。"""
    return {"buy": "B", "sell": "S"}.get(buy_sell) if isinstance(buy_sell, str) else None


def _trade_ymd(when: datetime | None = None) -> str:
    """該時刻**所屬的交易日** YYYYMMDD(N075:價格別標籤的第二個比對候選)。

    夜盤 23:50 送出的單,本機日曆日是今天、交易日是明天;群益回報 idx23 走哪一種日界未實證
    (跨日事件是否變值亦未實證),所以兩個都記(見 `store.note_price_type`)。
    - ≥15:00 → 次日起算的下一個交易日(週五夜盤 → 下週一);
    - <05:00 → 含今日的下一個交易日(週六凌晨 = 週五夜盤的延續 → 下週一);
    - 其餘(日盤時段)→ 含今日往回的最近交易日 = 今天。
    """
    now = datetime.now() if when is None else when
    cal = _calendar()
    if now.hour >= _NIGHT_OPEN_HOUR:
        return cal.next_trading_day(now.date() + timedelta(days=1)).strftime("%Y%m%d")
    if now.hour < _NIGHT_CLOSE_HOUR:
        return cal.next_trading_day(now.date()).strftime("%Y%m%d")
    return cal.last_trading_day(now.date()).strftime("%Y%m%d")


_WriteReq = (
    StockOrderRequest
    | FutureOrderRequest
    | CancelOrderRequest
    | CorrectPriceRequest
    | DecreaseQtyRequest
    | PositionCloseRequest
)
_ComCall = Callable[[], tuple[str, int]]
_Cmd = tuple[_ComCall, "asyncio.Future[tuple[str, int]]"]


def _mask_account(value: str | None) -> str | None:
    """帳號遮罩:只露末 4 碼(status route/log 共用語意;帳號本體不得外流)。"""
    if not value:
        return None
    return "****" + value[-4:]


def _settle(
    fut: asyncio.Future[tuple[str, int]],
    result: tuple[str, int] | None = None,
    exc: BaseException | None = None,
) -> None:
    """在 event loop 上 resolve 寫入 future。逾時側(wait_for)可能已 cancel,
    done 的 future 再 set 會炸 InvalidStateError 進 loop exception handler。"""
    if fut.done():
        return
    if exc is not None:
        fut.set_exception(exc)
    elif result is not None:
        fut.set_result(result)


class CapitalClient:
    def __init__(
        self,
        com: CapitalCom,
        *,
        user_id: str,
        password: str,
        full_account: str,
        env: str,
        safety: SafetyConfig,
        audit_base: Path,
    ) -> None:
        self._com = com
        self._user_id = user_id
        self._password = password
        self._full_account = full_account
        self._env = env
        self._safety = safety
        self._audit_base = audit_base
        self._cmd_q: queue.Queue[_Cmd | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._status = "starting"  # starting | ok | degraded | error
        self._last_error: str | None = None
        self._futures_account: str | None = None  # _init_com 自動發現(TF 市場)
        self.store = CapitalStore()  # 委託/部位快取:回報事件寫入、REST 讀
        self._broadcast: Callable[[dict[str, object]], None] | None = None
        # 最近一筆成交到達的 monotonic(F5 觀測):回查鏈三段收尾各印「自成交起 N ms」,
        # 讓真成交的耗時有數字可報;鏈落地即清,60s 定時輪詢那些輪不印(避免洗版)。
        self._fill_seen_at: float | None = None
        self._balance = BalanceCollector(on_complete=self._on_balance_complete, name="balance")
        self._profit = BalanceCollector(
            on_complete=self._on_profit_complete, parse=parse_profit_line, name="profit"
        )
        self._oi = BalanceCollector(
            on_complete=self._on_oi_complete, parse=parse_open_interest_line, name="oi"
        )
        self._balance_due: float | None = None  # monotonic;成交後 debounce 重查
        self._balance_inflight_until: float | None = None  # balance 段守門 deadline(None=不在段內)
        self._balance_last_ts: float = 0.0  # 定時重查用(0=啟動後第一圈就查)
        self._close_inflight: dict[str, float] = {}  # key → monotonic 解鎖時刻(只在 loop 上碰)
        self._pending_sec: list[Position] | None = None  # 證券部位暫存,期貨回完才合併發布
        #: 損益列回填蒐證去重:(股號, 種類) → 上次印過的均價(每 60 s 一輪同值不洗版)
        self._avg_logged: dict[tuple[str, str | None], float] = {}
        self._pending_deadline: float | None = None  # pending 逾時強制發布(watchdog)
        # 放棄輪旗標:collector.abandon() 已開遲到終止符的時間窗,下一次發查詢的 reset
        # 要保留它(COM 回呼無查詢識別 → 遲到的 `##` 只能靠這個窗擋;見 collector docstring)。
        # 只有查詢真的出手(rc==0)才清,否則窗會在鏈沒啟動的那一輪被白白關掉。
        self._balance_abandoned = False
        self._profit_abandoned = False
        self._oi_abandoned = False

    # ------------------------------------------------------------------ 狀態

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def futures_account(self) -> str | None:
        return self._futures_account

    def status_view(self) -> dict[str, object]:
        """GET /api/capital/status 欄位(design §6);disabled 情境由 route 處理(client None)。"""
        return {
            "status": self._status,
            "env": self._env,
            "account_masked": _mask_account(self._full_account),
            "futures_account_masked": _mask_account(self._futures_account),
            "order_enabled": self._safety.order_enabled,
        }

    def set_broadcast(self, fn: Callable[[dict[str, object]], None]) -> None:
        """fn(payload) —— 由 app 注入,通常包成 call_soon_threadsafe + broadcaster。"""
        self._broadcast = fn

    def _emit(self, payload: dict[str, object]) -> None:
        """broadcast 失敗不可炸 COM 執行緒/寫入鏈:推播是輔助面,log 留痕即可。"""
        if self._broadcast is None:
            return
        try:
            self._broadcast(payload)
        except Exception:
            logger.exception("capital broadcast 例外(已忽略):%s", payload.get("event"))

    def _set_status(self, new: str, *, error: str | None = None) -> None:
        if error is not None:
            self._last_error = error
        if new == self._status:
            return
        self._status = new
        if new == "ok":
            # 重登/重連:狀態斷過就沒有「進行中的鏈」可守,舊旗標會擋住重查。
            # 目前唯一的 ok caller 是 _init_com(啟動時全為初值,此分支等同 no-op);
            # 這裡是 reconnect 落地時的預留 —— 清點必須與 _finalize_positions 同組
            # (三個旗標),只清 inflight 會留下半清狀態卡在 _pending_sec 守門判上,
            # 鏈永遠不再放行(pending 段無 collector 事件時只有 _poll_pending 能解,
            # 而它同樣看 _pending_deadline)。
            # 放棄輪欠帳同組清:斷線前記的欠帳跨不過重連(那一輪的 `##` 隨連線一起沒了),
            # 留著只會白吞重連後第一個合法的空回應 → 幽靈部位多掛一輪(review F5)。
            self._balance_inflight_until = None
            self._pending_sec = None
            self._pending_deadline = None
            self._balance_abandoned = False
            self._profit_abandoned = False
            self._oi_abandoned = False
            # 走 `clear()` 不走 `reset()`(N018):reset 的語意是「發新查詢」,會把
            # collector 標成 `_awaiting = True` —— 但重連落地這一刻**沒有任何在途查詢**,
            # 標了之後下一次 pending watchdog 的 abandon() 就記帳成功,白吞一輪
            # 合法的空回應(帳戶真的沒部位時多掛一輪幽靈)。
            self._balance.clear()
            self._profit.clear()
            self._oi.clear()
        self._emit(
            {"event": "capital_status", "data": {"status": new, "last_error": self._last_error}}
        )

    # ------------------------------------------------------------------ 審計

    def _audit(self, record: dict[str, object]) -> None:
        # 檔名 prefix 耦合點只在這一行:群益審計落 capital-*.jsonl,
        # 與 TC4 trade 的 orders-*.jsonl 同 base 分檔
        append_audit(self._audit_base, record, when=date.today(), prefix="capital")

    def _record(
        self,
        action: str,
        req: _WriteReq,
        *,
        blocked: str | None = None,
        result: OrderResult | None = None,
    ) -> dict[str, object]:
        return {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "env": self._env,
            "action": action,
            "req": dataclasses.asdict(req),
            "blocked": blocked,
            "result": dataclasses.asdict(result) if result is not None else None,
        }

    async def _audit_blocked(self, action: str, req: _WriteReq, reason: str) -> None:
        """拒單審計:寫不進去照樣 raise AuditWriteError — 錢沒動,寧可整筆失敗。
        to_thread:同步寫檔不可卡 event loop(review B6;例外原樣透傳)。"""
        await asyncio.to_thread(self._audit, self._record(action, req, blocked=reason))

    async def _audit_after(self, action: str, req: _WriteReq, result: OrderResult) -> None:
        """命令已出手後的審計:寫檔失敗只能記 log,
        不可把已送進群益的單回報成失敗(誘發重送)。"""
        try:
            await asyncio.to_thread(self._audit, self._record(action, req, result=result))
        except Exception:
            logger.exception("審計後置寫入失敗(action=%s)— 委託已送出,結果未入帳: %s", action, result)

    def _on_late_result(
        self, action: str, req: _WriteReq, fut: asyncio.Future[tuple[str, int]]
    ) -> None:
        """timeout / route 取消後 COM 晚到的結果:補一行後置審計(late=true)+ warning
        (review B1),並補記價格別(review r1 IMPL-4)。
        done_callback 在 loop 上跑,同步 append_audit 可接受(罕見路徑)。"""
        if fut.cancelled():
            return
        exc = fut.exception()
        if exc is not None:
            result = OrderResult(
                ok=False, code=-1, message=f"COM 例外: {type(exc).__name__}: {exc}", seq_no=None
            )
        else:
            message, code = fut.result()
            ok = code == 0
            text = f"{self._com.return_code_message(code)} {message}".strip()
            result = OrderResult(
                ok=ok, code=code, message=text, seq_no=(message.strip() or None) if ok else None
            )
        logger.warning(
            "寫入結果晚到(action=%s, seq_no=%s, ok=%s)— 補記審計 late 行",
            action, result.seq_no, result.ok,
        )
        # 晚到的成功結果同樣要記價格別(review r1 IMPL-4):timeout / route 取消時
        # 「結果未知」不記是對的,但單真的成立了就得補 —— 否則一次 timeout 讓這張
        # 市價單在委託列表永久失標。刪/改/減量的 req 沒有 price_type → 不記。
        price_type = getattr(req, "price_type", None)
        if isinstance(price_type, str):
            stock_no = getattr(req, "stock_no", None)
            self._note_price_type(
                result,
                price_type,
                stock_no=stock_no if isinstance(stock_no, str) else None,
                buy_sell=_side_code(getattr(req, "buy_sell", None)),
            )
        record = self._record(action, req, result=result)
        record["late"] = True
        try:
            self._audit(record)
        except Exception:
            logger.exception("晚到結果審計寫入失敗(action=%s): %s", action, result)

    # ------------------------------------------------------------------ COM 事件(COM 執行緒)

    def _handle_reply(self, bstr_data: str) -> None:
        """OnNewData 主動回報 → store + 推 WS;成交(D)排程庫存重查。"""
        rec = parse_onnewdata(bstr_data)
        logger.info(
            "Capital reply: seq=%s stock=%s status=%s qty=%s",
            rec.seq_no, rec.stock_no, rec.status_label, rec.qty,
        )
        if (
            rec.status_raw != "C"
            and rec.alt_seq_no
            and rec.seq_no
            and rec.alt_seq_no != rec.seq_no
        ):
            # 真實樣本:預約單 KeyNo(idx0)≠ 尾欄序號(idx47),盤中單兩者相同。
            # 刪單回報(C)除外:尾欄是**刪單自己**的序號、KeyNo 是原委託,必定不同 ——
            # 2026-08-25 實錄 16 筆全是盤中單的刪單,沒有一筆是預約單(fix/tc4-logout…)。
            logger.warning("Capital reply: KeyNo=%s 尾欄序號=%s 不同(預約單?)", rec.seq_no, rec.alt_seq_no)
        t0 = time.monotonic()
        changed = self.store.apply_reply(rec)
        if rec.status_raw == "D":  # 成交 → debounce 重查(連續成交只查尾端一次)
            self._fill_seen_at = t0
            self._mark_balance_dirty()
            if changed:
                # 成交當下就把部位推出去(F5):回查鏈 0.5 s debounce + 三段串行往返是使用者
                # 「下單後倉位 / 均價很慢」的結構性來源;先推樂觀套用的部位,鏈落地再全量覆蓋。
                # `source: fill` 讓讀者分得出這是先到的還是券商確認的。**讀者目前 = 無**(前端
                # `useCapitalStream` 對 capital_position 一律 invalidate,不看 data);只有
                # `tests/capital/test_fill_latency.py` 用它分辨兩種推播。日後要拿掉就一併改測試。
                self._emit({"event": "capital_position", "data": {
                    "count": len(self.store.positions()),
                    "source": "fill",
                }})
                logger.info(
                    "成交樂觀套用部位: seq=%s stock=%s (%.1f ms)",
                    rec.seq_no, rec.stock_no, (time.monotonic() - t0) * 1000,
                )
            else:
                # 沒套的成交也要留痕(review Spec a):零股 / 無券 / 選擇權 / 期貨契約碼不明 /
                # 增量未滿張 / 無價 —— 正是最需要量「等回查鏈多久」的那些;不印就與現狀一樣看不見。
                logger.info(
                    "成交未樂觀套用(零股 / 無券 / 選擇權 / 契約碼不明 / 未滿張),等回查鏈: seq=%s stock=%s market=%s",
                    rec.seq_no, rec.stock_no, rec.market,
                )
        if rec.seq_no:
            self._emit({"event": "capital_order", "data": {
                "seq_no": rec.seq_no,
                "stock_no": rec.stock_no,
                "market": rec.market,
                "status_label": rec.status_label,
                "price": rec.price,
                "qty": rec.qty,
            }})

    def _handle_reply_disconnect(self, error_code: int) -> None:
        """OnDisconnect:回報主機斷線 → degraded(送單通道獨立可用),
        不自動重連、不 clear store(重播 backlog 前必須先 clear,另案;review R7)。"""
        msg = f"回報連線中斷 (code={error_code}),委託/成交回報停更"
        if self._status == "ok":
            self._set_status("degraded", error=msg)
        else:
            self._last_error = msg

    def _handle_balance(self, raw: str) -> None:
        self._balance.feed(raw)

    def _handle_profit(self, raw: str) -> None:
        self._profit.feed(raw)

    def _handle_open_interest(self, raw: str) -> None:
        self._oi.feed(raw)

    # ------------------------------------------------------------------ balance 鏈(COM 執行緒)

    def _mark_balance_dirty(self, delay_s: float = 0.5) -> None:
        self._balance_due = time.monotonic() + delay_s

    def _maybe_query_balance(self) -> None:
        """幫浦圈呼叫:due 到了或距上次查詢逾 60s → 發查詢。
        degraded(回報斷線)也要查 — 此時 60s 輪詢是部位唯一的更新來源。

        鏈(balance→profit→OI)進行中不得重發:第二次 GetRealBalance 吃群益 1019、
        且 _pending_sec 被覆寫 → 前一輪的 profit/OI 落到「遲到丟棄」分支,該輪部位
        均價/損益整批遺失。守門分兩段(deadline 只管 balance 段,pending 段有
        _poll_pending 保底);擋下時**不清 `_balance_due`** — 鏈結束後下一輪補查,
        成交不漏。"""
        if self._status not in ("ok", "degraded"):
            return
        now = time.monotonic()
        if self._pending_sec is not None:
            return
        if self._balance_inflight_until is not None:
            if now < self._balance_inflight_until:
                return
            # 零事件的死查詢:collector.poll 在 _last_feed is None 時早退、永不 flush,
            # deadline 逾期是唯一解卡通道(不放行 = 庫存永久停更)。
            # 解卡 = 放棄那一輪,但它的 `##` 可能才遲到(COM 回呼無查詢識別)→ 當下就
            # 記欠帳:此處到真正發下一次查詢之間可能隔到 60s(due 已清、stale 未到),
            # 那段空窗抵達的零列 `##` 照 flush 會把有庫存的部位清成空集合。
            self._balance.abandon()
            self._balance_abandoned = True
            # 守門旗標必須在同一條路徑清掉:留著的話幫浦圈每 50ms 重入這裡,
            # 每圈再 abandon 一次(欠帳窗一路往後推、staging 每圈被清空),
            # 真回應永遠拼不完整 —— 比原本「遲到 ## 清空一次」更糟(review F1/T1)。
            self._balance_inflight_until = None
        due = self._balance_due is not None and now >= self._balance_due
        stale = now - self._balance_last_ts >= 60.0
        if not due and not stale:
            return
        self._balance_due = None
        self._balance_last_ts = now  # 先記,失敗也不連發
        self._balance.reset(keep_abandoned=self._balance_abandoned)
        self._balance_inflight_until = now + _BALANCE_CHAIN_TIMEOUT_S
        rc = self._com.get_real_balance(self._user_id, self._full_account)
        if rc != 0:
            self._balance_inflight_until = None  # 鏈沒啟動,旗標不可佔著擋下一輪
            # due 在發查詢前已清 → 不重新武裝等於整筆成交的重查被吃掉(要等 60s
            # stale 才補),守門的「成交不漏」不變量破功。退避 1s 而非還原舊 due:
            # 舊 due 已過期,下一圈幫浦(50ms)就會再打一次 1019 成緊迴圈。
            self._mark_balance_dirty(1.0)
            logger.warning("GetRealBalanceReport rc=%s: %s", rc, self._com.return_code_message(rc))
            return
        # 查詢真的出手才交棒給 collector 的欠帳窗:rc≠0 時鏈沒啟動、放棄輪的 `##`
        # 還在路上,旗標先清掉會讓下一次成功查詢的 reset 順手關掉窗(review F3)
        self._balance_abandoned = False

    def _on_balance_complete(self, positions: list[Position]) -> None:
        """證券庫存收齊 → 暫存(不落 store)→ 串行接損益查詢(避開 1019 查詢處理中)。
        同檔多種庫存列(集保+融資並存)全數保留 — store 以 (股號, 種類) 為鍵,不需去重補償。"""
        self._pending_sec = positions
        self._log_chain_stage("庫存段收齊 %d 列", len(positions))
        self._pending_deadline = time.monotonic() + _PENDING_TIMEOUT_S
        self._balance_inflight_until = None  # 守門交棒給 pending 判(它有 8s 保底)
        self._balance_last_ts = time.monotonic()
        self._profit.reset(keep_abandoned=self._profit_abandoned)
        rc = self._com.get_profit_loss_gw(self._user_id, self._full_account)
        if rc != 0:
            logger.warning("GetProfitLossGWReport rc=%s: %s", rc, self._com.return_code_message(rc))
            self._query_open_interest()  # 損益跳過,鏈不可斷 — pending 靠期貨段收尾
            return
        self._profit_abandoned = False  # 出手才交棒(review F3,與 balance 段同語意)

    def _on_profit_complete(self, rows: list[ProfitRow]) -> None:
        """損益回填進 pending 證券部位(均價+含費稅息基底)→ 串行接期貨部位查詢。
        同檔多種類報告每種類一列:只回填同 kind 的列 — 資/券成本基礎不可混用。"""
        pending = self._pending_sec
        if pending is None:
            logger.warning("損益報告遲到(本輪 pending 已發布),丟棄 %d 列", len(rows))
            return
        self._log_chain_stage("損益段收齊 %d 列", len(rows))
        by_key = {(p.stock_no, p.kind): p for p in pending}
        for r in rows:
            # 兩段判別:查無股號 = 靜默(部位清單以即時庫存為權威,且 balance 側丟掉的列
            # ——零股不足 1 張 / 未知種類——在損益報告仍有列,合併成一段會每 60s 洗版 warning)
            same_no = [p for p in pending if p.stock_no == r.stock_no]
            if not same_no:
                continue
            p = by_key.get((r.stock_no, r.kind)) if r.kind is not None else None
            if p is None:
                # kind=None(未知標籤)也略過:寧缺均價,不可套錯成本基礎
                logger.warning(
                    "profit row 種類不符略過: %s 報告=%s(原文=%r) 部位=%s",
                    r.stock_no,
                    r.kind,
                    r.kind_raw,
                    [q.kind for q in same_no],
                )
                continue
            if self._avg_logged.get((r.stock_no, r.kind)) != r.avg_price:
                # 蒐證(2026-08-28 無券空單校準):群益給空單的「均價」是純賣價還是扣費稅淨收,
                # 08-28 8358 那筆平掉後查不回來 —— 每次值變動印一行,下一筆實錄就有第一手
                self._avg_logged[(r.stock_no, r.kind)] = r.avg_price
                logger.info(
                    "損益列回填 %s kind=%s avg=%s cost=%s pnl=%s price=%s(原 avg=%s,標籤原文=%r)",
                    r.stock_no,
                    r.kind,
                    r.avg_price,
                    r.cost,
                    r.pnl,
                    r.price,
                    p.avg_price,
                    r.kind_raw,
                )
            p.avg_price = r.avg_price
            # 群益損益試算「平均買進成本」已含買進手續費(prod 實證 4991 469.50 → 469.62):
            # 這一格是前端 positionEcon 不再加一次買費的唯一依據;漏寫 = wire 上 null =
            # 前端退回修前口徑(#118 在 prod 就是這樣死的)
            p.avg_source = "broker"
            p.pnl_base = r.pnl
            p.pnl_base_price = r.price
            p.pnl_cost = r.cost
        self._query_open_interest()

    def _query_open_interest(self) -> None:
        """期貨部位查詢(串行末段);無期貨帳號 → fut 恆空;查詢失敗 → 沿用上一輪
        fut 部位收尾(review A7:閃斷不可把面板期貨部位清空)。"""
        if self._futures_account is None:
            # 這條路徑**永遠不會發 OI 查詢** → 放棄輪旗標與 collector 欠帳留著只是殘留
            # 狀態(N018):日後 GetUserAccount 補到期貨帳號時,第一次
            # `reset(keep_abandoned=True)` 會把這個跨了不知多久的舊窗帶進新一輪,
            # 白吞一次合法的零列 OI 回應 = 期貨部位多掛一輪幽靈。
            self._oi_abandoned = False
            self._oi.clear()
            self._finalize_positions([])
            return
        self._oi.reset(keep_abandoned=self._oi_abandoned)
        rc = self._com.get_open_interest(self._user_id, self._futures_account)
        if rc != 0:
            logger.warning("GetOpenInterestGW rc=%s: %s", rc, self._com.return_code_message(rc))
            self._finalize_positions(self._stale_fut_positions())
            return
        self._oi_abandoned = False  # 出手才交棒(review F3,與 balance 段同語意)

    def _stale_fut_positions(self) -> list[Position]:
        """OI 查詢失敗/逾時:沿用 store 既有 fut 部位(review A7)。
        僅 OI 成功回報(_on_oi_complete)才全量覆蓋 fut 段。"""
        stale = [p for p in self.store.positions() if p.market == "fut"]
        logger.warning("期貨部位查詢未完成 — 沿用上一輪 fut 部位(%d 列)", len(stale))
        return stale

    def _on_oi_complete(self, rows: list[Position]) -> None:
        self._log_chain_stage("期貨部位段收齊 %d 列", len(rows))
        self._finalize_positions(merge_fut_positions(rows))

    def _finalize_positions(self, fut_rows: list[Position]) -> None:
        """證券(pending)+ 期貨合併,一次全量覆蓋 store(set_positions 全量語意,
        分兩次寫會互相蓋掉)→ 推 WS。"""
        sec = self._pending_sec
        if sec is None:
            logger.warning("期貨部位回報遲到(本輪 pending 已發布),丟棄 %d 列", len(fut_rows))
            return
        self._pending_sec = None
        self._pending_deadline = None
        self._balance_inflight_until = None  # 三個旗標同組清,且在 emit 前(例外不得滯留守門)
        merged = sec + fut_rows
        # 樂觀套用的期貨契約碼(`contract_from_fill`,真樣本僅一筆)與券商 OI 鍵對不對得上,
        # 只有真成交那一輪看得出來:落地前比一次鍵集合,不同就留一行(校準素材,F5)。
        opt_fut = {p.stock_no for p in self.store.positions() if p.market == "fut"}
        truth_fut = {p.stock_no for p in fut_rows}
        if self._fill_seen_at is not None and opt_fut != truth_fut:
            logger.info("期貨部位鍵差異(樂觀 vs 券商): %s vs %s", sorted(opt_fut), sorted(truth_fut))
        self.store.set_positions(merged)
        self._log_chain_stage("部位落地 %d 列", len(merged))
        self._fill_seen_at = None
        self._emit({"event": "capital_position", "data": {"count": len(merged)}})

    def _log_chain_stage(self, what: str, *args: object) -> None:
        """回查鏈進度(F5 觀測)。成交觸發的輪印 INFO 並附「自成交回報到達起 N ms」
        (量的是回報進 handler 的時刻,不是券商撮合時刻);60s 定時輪詢的輪降 DEBUG ——
        現狀成功路徑零 log,真成交的耗時無從量起。`what` 走 lazy %-args,與檔內其餘 log 同款。"""
        if self._fill_seen_at is None:
            logger.debug("balance 鏈: " + what, *args)
            return
        logger.info(
            "balance 鏈: " + what + "(自成交回報到達起 %.0f ms)",
            *args,
            (time.monotonic() - self._fill_seen_at) * 1000,
        )

    def _poll_pending(self) -> None:
        """幫浦圈 watchdog:損益/期貨查詢零事件卡死時,pending 逾時以已收資料寫入。
        (有收到部分事件的情況由各 collector 的 1s timeout poll 先 flush,不會走到這。)"""
        if self._pending_sec is None or self._pending_deadline is None:
            return
        if time.monotonic() >= self._pending_deadline:
            logger.warning("部位合併逾時(損益/期貨查詢未完成)— 以已收證券部位寫入")
            # 這一輪的損益/期貨段被放棄:兩者的 `##` 都可能才遲到(COM 回呼無查詢識別),
            # 下一輪收到會 flush 空集合 —— profit 空集合 = 均價/損益基底整批消失,
            # OI 空集合更會把期貨部位清光(A7 沿用邏輯繞不過 _on_oi_complete)。
            # 已正常收尾的那一段不會被多記:collector 的 `_awaiting` 在 flush 時就關了,
            # abandon() 對它是 no-op(review F4)—— 否則會白吞下一輪合法的空回應。
            self._profit.abandon()
            self._oi.abandon()
            self._profit_abandoned = True
            self._oi_abandoned = True
            self._finalize_positions(self._stale_fut_positions())  # fut 沿用上一輪(A7)

    # ------------------------------------------------------------------ 執行緒生命週期

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._thread = threading.Thread(target=self._run, daemon=True, name="capital-com")
        self._thread.start()

    def close(self) -> None:
        """關機:投終止訊號 + join(`COM_JOIN_TIMEOUT_SECS`)。執行緒側 finally 會降 status
        並 drain。join 逾時不 raise(review B5):COM 呼叫卡死時執行緒可能還活著,
        daemon 執行緒隨行程結束回收 — 不為等它阻塞關機。"""
        self._cmd_q.put(None)
        t = self._thread
        if t is not None:
            t.join(timeout=COM_JOIN_TIMEOUT_SECS)

    def _init_com(self) -> bool:
        """登入 + 憑證 + 連回報 + 帳號發現。成功回 True(ok/degraded);失敗 False(error)。"""
        try:
            self._com.setup(
                self._handle_reply,
                self._handle_balance,
                self._handle_profit,
                on_reply_disconnect=self._handle_reply_disconnect,
                on_open_interest=self._handle_open_interest,
            )
            rc = self._com.set_authority(2 if self._env == "test" else 0)
            if rc != 0:
                # 不呼叫/失敗的預設就是正式環境:test 模式失敗被吞 = 「測試單」
                # 可能落進真實市場,寧可不啟動;prod 失敗則預設即所求,記警告續行
                if self._env == "test":
                    raise RuntimeError("SetAuthority(test): " + self._com.return_code_message(rc))
                logger.warning(
                    "SetAuthority rc=%s: %s(預設即正式環境,續行)",
                    rc, self._com.return_code_message(rc),
                )
            code = self._com.login(self._user_id, self._password)
            if code != 0:
                raise RuntimeError("Login: " + self._com.return_code_message(code))
            rc = self._com.init_order()
            if rc != 0:
                # 吞掉會變成 status=ok 但每筆下單必敗的延遲爆炸,錯誤訊息也更難懂
                raise RuntimeError("SKOrderLib_Initialize: " + self._com.return_code_message(rc))
            code = self._com.read_cert(self._user_id)
            if code != 0:
                raise RuntimeError("ReadCertByID: " + self._com.return_code_message(code))
            # 連回報主機:漏這步 OnNewData 永遠不推,委託/成交/刪單回報全收不到。
            # 失敗不擋送單(送單獨立可用)→ degraded(design §2,與 treading-king
            # status=ok 不同:前端要能看出回報停更)。
            reply_error: str | None = None
            rc = self._com.connect_reply(self._user_id)
            if rc != 0:
                reply_error = "回報連線失敗: " + self._com.return_code_message(rc)
                logger.warning("Capital reply connect failed (rc=%s); 送單可用但收不到回報", rc)
            # 期貨帳號自動發現:TF 市場帳號;查無 → 期權寫入一律 no_futures_account 擋
            accounts = self._com.get_user_accounts()
            self._futures_account = next(
                (acct for mkt, acct in accounts if mkt.startswith("TF")), None
            )
            if self._futures_account is None:
                logger.warning("帳號清單查無期貨戶(TF)— 期權寫入動作將被 no_futures_account 擋下")
            if reply_error is not None:
                self._set_status("degraded", error=reply_error)
            else:
                self._set_status("ok")
            logger.info(
                "Capital login + cert OK (env=%s, status=%s, futures_account=%s)",
                self._env, self._status, "****" if self._futures_account else None,
            )
            return True
        except Exception as e:  # noqa: BLE001 — init 任一步失敗都收斂成 error 狀態,不炸執行緒
            self._set_status("error", error=f"{type(e).__name__}: {e}")
            logger.error("Capital init failed: %s", self._last_error)
            return False

    def _pump_once(self) -> None:
        """幫浦圈一輪(COM 執行緒)。例外吞掉+log:poll 的 flush 鏈會打 COM 查詢
        (斷線丟 COMError),單輪失敗不可殺執行緒 —— 執行緒死=寫入 future 永不
        resolve、status 卻還是 ok 的靜默失敗,真錢面板不可接受。"""
        try:
            self._com.pump()
            self._balance.poll()  # 沒等到結束標記的 flush 保險
            self._profit.poll()
            self._oi.poll()
            self._maybe_query_balance()  # 成交後 debounce / 60s 定時重查
            self._poll_pending()  # pending 合併逾時 watchdog
        except Exception:  # noqa: BLE001 — 單輪故障記 log 續命,見 docstring
            logger.exception("COM 幫浦圈例外(本輪略過)")
            time.sleep(1.0)  # 持續性故障時防 log 洪水

    def _run(self) -> None:
        # pythoncom 動態載入(對齊 com.py 慣例):CI/測試無 COM 環境時跳過 CoInitialize
        # (FakeCom 不需要 apartment;真實 SkcomCapitalCom 環境必有 pywin32)
        try:
            pythoncom = importlib.import_module("pythoncom")
        except ModuleNotFoundError:
            pythoncom = None
            logger.warning("pythoncom 不可用(無 COM 環境)— 略過 CoInitialize")
        if pythoncom is not None:
            pythoncom.CoInitialize()
        try:
            if not self._init_com():
                return
            while True:
                self._pump_once()
                try:
                    cmd = self._cmd_q.get(timeout=0.05)
                except queue.Empty:
                    continue
                if cmd is None:
                    break
                fn, fut = cmd
                exc: BaseException | None = None
                result: tuple[str, int] | None = None
                try:
                    result = fn()
                except Exception as e:  # noqa: BLE001 — COM 例外轉給 future,執行緒不可死
                    exc = e
                loop = self._loop
                if loop is not None:
                    try:
                        loop.call_soon_threadsafe(_settle, fut, result, exc)
                    except RuntimeError:
                        # loop 已關閉(行程收尾競態)— 對齊 _drain_pending 的 guard
                        # (review B5):結果無從回傳,終止執行緒走 finally 收尾
                        logger.error("event loop 已關閉,寫入結果無法回傳 — COM 執行緒終止")
                        break
        finally:
            # 執行緒亡故必須降 status:否則寫入請求進佇列後 future 永不 resolve,UI 還顯示健康
            if not self._last_error:
                self._last_error = "COM 執行緒已終止"
            self._set_status("error")
            self._drain_pending()
            logger.error("capital-com 執行緒結束(status→error)")

    def _drain_pending(self) -> None:
        """執行緒結束時佇列殘留的命令沒人消化:future 必須 fail,
        否則 status 檢查通過後才入佇列的寫入請求會永久懸掛。"""
        while True:
            try:
                cmd = self._cmd_q.get_nowait()
            except queue.Empty:
                return
            if cmd is None:
                continue
            _fn, fut = cmd
            loop = self._loop
            if loop is None:
                logger.error("寫入命令丟棄(event loop 未綁定)")
                continue
            try:
                loop.call_soon_threadsafe(
                    _settle, fut, None, RuntimeError("COM 執行緒已終止,命令未執行")
                )
            except RuntimeError:
                # loop 已關閉(行程收尾):future 無從 resolve,只能留 log
                logger.error("寫入命令丟棄(event loop 已關閉)")

    # ------------------------------------------------------------------ 寫入骨架(event loop)

    async def _execute_write(
        self,
        *,
        action: str,
        req: _WriteReq,
        gate: GateResult,
        com_call: _ComCall,
        message_prefix: str = "",
    ) -> OrderResult:
        """寫入操作共用骨架:閘 → ready 檢查 → 審計(前)→ COM 佇列 → 審計(後)。
        所有「拒絕/失敗」路徑都留審計 —— 真錢寫入,事後要能查帳(design §3/§9)。"""
        if not gate.allowed:
            reason = gate.reason or "blocked"
            await self._audit_blocked(action, req, reason)
            raise CapitalGateBlockedError(reason)
        # degraded(回報斷線)放行:送單通道獨立可用,且刪單/平倉是降風險操作
        if self._status not in ("ok", "degraded") or self._loop is None:
            await self._audit_blocked(action, req, "capital_not_ready")
            raise CapitalNotReadyError("群益未就緒(尚未登入或執行緒未啟動)")
        # 前置:寫不進去 → AuditWriteError,錢沒動(to_thread 不卡 loop,review B6)
        await asyncio.to_thread(self._audit, self._record(action, req))
        fut: asyncio.Future[tuple[str, int]] = self._loop.create_future()
        self._cmd_q.put((com_call, fut))
        try:
            # shield:timeout / route 取消都不可 cancel 底層 fut —
            # 真錢命令可能已送進群益,晚到結果要能落審計(review B1)
            message, code = await asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)
        except TimeoutError:
            # 命令可能已送進群益(同步呼叫卡在群益端)→ 結果未知,
            # 不可回「失敗」誘發重送;照樣審計留帳;晚到結果補 late 行
            result = OrderResult(ok=False, code=-1, message="結果未知,勿重送", seq_no=None)
            await self._audit_after(action, req, result)
            fut.add_done_callback(lambda f: self._on_late_result(action, req, f))
            return result
        except asyncio.CancelledError:
            # route task 取消(cancel-chain):單可能已出手,晚到結果補審計;取消不可吞
            fut.add_done_callback(lambda f: self._on_late_result(action, req, f))
            raise
        except Exception as e:  # noqa: BLE001 — COM 例外/執行緒亡故:審計後轉 CapitalDownError
            result = OrderResult(
                ok=False, code=-1, message=f"COM 例外: {type(e).__name__}: {e}", seq_no=None
            )
            await self._audit_after(action, req, result)
            raise CapitalDownError(result.message) from e
        ok = code == 0
        text = f"{self._com.return_code_message(code)} {message}".strip()
        result = OrderResult(
            ok=ok,
            code=code,
            message=(message_prefix + text) if message_prefix else text,
            seq_no=(message.strip() or None) if ok else None,
        )
        await self._audit_after(action, req, result)
        if not ok:
            # 群益明確拒絕(code≠0):審計後置照寫,再透傳 400 BROKER_REJECTED
            # (design §6;review A2/C1)。timeout「結果未知」(code=-1)不走這裡。
            raise BrokerRejectedError(err_code=str(code), err_msg=text)
        return result

    # ------------------------------------------------------------------ 送單

    def _note_price_type(
        self,
        result: OrderResult,
        price_type: str | None,
        *,
        stock_no: str | None = None,
        buy_sell: str | None = None,
    ) -> None:
        """送單成功且拿到委託序號 → 把價格別記進 store(SC-10)。
        群益回報無價格別欄,委託列表要標「市價」只能靠這一手。

        兩條不記的路徑語意不同(review r1 IMPL-4):
        - **拒單**(code≠0,seq_no=None):市場上沒有這張單,標籤會是假訊息。
        - **timeout**(結果未知):單可能已在市場上,只是結果還沒回來 —— 當下不記,
          但 COM 晚到結果若帶 seq 就補記(`_on_late_result`),否則本 app 送出的市價單
          會因為一次 timeout 就永久失標。
        `price_type` 為 None = 該請求沒有價格別(刪單 / 改價 / 減量)→ 不記。
        日期記**兩個候選**:本機日曆日 + 該時刻所屬的交易日(N075)。夜盤跨午夜時兩者
        不同,而群益回報 idx23 走哪一種日界未實證 —— 記兩個是舊行為的超集,
        不會讓現在標得出來的單失標,理由與 prune 規則見 `store.note_price_type`。
        平倉路徑也經過送單函式 → 一併標。
        `stock_no` / `buy_sell`(回報口徑 "B"/"S")綁進 note:多開的交易日候選正是 seq 重用
        的誤標窗,綁標的 + 方向後撞到不同單就不帶出(review R6 ST1;規則在 `store`)。

        交易日推算的保險絲(`last_trading_day` / `next_trading_day` 60 天內找不到交易日 = 日曆
        資料錯;日盤分支走前者、夜盤分支走後者,兩把都 raise RuntimeError)炸在這裡
        時**只退掉交易日候選**、其餘照記(review §2.4 Spec 7):標籤是附屬品,少標是 fail-safe
        方向;單已在市場上、審計行(晚到路徑在本函式之後才寫)不得因此斷掉。退回只記本機日 =
        N075 前的口徑,日盤單照樣標得出,只有夜盤那一天候選缺。"""
        if not (price_type and result.ok and result.seq_no):
            return
        # 先算本機日,保持改動前「本機日先、交易日後」的求值順序(pr-134 F-06);兩次讀時鐘
        # 本來就不是原子,這裡只釘順序,不釘「同一瞬」。
        today = _today_ymd()
        try:
            trade_date: str | None = _trade_ymd()
        except RuntimeError:
            logger.warning(
                "價格別標籤只記本機日(seq=%s):交易日推算失敗,交易日曆資料有誤",
                result.seq_no,
                exc_info=True,
            )
            trade_date = None
        self.store.note_price_type(
            result.seq_no,
            price_type,
            today,
            trade_date=trade_date,
            stock_no=stock_no,
            buy_sell=buy_sell,
        )

    async def submit_stock_order(
        self, req: StockOrderRequest, *, action: str = "order"
    ) -> OrderResult:
        def _do() -> tuple[str, int]:
            return self._com.send_stock_order(self._user_id, to_stockorder_fields(req, self._full_account))

        result = await self._execute_write(
            action=action, req=req, gate=check_stock_order(req, self._safety), com_call=_do
        )
        self._note_price_type(
            result, req.price_type, stock_no=req.stock_no, buy_sell=_side_code(req.buy_sell)
        )
        return result

    async def submit_future_order(
        self,
        req: FutureOrderRequest,
        *,
        contract: str,
        multiplier: int,
        new_close: int = 2,
        action: str = "order",
    ) -> OrderResult:
        """期貨/選擇權送單。contract = 已解析期交所碼(HOT 由 route 先 resolve),
        multiplier = 金額閘乘數(route 由 product 查)。平倉路徑傳 new_close=1。"""
        gate = check_future_order(req, self._safety, multiplier=multiplier)
        fut_account = self._futures_account
        if gate.allowed and fut_account is None:
            gate = GateResult(False, "no_futures_account")
        # 分流判準收在 mapping(單一定義):指數期貨/個股期走 SendFutureOrder,
        # 選擇權(TXO/週選)走 SendOptionOrder;未知產品以契約碼結構判別
        is_option = is_option_contract(contract)
        # market+ROD → mapping 強制 IOC;升級註記由 client 組進 message(review R6)
        prefix = (
            "市價單已升級 IOC;"
            if req.price_type == "market" and req.time_in_force == "ROD"
            else ""
        )

        def _do() -> tuple[str, int]:
            fields = to_futureorder_fields(
                req, fut_account or "", contract=contract, new_close=new_close
            )
            return self._com.send_future_order(self._user_id, fields, is_option=is_option)

        result = await self._execute_write(
            action=action, req=req, gate=gate, com_call=_do, message_prefix=prefix
        )
        # 期貨單的 `tc4_symbol` 與回報契約碼不同域 → 只綁方向
        self._note_price_type(result, req.price_type, buy_sell=_side_code(req.buy_sell))
        return result

    # ------------------------------------------------------------------ 刪/改/減(雙帳號路由)

    def _routing(self, seq_no: str, market: Market, base: GateResult) -> tuple[GateResult, str]:
        """market → 帳號選擇 + store 市場別交叉驗證。回 (gate, account)。
        store 查無(None)信 request 的 market 放行 — 斷線時 store 空仍要能刪單(review R3)。"""
        if not base.allowed:
            return base, ""
        if market == "fut":
            if self._futures_account is None:
                return GateResult(False, "no_futures_account"), ""
            account = self._futures_account
        else:
            account = self._full_account
        m = self.store.market_of(seq_no)
        if m is not None:
            expected = SEC_MARKETS if market == "sec" else _FUT_REPLY_MARKETS
            if m not in expected:
                return GateResult(False, "market_mismatch"), ""
        return base, account

    def _multiplier_for_contract(self, contract: str | None, *, seq_no: str) -> int:
        """期交所契約碼 → 金額閘乘數;任一步失敗 → 1 + warning(review R7)。"""
        if contract:
            try:
                return multiplier_of(exchange_product_of(contract))
            except ValueError as e:
                logger.warning(
                    "期貨乘數反查失敗(seq=%s, contract=%r): %s → multiplier=1",
                    seq_no, contract, e,
                )
                return 1
        logger.warning("期貨乘數反查失敗(seq=%s 查無委託契約碼)→ multiplier=1", seq_no)
        return 1

    def _fut_multiplier(self, seq_no: str) -> int:
        rec = next((o for o in self.store.orders() if o.seq_no == seq_no), None)
        return self._multiplier_for_contract(
            rec.stock_no if rec is not None else None, seq_no=seq_no
        )

    async def cancel_order(self, req: CancelOrderRequest) -> OrderResult:
        gate, account = self._routing(req.seq_no, req.market, check_cancel(self._safety))

        def _do() -> tuple[str, int]:
            return self._com.cancel_order(self._user_id, account, req.seq_no)

        return await self._execute_write(action="cancel", req=req, gate=gate, com_call=_do)

    async def correct_price(self, req: CorrectPriceRequest) -> OrderResult:
        # 總開關/路由閘先於 store 查找:審計 blocked 要記真正的擋單原因
        gate, account = self._routing(req.seq_no, req.market, check_master(self._safety))
        if gate.allowed:
            remaining = self.store.remaining_shares(req.seq_no)  # 原始單位:股/口
            if req.market == "sec":
                mult = 1000
                if remaining is not None:
                    # 股 → 張(ceil):零股尾數多算一張 = 金額閘更嚴,安全方向
                    remaining = -(-remaining // 1000)
            else:
                mult = self._fut_multiplier(req.seq_no)
            gate = check_correct_price(req.price, remaining, self._safety, multiplier=mult)
        # COM 介面收字串,依 market 格式化:證券兩位小數、期貨走送單同款
        # future_price_str(整數價無小數尾;review A6)
        price_str = (
            f"{req.price:.2f}" if req.market == "sec" else future_price_str(req.price)
        )

        def _do() -> tuple[str, int]:
            return self._com.correct_price(self._user_id, account, req.seq_no, price_str)

        result = await self._execute_write(
            action="correct_price", req=req, gate=gate, com_call=_do
        )
        # 改價成功 = 這張單現在是**限價**單(改價帶的就是限價),原本的「市價」記憶留著
        # 就會誤標(review r1 IMPL-6)—— 這是唯一一條 false positive 路徑,其餘失效方向
        # 都只是少標。這裡不看 result.ok:非 ok 能走到這只有 timeout(拒單一律 raise),
        # 而「結果未知」時改價可能已成立 → 一併作廢,寧可少一個標籤也不誤標。
        self.store.forget_price_type(req.seq_no)
        return result

    async def decrease_qty(self, req: DecreaseQtyRequest) -> OrderResult:
        gate, account = self._routing(
            req.seq_no, req.market, check_decrease(req.qty, self._safety)
        )

        def _do() -> tuple[str, int]:
            return self._com.decrease_qty(self._user_id, account, req.seq_no, req.qty)

        return await self._execute_write(action="decrease", req=req, gate=gate, com_call=_do)

    # ------------------------------------------------------------------ 平倉

    def _close_dup_reason(self, inflight_key: str, scan_key: str, side: BuySell) -> str | None:
        """平倉重複送單防護。部位快取要等成交回報→debounce→重查回來才更新,
        窗口內(數秒)第二次平倉仍看得到原始全量持倉、照樣過量閘 → 兩張全量反向單。
        兩層擋:1. in-flight 窗口(送出後 ~10s);2. store 同標的同向活躍委託。

        ⚠ 兩把鍵語意不同,顯式分離:
        - inflight_key = sec `"{股號}:{種類}"` / fut 契約碼 —— 同檔資+集保是兩筆各自的平倉,
          互不阻擋;寫入(_submit_close_locked)/讀取/過期清理三端必須同鍵,
          只改寫入端會讓 10s 防重送整層失效。
        - scan_key = 股號/契約碼 —— 委託回報沒有庫存種類這維,活單掃描只能以標的比對
          (同檔兩種類同向平倉時第二筆會被擋,是接受的保守行為)。"""
        deadline = self._close_inflight.get(inflight_key)
        if deadline is not None:
            if time.monotonic() < deadline:
                return f"{scan_key} 平倉單剛送出(在途),請先核對委託回報"
            del self._close_inflight[inflight_key]
        want = "B" if side == "buy" else "S"
        for o in self.store.orders():
            if o.actionable and o.stock_no == scan_key and o.buy_sell == want:
                return f"{scan_key} 已有同向活躍委託(seq={o.seq_no}),請先刪單或等其成交"
        return None

    async def _close_blocked(
        self, req: PositionCloseRequest, reason: str
    ) -> CapitalGateBlockedError:
        await self._audit_blocked("close", req, reason)
        return CapitalGateBlockedError(reason)

    async def _submit_close_locked(
        self, inflight_key: str, submit: Callable[[], Awaitable[OrderResult]]
    ) -> OrderResult:
        """in-flight 標記 + 送單。await 前就標記:同 loop 上的併發請求才擋得住。
        submit 被前置閘擋下(CapitalGateBlockedError / AuditWriteError / NotReady,
        錢沒動)→ 解鎖再 re-raise,立即重試不被「在途」擋(review A8);
        逾時/COM 例外的結果未知 → 不解鎖,寧可鎖滿窗口(多鎖 10s 是可接受代價)。
        鍵一律由 inflight_key 決定(caller 已依 market 組好),不從 req 另推一次 —
        兩處推法各自演化正是防重送整層失效的入口。"""
        self._close_inflight[inflight_key] = time.monotonic() + _CLOSE_INFLIGHT_S
        try:
            return await submit()
        except (CapitalGateBlockedError, AuditWriteError, CapitalNotReadyError):
            self._close_inflight.pop(inflight_key, None)
            raise

    def _sec_no_position_reason(self, req: PositionCloseRequest) -> str:
        """sec 查不到部位的兩種成因分流:req 沒帶 kind 且同檔多列 = 歧義,阻擋不猜
        (猜錯種類 = 送錯單種)。position_for 與這次計數之間的競態只影響文案,可接受。"""
        if req.kind is None:
            # 母體與 position_for(market="sec") 的掃描母體對齊,兩處判別不得各自為政
            same = [
                p for p in self.store.positions() if p.market == "sec" and p.stock_no == req.key
            ]
            if len(same) > 1:
                return f"{req.key} 多種庫存並存,請指定種類"
        return f"{req.key} 無部位可平"

    async def close_position(self, req: PositionCloseRequest) -> OrderResult:
        if req.market == "sec":
            # kind 有值 → 精確鍵;None → 唯一列 fallback(舊 body 相容),多列則歧義阻擋
            pos = self.store.position_for(req.key, req.kind, market="sec")
            if pos is None or pos.qty == 0 or pos.market != "sec":
                raise await self._close_blocked(req, self._sec_no_position_reason(req))
            try:
                # kind 來自即時庫存 — 融資部位平倉送融資賣,不可送現股賣
                order = build_close_order(pos, req)
            except ValueError as e:
                raise await self._close_blocked(req, str(e)) from e
            inflight_key = f"{req.key}:{pos.kind}"
            reason = self._close_dup_reason(inflight_key, req.key, order.buy_sell)
            if reason:
                raise await self._close_blocked(req, reason)
            return await self._submit_close_locked(
                inflight_key, lambda: self.submit_stock_order(order, action="close")
            )

        # fut:kind 忽略(OI 列不帶種類),market 內唯一匹配即可 — 不寫死 "cash",
        # 免得 OnOpenInterest 欄序 prod 校正時順手設了 kind 就靜默「無部位可平」
        pos = self.store.position_for(req.key, market="fut")
        if pos is None or pos.qty == 0 or pos.market != "fut":
            raise await self._close_blocked(req, f"{req.key} 無部位可平")
        try:
            # 反向 限價貼漲跌停 + IOC(design amendment);tc4_symbol 欄存期交所契約碼
            fut_order = build_future_close_order(pos, req)
        except ValueError as e:
            raise await self._close_blocked(req, str(e)) from e
        reason = self._close_dup_reason(req.key, req.key, fut_order.buy_sell)
        if reason:
            raise await self._close_blocked(req, reason)
        multiplier = self._multiplier_for_contract(req.key, seq_no="(close)")
        return await self._submit_close_locked(
            req.key,
            lambda: self.submit_future_order(
                fut_order, contract=req.key, multiplier=multiplier, new_close=1, action="close"
            ),
        )
