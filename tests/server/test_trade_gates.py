"""SC-3/4/5/6(runtime 層):TradeRuntime 三道閘 / 狀態機 / 回報 store / 審計接線。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable

import pytest

from copycat.live.trade_models import (
    AccountInfo,
    BrokerRejectedError,
    OrderReport,
    OrderRequest,
    TouchanceDownError,
)
from copycat.server.trade import (
    ConfirmRequiredError,
    LiveBlockedError,
    PreviewExpiredError,
    SymbolNotAllowedError,
    TradeRuntime,
)

SYM = "TC.O.TWF.TXO.202607.C.23000"


def acc(broker_id: str, account: str = "9999000") -> AccountInfo:
    return AccountInfo(
        broker_id=broker_id, account=account, account_mask=f"{broker_id}-{account}", raw={}
    )


def report(report_id: str, status: str = "4") -> OrderReport:
    return OrderReport(
        report_id=report_id,
        symbol=SYM,
        side="1",
        status_raw=status,
        price="15.5",
        qty="1",
        filled_qty="0",
        err_code=None,
        err_msg=None,
        raw={},
    )


class SpyTradeSource:
    """測試替身(定名區隔 production 的 fake_trade.FakeTradeSource)。"""

    def __init__(self, accounts: list[AccountInfo] | None = None) -> None:
        self.accounts_list = accounts if accounts is not None else [acc("SIM")]
        self.accounts_calls = 0
        self.accounts_error: Exception | None = None
        self.place_calls: list[dict[str, str]] = []
        self.place_error: Exception | None = None
        self.restore_result: list[OrderReport] = []
        self.restore_calls = 0
        self.on_report: Callable[[str, OrderReport], None] | None = None
        self.on_reconnect: Callable[[], None] | None = None
        self.subscribe_hook: Callable[[], None] | None = None
        self.closed = False

    def accounts(self) -> list[AccountInfo]:
        self.accounts_calls += 1
        if self.accounts_error is not None:
            raise self.accounts_error
        return self.accounts_list

    def place_order(self, param: dict[str, str]) -> dict:
        self.place_calls.append(param)
        if self.place_error is not None:
            raise self.place_error
        return {"Success": "OK"}

    def restore_reports(self) -> list[OrderReport]:
        self.restore_calls += 1
        return list(self.restore_result)

    def restore_fills(self) -> list[OrderReport]:
        return []

    def subscribe_reports(
        self, on_report: Callable[[str, OrderReport], None], on_reconnect: Callable[[], None]
    ) -> None:
        self.on_report = on_report
        self.on_reconnect = on_reconnect
        if self.subscribe_hook is not None:
            self.subscribe_hook()

    def close(self) -> None:
        self.closed = True


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make_runtime(
    source: SpyTradeSource,
    tmp_path: Path,
    *,
    live_enabled: bool = False,
    ttl: float = 30.0,
    clock: Clock | None = None,
) -> TradeRuntime:
    return TradeRuntime(
        source,
        live_enabled=live_enabled,
        sim_patterns=["SIM"],
        audit_dir=tmp_path / "audit",
        allowed_symbols=lambda: {SYM, "TC.F.TWF.FITX.HOT"},
        preview_ttl_secs=ttl,
        now=clock if clock is not None else Clock(),
    )


def order(**kw: Any) -> OrderRequest:
    base: dict = {"symbol": SYM, "side": "buy", "kind": "limit", "qty": 1, "price_millipts": 15500}
    base.update(kw)
    return OrderRequest(**base)


def audit_lines(tmp_path: Path) -> list[dict]:
    files = sorted((tmp_path / "audit").glob("orders-*.jsonl"))
    lines: list[dict] = []
    for f in files:
        lines += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    return lines


class TestGateOne:
    async def test_sim_account_selected_with_banner(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = SpyTradeSource([acc("F999", "1111222"), acc("SIM", "9999000")])
        rt = make_runtime(src, tmp_path)
        with caplog.at_level(logging.WARNING):
            await rt.start()
        view = rt.account_view()
        assert view["status"] == "ready"
        assert view["mode"] == "sim"
        assert view["account_masked"] == "****9000"
        banner = "\n".join(caplog.messages)
        assert "模擬" in banner
        assert "****9000" in banner
        assert "9999000" not in banner  # 遮罩:完整帳號不得出現在 log

    async def test_only_live_accounts_blocked_by_default(self, tmp_path: Path) -> None:
        src = SpyTradeSource([acc("F999")])
        rt = make_runtime(src, tmp_path)
        await rt.start()
        assert rt.account_view()["status"] == "live_blocked"
        with pytest.raises(LiveBlockedError):
            await rt.preview(order())

    async def test_live_enabled_allows_live_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = SpyTradeSource([acc("F999")])
        rt = make_runtime(src, tmp_path, live_enabled=True)
        with caplog.at_level(logging.WARNING):
            await rt.start()
        assert rt.account_view()["mode"] == "live"
        assert "正式戶" in "\n".join(caplog.messages)

    async def test_deterministic_pick_sorted_first(self, tmp_path: Path) -> None:
        src = SpyTradeSource([acc("SIM", "222"), acc("SIM", "1111111")])
        rt = make_runtime(src, tmp_path)
        await rt.start()
        assert rt.account_view()["account_masked"] == "****1111"

    async def test_no_accounts_not_ready(self, tmp_path: Path) -> None:
        src = SpyTradeSource([])
        rt = make_runtime(src, tmp_path)
        await rt.start()
        assert rt.account_view()["status"] == "no_account"


class TestGateTwo:
    async def test_preview_then_submit_audits_chain(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        p = await rt.preview(order())
        assert p["param"]["Price"] == "15.5"
        result = await rt.submit(p["preview_id"])
        assert result["request_id"] == p["request_id"]
        events = [(line["event"], line["request_id"]) for line in audit_lines(tmp_path)]
        rid = p["request_id"]
        assert ("preview", rid) in events
        assert ("submit", rid) in events
        assert ("result", rid) in events
        assert src.place_calls[0]["Symbol"] == SYM

    async def test_submit_without_preview_confirm_required(self, tmp_path: Path) -> None:
        rt = make_runtime(SpyTradeSource(), tmp_path)
        await rt.start()
        with pytest.raises(ConfirmRequiredError):
            await rt.submit("nope")

    async def test_preview_id_single_use(self, tmp_path: Path) -> None:
        rt = make_runtime(SpyTradeSource(), tmp_path)
        await rt.start()
        p = await rt.preview(order())
        await rt.submit(p["preview_id"])
        with pytest.raises(ConfirmRequiredError):
            await rt.submit(p["preview_id"])

    async def test_expired_preview(self, tmp_path: Path) -> None:
        clock = Clock()
        rt = make_runtime(SpyTradeSource(), tmp_path, ttl=30.0, clock=clock)
        await rt.start()
        p = await rt.preview(order())
        clock.t += 31.0
        with pytest.raises(PreviewExpiredError):
            await rt.submit(p["preview_id"])

    async def test_symbol_not_allowed(self, tmp_path: Path) -> None:
        rt = make_runtime(SpyTradeSource(), tmp_path)
        await rt.start()
        with pytest.raises(SymbolNotAllowedError):
            await rt.preview(order(symbol="TC.O.TWF.TXO.209912.C.99999"))


class TestGateThree:
    async def test_preview_audit_failure_rejects(self, tmp_path: Path) -> None:
        from copycat.server.audit import AuditWriteError

        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        (tmp_path / "audit").rmdir() if (tmp_path / "audit").exists() else None
        (tmp_path / "audit").write_text("block", encoding="utf-8")  # 目錄位置被檔案佔住
        with pytest.raises(AuditWriteError):
            await rt.preview(order())
        assert src.place_calls == []

    async def test_result_audit_failure_degrades_not_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copycat.server.trade as trade_mod

        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        p = await rt.preview(order())
        real_append = trade_mod.append_audit

        def flaky(base: Path, record: dict, *, when: Any) -> None:
            if record.get("event") == "result":
                raise trade_mod.AuditWriteError("disk full")
            real_append(base, record, when=when)

        monkeypatch.setattr(trade_mod, "append_audit", flaky)
        result = await rt.submit(p["preview_id"])  # 不得 raise(R3)
        assert result["result"]["Success"] == "OK"
        assert rt.orders_view()["audit_degraded"] is True

    async def test_audit_degraded_recovers_after_successful_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """暫時性審計失敗不得變永久警示:下一次寫入成功即清旗(review A2)。"""
        import copycat.server.trade as trade_mod

        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        p1 = await rt.preview(order())
        real_append = trade_mod.append_audit
        fail_once = {"armed": True}

        def flaky(base: Path, record: dict, *, when: Any) -> None:
            if record.get("event") == "result" and fail_once["armed"]:
                fail_once["armed"] = False
                raise trade_mod.AuditWriteError("transient")
            real_append(base, record, when=when)

        monkeypatch.setattr(trade_mod, "append_audit", flaky)
        await rt.submit(p1["preview_id"])
        assert rt.orders_view()["audit_degraded"] is True
        p2 = await rt.preview(order())
        await rt.submit(p2["preview_id"])  # 這輪審計全成功
        assert rt.orders_view()["audit_degraded"] is False

    async def test_broker_reject_still_audits_result(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        src.place_error = BrokerRejectedError("-22", "tick size")
        rt = make_runtime(src, tmp_path)
        await rt.start()
        p = await rt.preview(order())
        with pytest.raises(BrokerRejectedError):
            await rt.submit(p["preview_id"])
        results = [line for line in audit_lines(tmp_path) if line["event"] == "result"]
        assert results and results[0]["result"]["err_code"] == "-22"


class TestReportStore:
    async def test_push_report_enters_store_and_audit(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        assert src.on_report is not None
        src.on_report("exec", report("E1"))
        await asyncio.sleep(0.02)
        view = rt.orders_view()
        assert [o["report_id"] for o in view["orders"]] == ["E1"]
        assert any(line["event"] == "report" for line in audit_lines(tmp_path))

    async def test_report_audit_failure_flags_but_stores(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copycat.server.trade as trade_mod

        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()

        def boom(base: Path, record: dict, *, when: Any) -> None:
            raise trade_mod.AuditWriteError("disk full")

        monkeypatch.setattr(trade_mod, "append_audit", boom)
        assert src.on_report is not None
        src.on_report("exec", report("E2"))
        await asyncio.sleep(0.02)
        view = rt.orders_view()
        assert [o["report_id"] for o in view["orders"]] == ["E2"]
        assert view["audit_degraded"] is True

    async def test_first_start_restore_does_not_clobber_push(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        src.restore_result = [report("E1", status="old")]
        src.subscribe_hook = lambda: src.on_report and src.on_report(
            "exec", report("E1", status="push")
        )
        rt = make_runtime(src, tmp_path)
        await rt.start()
        await asyncio.sleep(0.02)
        orders = rt.orders_view()["orders"]
        assert orders[0]["status_raw"] == "push"  # R4-1:首次 start setdefault

    async def test_reconnect_restore_overwrites_and_clears_degraded(
        self, tmp_path: Path
    ) -> None:
        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        assert src.on_report is not None and src.on_reconnect is not None
        src.on_report("exec", report("E1", status="stale"))
        await asyncio.sleep(0.02)
        src.restore_result = [report("E1", status="terminal")]
        src.on_reconnect()
        await asyncio.sleep(0.05)
        view = rt.orders_view()
        assert view["orders"][0]["status_raw"] == "terminal"  # R3-3:re-restore 覆寫
        assert view["degraded"] is False

    async def test_re_restore_failure_keeps_degraded(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()

        def fail_restore() -> list[OrderReport]:
            raise TouchanceDownError("down")

        src.restore_reports = fail_restore  # type: ignore[method-assign]
        assert src.on_reconnect is not None
        src.on_reconnect()
        await asyncio.sleep(0.05)
        assert rt.orders_view()["degraded"] is True  # R4-6


class TestRecovery:
    async def test_start_failure_then_recovery_reruns_full_start(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = SpyTradeSource()
        src.accounts_error = TouchanceDownError("down")
        rt = make_runtime(src, tmp_path)
        await rt.start()
        assert rt.account_view()["status"] == "touchance_down"
        src.accounts_error = None
        with caplog.at_level(logging.WARNING):
            p = await rt.preview(order())  # R3-4:恢復 = 重跑完整 start(含 banner)
        assert p["preview_id"]
        assert rt.account_view()["status"] == "ready"
        assert "模擬" in "\n".join(caplog.messages)

    async def test_concurrent_recovery_single_flight(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        src.accounts_error = TouchanceDownError("down")
        rt = make_runtime(src, tmp_path)
        await rt.start()
        calls_after_fail = src.accounts_calls
        src.accounts_error = None
        results = await asyncio.gather(rt.preview(order()), rt.preview(order()))
        assert all(r["preview_id"] for r in results)
        assert src.accounts_calls == calls_after_fail + 1  # R4-3:只重跑一次


class TestClose:
    async def test_close_closes_source(self, tmp_path: Path) -> None:
        src = SpyTradeSource()
        rt = make_runtime(src, tmp_path)
        await rt.start()
        await rt.close()
        assert src.closed is True
