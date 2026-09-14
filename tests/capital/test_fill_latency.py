"""成交回報 → 部位可見的時序 loop(feat/chart-ux-batch-0826 F5;diagnosing-bugs Phase 1)。

真成交要真下單(花錢),loop 改用 FakeCom 重現**結構性**延遲:券商三段回查
(庫存 → 損益 → 期貨部位)各模擬 150 ms 往返。修前部位只由回查鏈餵,
fill → `capital_position` ≈ 0.5 s debounce + 3 × 150 ms ≈ 0.95 s;修後成交當下樂觀套用
並立即推播,< 50 ms。時間門檻取 50 ms 而不是「0」:幫浦圈本身 10 ms 級,留餘裕。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from tests.capital.balance_rows import RAW_T_HELD, balance_variant
from tests.capital.fake_com import FakeCom
from tests.capital.profit_rows import PNL_3357_MARGIN, pnl_variant

_SIM_RTT_S = 0.02  # 因果順序與「鏈會落地」都與 RTT 大小無關;150 ms 只是敘事(review F-15)
_PROFIT_ROW = pnl_variant(PNL_3357_MARGIN, {3: "現股", 25: "1"})  # 30 欄 fixture,pr-119 F-05
_OI_ROW = "TF,F9999999,TXFI6,B,2,0,23000.0"


def _client(com: FakeCom, tmp_path: Path) -> CapitalClient:
    client = CapitalClient(
        com,
        user_id="u",
        password="p",
        full_account="1234567890A",
        env="test",
        safety=SafetyConfig(order_enabled=True, max_qty=5, max_amount=None),
        audit_base=tmp_path / "audit",
    )
    client._status = "ok"
    client._futures_account = "F9999999"
    return client


def _fill_evt_raw(seq: str = "S1", qty: str = "1000", price: str = "90.0000") -> str:
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TS", "D", "N"
    arr[6], arr[8], arr[11], arr[20] = "B00R2", "3357", price, qty
    return ",".join(arr)


def _run_chain(client: CapitalClient, com: FakeCom, *, until: Callable[[], bool], budget_s: float) -> None:
    """模擬券商:看到查詢後 `_SIM_RTT_S` 才餵回覆;直到 `until()` 成立或預算用盡。"""
    replies: dict[str, tuple[Callable[[str], None], list[str]]] = {
        "get_real_balance": (client._handle_balance, [RAW_T_HELD, "##"]),
        "get_profit_loss_gw": (client._handle_profit, ["000,查詢成功", _PROFIT_ROW, "##,,,,"]),
        "get_open_interest": (client._handle_open_interest, [_OI_ROW, "##"]),
    }
    seen_at: dict[str, float] = {}
    answered: set[str] = set()
    deadline = time.monotonic() + budget_s
    while time.monotonic() < deadline and not until():
        client._pump_once()
        now = time.monotonic()
        for name in replies:
            if name not in seen_at and any(entry[0] == name for entry in com.sent):
                seen_at[name] = now
            if name in seen_at and name not in answered and now - seen_at[name] >= _SIM_RTT_S:
                handler, rows = replies[name]
                for row in rows:
                    handler(row)
                answered.add(name)
        time.sleep(0.01)


def test_fill_reaches_positions_before_broker_chain_starts(tmp_path: Path) -> None:
    """不變量以**因果順序**釘(review Std 4):第一則 `capital_position` 必須早於第一次
    `GetRealBalanceReport` 查詢出手 —— 這正是「不等回查鏈」的定義;牆鐘毫秒只進失敗訊息,
    不當門檻(負載機 / CI 上體質性 flaky)。修前這裡是 463 ms、且順序反過來。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    stamps: dict[str, float] = {}
    order: list[str] = []

    def broadcast(payload: dict[str, object]) -> None:
        if payload["event"] == "capital_position" and "position" not in stamps:
            stamps["position"] = time.monotonic()
            order.append("position")
            if any(entry[0] == "get_real_balance" for entry in com.sent):
                order.append("balance-query-was-already-sent")

    client.set_broadcast(broadcast)
    client.store.set_positions([])  # 開機首次快照已落地(樂觀套用只在其後開,review F-02)
    t_fill = time.monotonic()
    client._handle_reply(_fill_evt_raw())
    _run_chain(client, com, until=lambda: "position" in stamps, budget_s=3.0)

    assert "position" in stamps, "成交後 3 s 內沒有任何 capital_position 推播"
    latency_ms = (stamps["position"] - t_fill) * 1000
    assert order == ["position"], f"部位推播晚於回查鏈出手(fill → 推播 {latency_ms:.0f} ms):{order}"
    pos = client.store.position_for("3357")
    assert pos is not None and pos.qty == 1 and pos.kind == "cash" and pos.avg_price == 90.0


