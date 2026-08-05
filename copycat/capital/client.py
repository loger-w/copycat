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
from datetime import date, datetime
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

logger = logging.getLogger(__name__)

# 寫入命令等 COM 結果的上限:SendStockOrder 是同步呼叫,群益端掛起時 future 永不
# resolve → HTTP 請求永久懸掛,使用者不知道單送出沒、最容易誘發重送
_WRITE_TIMEOUT_S = 10.0

# 平倉 in-flight 窗口:送出後到回報進 store(或部位重查完成)前,擋同 key 再平倉
_CLOSE_INFLIGHT_S = 10.0

# balance→profit→OI 串行鏈的 pending 逾時:任一段卡住(rc!=0 已即時降級,這裡防
# 零事件的靜默卡死)就以已收資料寫入,部位快取不可永久滯留在暫存區
_PENDING_TIMEOUT_S = 8.0

# reply idx1 期權市場別(cancel/correct/decrease 的 market 交叉驗證用;
# 證券側用 reply.SEC_MARKETS 同一份)
_FUT_REPLY_MARKETS: frozenset[str] = frozenset({"TF", "TO", "OF", "OO"})

# SendFutureOrder 家族;其餘產品(TXO/週選)走 SendOptionOrder
_FUTURE_PRODUCTS: frozenset[str] = frozenset({"TXF", "MXF", "TMF"})

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
        self._balance = BalanceCollector(on_complete=self._on_balance_complete)
        self._profit = BalanceCollector(on_complete=self._on_profit_complete, parse=parse_profit_line)
        self._oi = BalanceCollector(on_complete=self._on_oi_complete, parse=parse_open_interest_line)
        self._balance_due: float | None = None  # monotonic;成交後 debounce 重查
        self._balance_last_ts: float = 0.0  # 定時重查用(0=啟動後第一圈就查)
        self._close_inflight: dict[str, float] = {}  # key → monotonic 解鎖時刻(只在 loop 上碰)
        self._pending_sec: list[Position] | None = None  # 證券部位暫存,期貨回完才合併發布
        self._pending_deadline: float | None = None  # pending 逾時強制發布(watchdog)

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
        (review B1)。done_callback 在 loop 上跑,同步 append_audit 可接受(罕見路徑)。"""
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
        if rec.alt_seq_no and rec.seq_no and rec.alt_seq_no != rec.seq_no:
            # 真實樣本:預約單 KeyNo(idx0)≠ 尾欄序號(idx47),盤中單兩者相同。
            logger.warning("Capital reply: KeyNo=%s 尾欄序號=%s 不同(預約單?)", rec.seq_no, rec.alt_seq_no)
        self.store.apply_reply(rec)
        if rec.status_raw == "D":  # 成交 → debounce 重查(連續成交只查尾端一次)
            self._mark_balance_dirty()
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

    def _mark_balance_dirty(self, delay_s: float = 2.0) -> None:
        self._balance_due = time.monotonic() + delay_s

    def _maybe_query_balance(self) -> None:
        """幫浦圈呼叫:due 到了或距上次查詢逾 60s → 發查詢。
        degraded(回報斷線)也要查 — 此時 60s 輪詢是部位唯一的更新來源。"""
        if self._status not in ("ok", "degraded"):
            return
        now = time.monotonic()
        due = self._balance_due is not None and now >= self._balance_due
        stale = now - self._balance_last_ts >= 60.0
        if not due and not stale:
            return
        self._balance_due = None
        self._balance_last_ts = now  # 先記,失敗也不連發
        self._balance.reset()
        rc = self._com.get_real_balance(self._user_id, self._full_account)
        if rc != 0:
            logger.warning("GetRealBalanceReport rc=%s: %s", rc, self._com.return_code_message(rc))

    def _on_balance_complete(self, positions: list[Position]) -> None:
        """證券庫存收齊 → 暫存(不落 store)→ 串行接損益查詢(避開 1019 查詢處理中)。
        同檔多種庫存列(集保+融資並存)全數保留 — store 以 (股號, 種類) 為鍵,不需去重補償。"""
        self._pending_sec = positions
        self._pending_deadline = time.monotonic() + _PENDING_TIMEOUT_S
        self._balance_last_ts = time.monotonic()
        self._profit.reset()
        rc = self._com.get_profit_loss_gw(self._user_id, self._full_account)
        if rc != 0:
            logger.warning("GetProfitLossGWReport rc=%s: %s", rc, self._com.return_code_message(rc))
            self._query_open_interest()  # 損益跳過,鏈不可斷 — pending 靠期貨段收尾

    def _on_profit_complete(self, rows: list[ProfitRow]) -> None:
        """損益回填進 pending 證券部位(均價+含費稅息基底)→ 串行接期貨部位查詢。
        同檔多種類報告每種類一列:只回填同 kind 的列 — 資/券成本基礎不可混用。"""
        pending = self._pending_sec
        if pending is None:
            logger.warning("損益報告遲到(本輪 pending 已發布),丟棄 %d 列", len(rows))
            return
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
                    "profit row 種類不符略過: %s 報告=%s 部位=%s",
                    r.stock_no,
                    r.kind,
                    [q.kind for q in same_no],
                )
                continue
            p.avg_price = r.avg_price
            p.pnl_base = r.pnl
            p.pnl_base_price = r.price
            p.pnl_cost = r.cost
        self._query_open_interest()

    def _query_open_interest(self) -> None:
        """期貨部位查詢(串行末段);無期貨帳號 → fut 恆空;查詢失敗 → 沿用上一輪
        fut 部位收尾(review A7:閃斷不可把面板期貨部位清空)。"""
        if self._futures_account is None:
            self._finalize_positions([])
            return
        self._oi.reset()
        rc = self._com.get_open_interest(self._user_id, self._futures_account)
        if rc != 0:
            logger.warning("GetOpenInterestGW rc=%s: %s", rc, self._com.return_code_message(rc))
            self._finalize_positions(self._stale_fut_positions())

    def _stale_fut_positions(self) -> list[Position]:
        """OI 查詢失敗/逾時:沿用 store 既有 fut 部位(review A7)。
        僅 OI 成功回報(_on_oi_complete)才全量覆蓋 fut 段。"""
        stale = [p for p in self.store.positions() if p.market == "fut"]
        logger.warning("期貨部位查詢未完成 — 沿用上一輪 fut 部位(%d 列)", len(stale))
        return stale

    def _on_oi_complete(self, rows: list[Position]) -> None:
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
        merged = sec + fut_rows
        self.store.set_positions(merged)
        self._emit({"event": "capital_position", "data": {"count": len(merged)}})

    def _poll_pending(self) -> None:
        """幫浦圈 watchdog:損益/期貨查詢零事件卡死時,pending 逾時以已收資料寫入。
        (有收到部分事件的情況由各 collector 的 1s timeout poll 先 flush,不會走到這。)"""
        if self._pending_sec is None or self._pending_deadline is None:
            return
        if time.monotonic() >= self._pending_deadline:
            logger.warning("部位合併逾時(損益/期貨查詢未完成)— 以已收證券部位寫入")
            self._finalize_positions(self._stale_fut_positions())  # fut 沿用上一輪(A7)

    # ------------------------------------------------------------------ 執行緒生命週期

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._thread = threading.Thread(target=self._run, daemon=True, name="capital-com")
        self._thread.start()

    def close(self) -> None:
        """關機:投終止訊號 + join(timeout=5)。執行緒側 finally 會降 status 並 drain。
        join 逾時不 raise(review B5):COM 呼叫卡死時執行緒可能還活著,
        daemon 執行緒隨行程結束回收 — 不為等它阻塞關機。"""
        self._cmd_q.put(None)
        t = self._thread
        if t is not None:
            t.join(timeout=5)

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

    async def submit_stock_order(
        self, req: StockOrderRequest, *, action: str = "order"
    ) -> OrderResult:
        def _do() -> tuple[str, int]:
            return self._com.send_stock_order(self._user_id, to_stockorder_fields(req, self._full_account))

        return await self._execute_write(
            action=action, req=req, gate=check_stock_order(req, self._safety), com_call=_do
        )

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
        # 分流判準:期貨家族 {TXF, MXF, TMF} 走 SendFutureOrder,其餘(TXO/週選)期權面
        is_option = exchange_product_of(contract) not in _FUTURE_PRODUCTS
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

        return await self._execute_write(
            action=action, req=req, gate=gate, com_call=_do, message_prefix=prefix
        )

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

        return await self._execute_write(action="correct_price", req=req, gate=gate, com_call=_do)

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
