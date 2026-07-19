"""TradeRuntime:下單 asyncio 邊界 + §7 三道閘(design.md v5 §2.3)。

三道閘全在這層,UI 繞不過:
閘一 環境隔離 — DQ4_LIVE 預設關,無法分類一律視為正式戶擋下;banner 印環境 + 遮罩帳號。
閘二 二次確認 — preview(dry-run)→ 一次性 preview_id(TTL)→ submit。
閘三 審計 — NewOrder 送出前寫失敗拒單;送出後寫失敗只降級(絕不 5xx 誘導重送)。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, Sequence

from copycat.live.trade_models import (
    AccountInfo,
    BrokerRejectedError,
    OrderReport,
    OrderRequest,
    TouchanceDownError,
    classify_is_sim,
    mask_account,
    to_neworder_param,
)
from copycat.server.audit import AuditWriteError, append_audit

logger = logging.getLogger(__name__)

TradeStatus = Literal["ready", "touchance_down", "no_account", "live_blocked"]

_RECOVER_TIMEOUT_SECS = 15.0
_SWEEP_FACTOR = 10.0  # 過期超過 10×TTL 才清掃(R8:TTL~10×TTL 間保留供 PREVIEW_EXPIRED)


class TradeSource(Protocol):
    def accounts(self) -> list[AccountInfo]: ...

    def place_order(self, param: dict[str, str]) -> dict: ...

    def restore_reports(self) -> list[OrderReport]: ...

    def restore_fills(self) -> list[OrderReport]: ...

    def subscribe_reports(
        self,
        on_report: Callable[[str, OrderReport], None],
        on_reconnect: Callable[[], None],
    ) -> None: ...

    def close(self) -> None: ...


class ConfirmRequiredError(Exception):
    """submit 未附有效 preview_id(閘二)。"""


class PreviewExpiredError(Exception):
    """preview_id 已逾時(閘二)。"""


class LiveBlockedError(Exception):
    """正式戶未啟用(閘一,DQ4_LIVE 預設關)。"""


class NotReadyError(Exception):
    """trade 未就緒(無帳號 / 未配置)。"""


class InvalidOrderError(Exception):
    """下單參數不合法(qty / price)。"""


class SymbolNotAllowedError(Exception):
    """symbol 不在可下單白名單(資料驅動,R5)。"""


def _report_dict(rep: OrderReport) -> dict[str, Any]:
    return {
        "report_id": rep.report_id,
        "symbol": rep.symbol,
        "side": rep.side,
        "status_raw": rep.status_raw,
        "price": rep.price,
        "qty": rep.qty,
        "filled_qty": rep.filled_qty,
        "err_code": rep.err_code,
        "err_msg": rep.err_msg,
    }


def _ts() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class TradeRuntime:
    def __init__(
        self,
        source: TradeSource,
        *,
        live_enabled: bool,
        sim_patterns: Sequence[str],
        audit_dir: Path,
        allowed_symbols: Callable[[], set[str]],
        preview_ttl_secs: float = 30.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._live_enabled = live_enabled
        self._sim_patterns = list(sim_patterns)
        self._audit_dir = Path(audit_dir)
        self._allowed_symbols = allowed_symbols
        self._ttl = preview_ttl_secs
        self._now = now
        self._status: TradeStatus = "touchance_down"
        self._account: AccountInfo | None = None
        self._is_sim = False
        # preview_id -> (request_id, param, deadline);一次性 + TTL(閘二)
        self._previews: dict[str, tuple[str, dict[str, str], float]] = {}
        self._orders: dict[str, OrderReport] = {}
        self._fills: dict[str, OrderReport] = {}
        self._degraded = False
        self._audit_degraded = False
        self._started_once = False
        self._subscribed = False
        self._start_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._re_restore_task: asyncio.Task[None] | None = None

    # ---- 啟動 / 恢復(single-flight,R4-3) ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        async with self._start_lock:
            await self._start_locked()

    async def _start_locked(self) -> None:
        try:
            accounts = await asyncio.to_thread(self._source.accounts)
        except TouchanceDownError:
            logger.warning("TC4 trade 連線失敗,status=touchance_down")
            self._status = "touchance_down"
            return
        if not accounts:
            self._status = "no_account"
            return
        key = lambda a: (a.broker_id, a.account)  # noqa: E731
        sims = sorted((a for a in accounts if classify_is_sim(a, self._sim_patterns)), key=key)
        lives = sorted((a for a in accounts if not classify_is_sim(a, self._sim_patterns)), key=key)
        if sims:
            self._account, self._is_sim = sims[0], True
        elif self._live_enabled and lives:
            self._account, self._is_sim = lives[0], False
        else:
            self._status = "live_blocked"
            return
        self._banner(candidates=len(accounts))
        try:
            if not self._subscribed:
                # subscribe → restore(R9:dict 以 report_id 去重,先訂閱無漏報窗)
                await asyncio.to_thread(
                    self._source.subscribe_reports, self._on_report, self._on_reconnect
                )
                self._subscribed = True
            reports = await asyncio.to_thread(self._source.restore_reports)
            fills = await asyncio.to_thread(self._source.restore_fills)
        except TouchanceDownError:
            logger.warning("TC4 trade 回報訂閱/回補失敗,status=touchance_down")
            self._status = "touchance_down"
            return
        # 僅首次 start 用 setdefault;之後任何 restore 一律 overwrite(R4-1)
        self._apply_restore(reports, fills, overwrite=self._started_once)
        self._started_once = True
        self._status = "ready"

    def _banner(self, *, candidates: int) -> None:
        assert self._account is not None
        if not self._is_sim:
            logger.warning("!!! 正式戶 !!!")
            logger.warning("!!! 正式戶 !!!")
        logger.warning(
            "=== DQ4 交易環境:%s | 帳戶:%s | 候選帳戶 %d 個 ===",
            "模擬" if self._is_sim else "正式",
            mask_account(self._account.account),
            candidates,
        )

    async def _ensure_ready(self) -> None:
        if self._status == "ready":
            return
        if self._status == "live_blocked":
            raise LiveBlockedError("live account disabled (DQ4_LIVE unset)")
        # 恢復 = 重跑完整 start 序列(R3-4),single-flight(R4-3)
        async with self._start_lock:
            if self._status not in ("ready", "live_blocked"):
                await asyncio.wait_for(self._start_locked(), _RECOVER_TIMEOUT_SECS)
        if self._status == "ready":
            return
        if self._status == "live_blocked":
            raise LiveBlockedError("live account disabled (DQ4_LIVE unset)")
        if self._status == "no_account":
            raise NotReadyError("no trade account logged in")
        raise TouchanceDownError("TC4 trade unavailable")

    # ---- 閘二:preview / submit ----

    async def preview(self, req: OrderRequest) -> dict[str, Any]:
        await self._ensure_ready()
        self._sweep_previews()
        if req.qty < 1:
            raise InvalidOrderError(f"qty must be >= 1, got {req.qty}")
        if req.kind == "limit" and req.price_millipts is None:
            raise InvalidOrderError("limit order requires price")
        if not req.symbol.startswith(("TC.F.", "TC.O.")):
            raise SymbolNotAllowedError(req.symbol)
        if req.symbol not in self._allowed_symbols():
            raise SymbolNotAllowedError(req.symbol)
        account = self._account
        assert account is not None
        param = to_neworder_param(req, broker_id=account.broker_id, account=account.account)
        request_id = uuid.uuid4().hex
        await asyncio.to_thread(
            partial(
                append_audit,
                self._audit_dir,
                self._record("preview", request_id, param=param),
                when=date.today(),
            )
        )  # 前置寫失敗 → AuditWriteError 冒泡拒單(閘三)
        preview_id = uuid.uuid4().hex
        self._previews[preview_id] = (request_id, param, self._now() + self._ttl)
        return {
            "preview_id": preview_id,
            "request_id": request_id,
            "param": param,
            "account_masked": mask_account(account.account),
            "mode": "sim" if self._is_sim else "live",
        }

    async def submit(self, preview_id: str) -> dict[str, Any]:
        entry = self._previews.pop(preview_id, None)  # 一次性
        if entry is None:
            raise ConfirmRequiredError(preview_id)
        request_id, param, deadline = entry
        if self._now() > deadline:
            raise PreviewExpiredError(preview_id)
        await self._ensure_ready()
        await asyncio.to_thread(
            partial(
                append_audit,
                self._audit_dir,
                self._record("submit", request_id, param=param),
                when=date.today(),
            )
        )  # 前置寫失敗 → 拒單(單尚未送出)
        try:
            resp = await asyncio.to_thread(self._source.place_order, param)
        except BrokerRejectedError as exc:
            # NewOrder 已送出:結果必須落審計(impl-R3),失敗僅降級
            await self._audit_best_effort(
                self._record(
                    "result",
                    request_id,
                    result={"success": False, "err_code": exc.err_code, "err_msg": exc.err_msg},
                )
            )
            raise
        except TouchanceDownError:
            await self._audit_best_effort(
                self._record(
                    "result", request_id, result={"success": None, "outcome": "unknown"}
                )
            )
            raise
        await self._audit_best_effort(
            self._record("result", request_id, result={"success": True, "response": resp})
        )
        return {"request_id": request_id, "result": resp}

    def _sweep_previews(self) -> None:
        cutoff = self._now() - self._ttl * (_SWEEP_FACTOR - 1.0)
        stale = [pid for pid, (_, _, deadline) in self._previews.items() if deadline < cutoff]
        for pid in stale:
            del self._previews[pid]

    def _record(self, event: str, request_id: str, **extra: Any) -> dict[str, Any]:
        account = self._account
        return {
            "event": event,
            "request_id": request_id,
            "ts": _ts(),
            "account_masked": mask_account(account.account) if account else None,
            "mode": ("sim" if self._is_sim else "live") if account else None,
            **extra,
        }

    async def _audit_best_effort(self, record: dict[str, Any]) -> None:
        try:
            await asyncio.to_thread(partial(append_audit, self._audit_dir, record, when=date.today()))
        except AuditWriteError:
            logger.exception("送出後審計寫入失敗(降級,不回 5xx)")
            self._audit_degraded = True

    # ---- 回報 store(listener thread 進入點) ----

    def _on_report(self, kind: str, rep: OrderReport) -> None:
        # 審計直接在 listener thread 寫(R7);失敗只降級(R3)
        try:
            append_audit(
                self._audit_dir,
                {"event": "report", "kind": kind, "ts": _ts(), "report": _report_dict(rep)},
                when=date.today(),
            )
        except AuditWriteError:
            logger.exception("report 審計寫入失敗(降級)")
            self._audit_degraded = True
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._store_report, kind, rep)

    def _store_report(self, kind: str, rep: OrderReport) -> None:
        store = self._orders if kind == "exec" else self._fills
        store[rep.report_id] = rep  # push 一律覆寫

    def _on_reconnect(self) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._begin_re_restore)

    def _begin_re_restore(self) -> None:
        self._degraded = True
        loop = self._loop
        assert loop is not None
        self._re_restore_task = loop.create_task(self._re_restore())

    async def _re_restore(self) -> None:
        try:
            reports = await asyncio.to_thread(self._source.restore_reports)
            fills = await asyncio.to_thread(self._source.restore_fills)
        except TouchanceDownError:
            # 失敗:degraded 維持 True,下一次 generation 變化或恢復重跑 start 再試(R4-6)
            logger.exception("re-restore 失敗,degraded 維持")
            return
        self._apply_restore(reports, fills, overwrite=True)  # 斷線窗內推進要蓋回(R3-3)
        self._degraded = False

    def _apply_restore(
        self, reports: list[OrderReport], fills: list[OrderReport], *, overwrite: bool
    ) -> None:
        for rep in reports:
            if overwrite:
                self._orders[rep.report_id] = rep
            else:
                self._orders.setdefault(rep.report_id, rep)
        for rep in fills:
            if overwrite:
                self._fills[rep.report_id] = rep
            else:
                self._fills.setdefault(rep.report_id, rep)

    # ---- 視圖 ----

    def orders_view(self) -> dict[str, Any]:
        return {
            "orders": [_report_dict(r) for r in self._orders.values()],
            "fills": [_report_dict(r) for r in self._fills.values()],
            "degraded": self._degraded,
            "audit_degraded": self._audit_degraded,
        }

    def account_view(self) -> dict[str, Any]:
        account = self._account
        return {
            "status": self._status,
            "mode": ("sim" if self._is_sim else "live") if account is not None else None,
            "account_masked": mask_account(account.account) if account is not None else None,
            "broker_id": account.broker_id if account is not None else None,
            "audit_degraded": self._audit_degraded,
            "orderable_symbols": sorted(self._allowed_symbols()),
        }

    async def close(self) -> None:
        task = self._re_restore_task
        if task is not None and not task.done():
            task.cancel()
        await asyncio.to_thread(self._source.close)