def test_broker_chain_still_overrides_optimistic_fill(tmp_path: Path) -> None:
    """樂觀套用只是先到;回查鏈落地後以券商為準(3 張、均價 150.55、期貨列也在)。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    finalized: list[int] = []

    def broadcast(payload: dict[str, object]) -> None:
        if payload["event"] == "capital_position" and payload["data"].get("source") != "fill":  # type: ignore[union-attr]
            finalized.append(1)

    client.set_broadcast(broadcast)
    client.store.set_positions([])
    client._handle_reply(_fill_evt_raw())
    _run_chain(client, com, until=lambda: bool(finalized), budget_s=3.0)

    assert finalized, "回查鏈 3 s 內未落地"
    sec = client.store.position_for("3357")
    fut = client.store.position_for("TXFI6")
    assert sec is not None and sec.qty == 3 and sec.avg_price == 150.55
    assert fut is not None and fut.qty == 2


def test_chain_landing_does_not_regress_fill_arrived_in_flight(tmp_path: Path) -> None:
    """倒退 repro(next-time L57):balance 查詢出手後、落地前又有成交 —— 快照取數
    早於 fill B,落地的全量覆蓋不得把樂觀套用的 fill B 倒退掉(user 08-28:
    「樂觀更新不該被資料拿到後改動」;prod 症狀 = 部位閃回舊值 ~2 s / 少一檔 60 s)。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    client.store.set_positions([])  # 開機首次快照已落地
    client._handle_reply(_fill_evt_raw(seq="S1"))  # fill A → 樂觀 1 張
    client._mark_balance_dirty(0.0)
    client._pump_once()
    assert any(e[0] == "get_real_balance" for e in com.sent), "balance 查詢未出手"
    # 券商取數時刻 = 查詢出手當下:只看得到 fill A(1 張)
    client._handle_balance(balance_variant(RAW_T_HELD, {11: "1000", 14: "1000"}))
    client._handle_balance("##")
    client._pump_once()
    # fill B 在鏈飛行中(損益段未回)到達 → 樂觀 2 張
    client._handle_reply(_fill_evt_raw(seq="S2"))
    mid = client.store.position_for("3357")
    assert mid is not None and mid.qty == 2
    client._handle_profit("000,查詢成功")
    client._handle_profit(_PROFIT_ROW)
    client._handle_profit("##,,,,")
    client._handle_open_interest("##")
    client._pump_once()
    p = client.store.position_for("3357")
    assert p is not None and p.qty == 2, (
        f"快照落地把鏈飛行中的成交倒退:qty={p.qty if p else None}"
    )


