"""成交回報 → 部位可見的時序 loop(feat/chart-ux-batch-0826 F5;diagnosing-bugs Phase 1)。

真成交要真下單(花錢),loop 改用 FakeCom 重現**結構性**延遲:券商三段回查
(庫存 → 損益 → 期貨部位)各模擬 150 ms 往返。修前部位只由回查鏈餵,
fill → `capital_position` ≈ 0.5 s debounce + 3 × 150 ms ≈ 0.95 s;修後成交當下樂觀套用
並立即推播,< 50 ms。時間門檻取 50 ms 而不是「0」:幫浦圈本身 10 ms 級,留餘裕。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from tests.capital.fake_com import FakeCom
from tests.capital.profit_rows import PNL_3357_MARGIN, pnl_variant

_SIM_RTT_S = 0.02  # 因果順序與「鏈會落地」都與 RTT 大小無關;150 ms 只是敘事(review F-15)
_BAL_ROW = "3357,T,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
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
        "get_real_balance": (client._handle_balance, [_BAL_ROW, "##"]),
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