def test_fill_covered_by_watermark_is_not_reapplied(tmp_path: Path) -> None:
    """水位護欄的另一半:查詢出手**前**的成交已在快照裡,落地時不得再套一次(雙計)。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    client.store.set_positions([])
    client._handle_reply(_fill_evt_raw(seq="S1"))  # fill A → 樂觀 1 張
    client._mark_balance_dirty(0.0)
    client._pump_once()  # 查詢出手,水位涵蓋 fill A
    client._handle_balance(balance_variant(RAW_T_HELD, {11: "1000", 14: "1000"}))  # 快照含 A
    client._handle_balance("##")
    client._handle_profit("000,查詢成功")
    client._handle_profit(_PROFIT_ROW)
    client._handle_profit("##,,,,")
    client._handle_open_interest("##")
    client._pump_once()
    p = client.store.position_for("3357")
    assert p is not None and p.qty == 1, f"水位前成交被重套成雙計:qty={p.qty if p else None}"


# ---------------------------------------------------------------- #234 回報鏈量測去污染


class _Broker:
    """跨多輪鏈的假券商:每看到一次新查詢就在 `_SIM_RTT_S` 後餵一次回覆(`_run_chain` 只答一次,
    要驗「第二輪鏈才涵蓋成交」得能答兩輪)。"""

    def __init__(self, client: CapitalClient, com: FakeCom) -> None:
        self._client = client
        self._com = com
        self._replies: dict[str, tuple[Callable[[str], None], list[str]]] = {
            "get_real_balance": (client._handle_balance, [RAW_T_HELD, "##"]),
            "get_profit_loss_gw": (client._handle_profit, ["000,查詢成功", _PROFIT_ROW, "##,,,,"]),
            "get_open_interest": (client._handle_open_interest, [_OI_ROW, "##"]),
        }
        self._answered = dict.fromkeys(self._replies, 0)
        self._due: dict[str, float] = {}

    def run(self, *, until: Callable[[], bool], budget_s: float) -> None:
        deadline = time.monotonic() + budget_s
        while time.monotonic() < deadline and not until():
            self._client._pump_once()
            now = time.monotonic()
            for name, (handler, rows) in self._replies.items():
                sent = sum(1 for entry in self._com.sent if entry[0] == name)
                if sent > self._answered[name] and name not in self._due:
                    self._due[name] = now
                if name in self._due and now - self._due[name] >= _SIM_RTT_S:
                    for row in rows:
                        handler(row)
                    self._answered[name] += 1
                    del self._due[name]
            time.sleep(0.005)


_ELAPSED = re.compile(r"自成交回報到達起 (\d+) ms")


def _elapsed_info(caplog: pytest.LogCaptureFixture) -> list[int]:
    """INFO 級「balance 鏈」行上的累積值,依出現序。"""
    out: list[int] = []
    for r in caplog.records:
        if r.levelno == logging.INFO and r.name == "copycat.capital.client":
            m = _ELAPSED.search(r.getMessage())
            if m:
                out.append(int(m.group(1)))
    return out


def _landed_info(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and "部位落地" in r.getMessage() and "自成交" in r.getMessage()
    ]


def test_fill_in_flight_keeps_chain_timer_origin(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """鏈飛行中(庫存段已收、損益段未回)再來一筆成交,計時器**不歸零**:四段累積值單調遞增、
    落地印「涵蓋 2 筆成交」。修前 `_fill_seen_at` 每筆成交覆寫 → 損益段的數字比庫存段還小
    (V2 抓到的「累積值非單調」指紋,8 / 178 條)。白名單:群益查詢節奏不變 —— 落地時只出過
    一次庫存查詢,fill B 武裝的重查在落地**之後**才出手(成交不漏)。"""
    caplog.set_level(logging.INFO, logger="copycat.capital.client")
    com = FakeCom()
    client = _client(com, tmp_path)
    client.store.set_positions([])
    broker = _Broker(client, com)
    client._balance_last_ts = time.monotonic()  # 開機首圈的 60 s 輪詢已過;走成交 debounce 路徑

    client._handle_reply(_fill_evt_raw(seq="S1"))
    broker.run(until=lambda: len(_elapsed_info(caplog)) >= 1, budget_s=3.0)  # 庫存段收齊
    assert _elapsed_info(caplog)[0] >= 500  # 0.5 s debounce 在裡面
    client._handle_reply(_fill_evt_raw(seq="S2"))  # 鏈飛行中第二筆成交
    broker.run(until=lambda: bool(_landed_info(caplog)), budget_s=3.0)

    elapsed = _elapsed_info(caplog)
    assert len(elapsed) == 4, elapsed
    assert elapsed == sorted(elapsed), f"累積值倒退(計時器被中途歸零):{elapsed}"
    assert "涵蓋 2 筆成交" in _landed_info(caplog)[0]
    balance_queries = lambda: sum(1 for e in com.sent if e[0] == "get_real_balance")  # noqa: E731
    assert balance_queries() == 1  # 落地當下只出過一次庫存查詢(鏈中不重發)
    broker.run(until=lambda: balance_queries() >= 2, budget_s=3.0)
    assert balance_queries() == 2  # fill B 武裝的重查在落地後出手:成交不漏(白名單)


def test_fill_during_stale_poll_chain_is_measured_by_the_next_chain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """60 s 定時輪詢的鏈飛行中來了成交:那輪鏈**沒涵蓋**這筆成交(查詢早於成交出手),各段維持
    DEBUG、落地不印耗時;成交武裝的下一輪才印 INFO 且「涵蓋 1 筆成交」。修前:成交點亮 `_fill_seen_at`
    後,輪詢那輪的剩餘段就印出幾百 ms 的假數字(V2 的「缺庫存段起點」指紋,4 條)。"""
    caplog.set_level(logging.INFO, logger="copycat.capital.client")
    com = FakeCom()
    client = _client(com, tmp_path)
    client.store.set_positions([])
    broker = _Broker(client, com)
    landings: list[int] = []
    client.set_broadcast(
        lambda payload: landings.append(1)
        if payload["event"] == "capital_position" and payload["data"].get("source") != "fill"  # type: ignore[union-attr]
        else None
    )

    client._pump_once()  # `_balance_last_ts` 初值 0 → 開機首圈就是 60 s 定時輪詢那輪
    assert any(e[0] == "get_real_balance" for e in com.sent), "定時輪詢未出手"
    client._handle_reply(_fill_evt_raw(seq="S1"))  # 成交在輪詢鏈飛行中到達
    broker.run(until=lambda: len(landings) >= 1, budget_s=3.0)
    assert landings == [1]
    assert _elapsed_info(caplog) == [], "輪詢那輪沒涵蓋這筆成交,不得印耗時"

    broker.run(until=lambda: len(landings) >= 2, budget_s=3.0)
    assert landings == [1, 1]
    elapsed = _elapsed_info(caplog)
    assert len(elapsed) == 4 and elapsed == sorted(elapsed), elapsed
    assert elapsed[0] >= 500
    assert "涵蓋 1 筆成交" in _landed_info(caplog)[0]
