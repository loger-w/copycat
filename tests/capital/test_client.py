"""CapitalClient:COM 執行緒橋 + 閘/審計/雙帳號路由(SC-1/2/3/4/6/9)。

治具 tests/capital/fake_com.py(FakeCom 收集 sent、RecordingCom 記啟動序列)。
寫入紀律(design §3/§9):master 閘 → 各閘(不過 = 審計 blocked 行 + raise
CapitalGateBlockedError)→ 審計前置(失敗 raise AuditWriteError 整筆失敗)→
COM(10s timeout → 結果未知)→ 審計後置(失敗只 log、不改 OrderResult)。
"""

from __future__ import annotations

import asyncio
import json
import queue
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

import copycat.capital.client as client_mod
import copycat.stkfut_map as stkfut_map
from copycat.capital.client import CapitalClient
from copycat.capital.com import CapitalCom
from copycat.capital.models import (
    CancelOrderRequest,
    CapitalDownError,
    CapitalGateBlockedError,
    CapitalNotReadyError,
    CorrectPriceRequest,
    DecreaseQtyRequest,
    FutureOrderRequest,
    OrderResult,
    Position,
    PositionCloseRequest,
    StockOrderRequest,
)
from copycat.capital.reply import parse_onnewdata
from copycat.capital.safety import SafetyConfig
from copycat.server.audit import AuditWriteError
from copycat.stkfut_map import write_map
from copycat.live.trade_models import BrokerRejectedError
from tests.capital.fake_com import FakeCom, RecordingCom, RejectingCom

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _client(
    com: FakeCom,
    tmp_path: Path,
    *,
    enabled: bool = True,
    env: str = "test",
    max_qty: int | None = 5,
    max_amount: float | None = None,
) -> CapitalClient:
    return CapitalClient(
        com,
        user_id="u",
        password="p",
        full_account="1234567890A",
        env=env,
        safety=SafetyConfig(order_enabled=enabled, max_qty=max_qty, max_amount=max_amount),
        audit_base=tmp_path / "audit",
    )


def _mark_ready(client: CapitalClient, futures_account: str | None = "F9999999") -> None:
    """不跑真執行緒:直接標 ok + 注入期貨帳號(佇列由 _drive 消化)。"""
    client._status = "ok"
    client._futures_account = futures_account


async def _drive(
    client: CapitalClient, factory: Callable[[], Awaitable[OrderResult]]
) -> OrderResult:
    """測試替代 COM 執行緒:綁 running loop、邊讓步邊 drain 佇列(與 _run 同構)。
    審計走 to_thread(review B6)→ 命令入佇列的時點跨多輪 loop,
    需輪詢至 task 完成(卡死由 _WRITE_TIMEOUT_S 10s 收束,不會無限迴圈)。"""
    client._loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(factory())
    while not task.done():
        await asyncio.sleep(0)
        try:
            cmd = client._cmd_q.get_nowait()
        except queue.Empty:
            continue
        if cmd is None:
            continue
        fn, fut = cmd
        try:
            fut.set_result(fn())
        except Exception as e:  # noqa: BLE001 — 與 production _run 同構
            fut.set_exception(e)
    return await task


def _audit_lines(client: CapitalClient) -> list[dict[str, Any]]:
    files = sorted((client._audit_base).glob("*.jsonl"))
    out: list[dict[str, Any]] = []
    for f in files:
        out.extend(json.loads(line) for line in f.read_text(encoding="utf-8").splitlines())
    return out


def _stock_evt_raw(seq: str, qty: str = "1000", price: str = "90.0000", bs: str = "B00R2") -> str:
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TS", "N", "N"
    arr[6], arr[8], arr[11], arr[20] = bs, "3357", price, qty
    return ",".join(arr)


def _fut_evt_raw(seq: str, contract: str = "TXFI6", qty: str = "2", price: str = "23000") -> str:
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TF", "N", "N"
    arr[6], arr[8], arr[11], arr[20] = "BNR20", contract, price, qty
    return ",".join(arr)


def _fill_evt_raw(seq: str = "S1", qty: str = "1000", price: str = "90.0000") -> str:
    """成交回報(Type=D):觸發 balance 重查排程。"""
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TS", "D", "N"
    arr[6], arr[8], arr[11], arr[20] = "B00R2", "3357", price, qty
    return ",".join(arr)


def _balance_queries(com: FakeCom) -> int:
    return sum(1 for entry in com.sent if entry[0] == "get_real_balance")


def _stock_req(qty: int = 2) -> StockOrderRequest:
    return StockOrderRequest(stock_no="2330", buy_sell="buy", price=590.0, qty=qty)


def _fut_req(**kw: Any) -> FutureOrderRequest:
    base: dict[str, Any] = {
        "tc4_symbol": "TC.F.TWF.TXF.202609",
        "buy_sell": "buy",
        "price": 23000.0,
        "qty": 2,
    }
    base.update(kw)
    return FutureOrderRequest(**base)


def _sent_fields(entry: tuple[object, ...]) -> dict[str, object]:
    """sent tuple 第二欄的 fields dict(pyright 收窄用)。"""
    fields = entry[1]
    assert isinstance(fields, dict)
    return fields


def test_fake_com_satisfies_protocol() -> None:
    c: CapitalCom = FakeCom()  # pyright 驗 Protocol 完整性
    assert c.set_authority(2) == 0


# ---------------------------------------------------------------------------
# 啟動序列 / TF 帳號自動發現(SC-1)
# ---------------------------------------------------------------------------


def test_init_com_sequence_order(tmp_path: Path) -> None:
    com = RecordingCom()
    client = _client(com, tmp_path)
    assert client._init_com() is True
    assert com.calls == [
        "setup",
        "set_authority",
        "login",
        "init_order",
        "read_cert",
        "connect_reply",
        "get_user_accounts",
    ]
    assert client.status == "ok"
    assert com.authority == 2  # env=test → SetAuthority(2)


def test_init_com_prod_authority_zero(tmp_path: Path) -> None:
    com = RecordingCom()
    client = _client(com, tmp_path, env="prod")
    assert client._init_com() is True
    assert com.authority == 0


def test_futures_account_discovered_from_tf_market(tmp_path: Path) -> None:
    com = FakeCom()  # 預設含 ("TF", "F9999999")
    client = _client(com, tmp_path)
    assert client._init_com() is True
    assert client.futures_account == "F9999999"


def test_no_tf_account_warns_and_leaves_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    com = FakeCom(accounts=[("TS", "1234567890A")])
    client = _client(com, tmp_path)
    with caplog.at_level("WARNING"):
        assert client._init_com() is True
    assert client.futures_account is None
    assert any("期貨" in r.message for r in caplog.records)


def test_connect_reply_failure_degrades_but_init_succeeds(tmp_path: Path) -> None:
    com = RecordingCom()
    com.connect_reply_rc = 3001
    client = _client(com, tmp_path)
    assert client._init_com() is True
    assert client.status == "degraded"
    assert client.last_error is not None
    # 回報失敗不可中斷後續:帳號發現仍要跑
    assert "get_user_accounts" in com.calls


def test_status_change_broadcasts_capital_status(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    pushed: list[dict[str, object]] = []
    client.set_broadcast(pushed.append)
    assert client._init_com() is True
    assert any(p["event"] == "capital_status" for p in pushed)


# ---------------------------------------------------------------------------
# 證券送單 fields 逐欄(SC-2)
# ---------------------------------------------------------------------------


async def test_submit_stock_fields_and_result(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    res = await _drive(client, lambda: client.submit_stock_order(_stock_req()))
    assert res.ok is True and res.code == 0
    assert res.seq_no == "SEQ0001"
    kind, fields = com.sent[0][0], com.sent[0][1]
    assert kind == "stock"
    assert fields == {
        "bstrFullAccount": "1234567890A",
        "bstrStockNo": "2330",
        "sBuySell": 0,
        "bstrPrice": "590.00",
        "nQty": 2,
        "nSpecialTradeType": 2,
        "nTradeType": 0,
        "sFlag": 0,
        "sPeriod": 0,
        "sPrime": 0,
    }
    lines = _audit_lines(client)
    assert len(lines) == 2  # 前置 + 後置
    assert lines[0]["action"] == "order" and lines[0]["result"] is None
    assert lines[1]["result"]["ok"] is True
    assert lines[0]["env"] == "test" and lines[0]["req"]["stock_no"] == "2330"


# ---------------------------------------------------------------------------
# 期貨/選擇權送單分流 + ROD→IOC 註記(SC-3)
# ---------------------------------------------------------------------------


async def test_submit_future_goes_send_future_order(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    res = await _drive(
        client, lambda: client.submit_future_order(_fut_req(), contract="TXFI6", multiplier=200)
    )
    assert res.ok is True and res.seq_no == "SEQF001"
    kind, fields, is_option = com.sent[0]
    assert kind == "future" and is_option is False
    assert fields == {
        "bstrFullAccount": "F9999999",
        "bstrStockNo": "TXFI6",
        "bstrPrice": "23000",
        "sTradeType": 0,
        "sBuySell": 0,
        "sDayTrade": 0,
        "sNewClose": 2,
        "nQty": 2,
    }


async def test_submit_option_goes_send_option_order(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    req = _fut_req(tc4_symbol="TC.O.TWF.TXO.202609.C.20000", price=300.0, qty=1)
    await _drive(
        client, lambda: client.submit_future_order(req, contract="TXO20000I6", multiplier=50)
    )
    kind, _fields, is_option = com.sent[0]
    assert kind == "future" and is_option is True
    assert _sent_fields(com.sent[0])["bstrStockNo"] == "TXO20000I6"


async def test_weekly_contract_routes_as_option(tmp_path: Path) -> None:
    # TX4 週選是選擇權家族(已知產品),走 SendOptionOrder
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    req = _fut_req(tc4_symbol="TC.O.TWF.TX4.202607.C.23000", price=100.0, qty=1)
    await _drive(
        client, lambda: client.submit_future_order(req, contract="TX423000G6", multiplier=50)
    )
    assert com.sent[0][2] is True


def _stkfut_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """個股期對映表注入(隔離版控真檔;CDF=標準 2000、QFF=小型 100)—— 同 test_capital_api 慣例。

    `lookup_product` 的 process 級索引 cache 以 path + stat 簽章為鍵,tmp_path 天然隔離。
    """
    path = tmp_path / "stkfut_map.json"
    write_map(
        path,
        {
            "2330": {
                "prod": "CDF",
                "name": "台積電",
                "unit": 2000,
                "mini": {"prod": "QFF", "unit": 100},
            }
        },
    )
    monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", path)


@pytest.mark.parametrize(
    "symbol,contract,multiplier",
    [
        ("TC.F.TWF.CDF.202609", "CDFI6", 2000),  # 標準腿
        ("TC.F.TWF.QFF.202609", "QFFI6", 100),  # 小型腿
    ],
)
async def test_stock_future_routes_as_future(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
    contract: str,
    multiplier: int,
) -> None:
    """個股期是**期貨**,必須走 SendFutureOrder。

    舊分流是「非 {TXF, MXF, TMF} → 選擇權」的封閉白名單,個股期落到選擇權那側 ——
    最好情況群益/期交所退單(功能整條不可用),最壞情況選擇權通道解讀 FUTUREORDER
    struct 送出非預期委託。真錢面。
    """
    _stkfut_map(tmp_path, monkeypatch)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    req = _fut_req(tc4_symbol=symbol, price=1180.0, qty=1)
    await _drive(
        client, lambda: client.submit_future_order(req, contract=contract, multiplier=multiplier)
    )
    kind, _fields, is_option = com.sent[0]
    assert kind == "future" and is_option is False
    assert _sent_fields(com.sent[0])["bstrStockNo"] == contract


async def test_close_stock_future_position_routes_as_future(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 平倉走同一支 submit_future_order → 同一個分流缺陷(既有部位平不掉)
    _stkfut_map(tmp_path, monkeypatch)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions([Position(market="fut", stock_no="CDFI6", qty=1, avg_price=1180.0)])
    req = PositionCloseRequest(market="fut", key="CDFI6", price=1100.0)
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    assert com.sent[0][2] is False


async def test_close_adjusted_stock_future_routes_as_future(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """除權息調整後的個股期(第三碼變數字,如 EE1)平倉仍必須走 SendFutureOrder。

    這種碼進不了 `stkfut_map`(那份只組 XXF 形)→ 掉到結構判別;「body 含任何
    數字 = 選擇權」會讓它與本輪 P0 同樣走選擇權通道,而平倉的 fut 分支沒有單位閘
    可擋(乘數反查失敗只 warn 降 1),既有部位平不掉。
    """
    _stkfut_map(tmp_path, monkeypatch)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions([Position(market="fut", stock_no="EE1I6", qty=1, avg_price=60.0)])
    req = PositionCloseRequest(market="fut", key="EE1I6", price=55.0)
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    assert com.sent[0][2] is False


@pytest.mark.parametrize(
    "contract,is_option",
    [
        ("SXFI6", False),  # 未知產品、契約本體純字母 = 期貨形
        ("ZZZ20000I6", True),  # 未知產品、契約本體含履約價數字 = 選擇權形
    ],
)
async def test_unknown_product_routed_by_contract_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contract: str, is_option: bool
) -> None:
    """未知產品(對映表查無、非指數期權)以契約碼結構判別:選擇權碼必含履約價數字。

    白名單註定追不上上架節奏(個股期就是這樣漏掉的),預設方向必須由結構決定
    而不是「不認得就當選擇權」。
    """
    _stkfut_map(tmp_path, monkeypatch)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    req = _fut_req(price=100.0, qty=1)
    await _drive(client, lambda: client.submit_future_order(req, contract=contract, multiplier=1))
    assert com.sent[0][2] is is_option


async def test_market_rod_upgraded_to_ioc_with_message_note(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    req = _fut_req(price_type="market")  # 預設 TIF=ROD
    res = await _drive(
        client, lambda: client.submit_future_order(req, contract="TXFI6", multiplier=200)
    )
    fields = _sent_fields(com.sent[0])
    assert fields["bstrPrice"] == "M" and fields["sTradeType"] == 1  # IOC
    assert res.message.startswith("市價單已升級 IOC;")


async def test_market_explicit_ioc_no_message_note(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    req = _fut_req(price_type="market", time_in_force="IOC")
    res = await _drive(
        client, lambda: client.submit_future_order(req, contract="TXFI6", multiplier=200)
    )
    assert not res.message.startswith("市價單已升級")


async def test_future_order_no_futures_account_blocked(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.submit_future_order(_fut_req(), contract="TXFI6", multiplier=200)
    assert ei.value.reason == "no_futures_account"
    assert com.sent == []
    assert _audit_lines(client)[-1]["blocked"] == "no_futures_account"


async def test_future_amount_gate_uses_multiplier(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path, max_amount=1_000_000.0)
    _mark_ready(client)
    with pytest.raises(CapitalGateBlockedError) as ei:  # 23000×2×200 = 9.2M > 1M
        await client.submit_future_order(_fut_req(), contract="TXFI6", multiplier=200)
    assert ei.value.reason is not None and "超過上限" in ei.value.reason
    assert com.sent == []


# ---------------------------------------------------------------------------
# 閘不過 = 審計 blocked + raise;未就緒 raise(SC-9)
# ---------------------------------------------------------------------------


async def test_master_off_blocks_audits_and_never_touches_com(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path, enabled=False)
    _mark_ready(client)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.submit_stock_order(_stock_req())
    assert ei.value.reason == "order_disabled"
    assert com.sent == []
    lines = _audit_lines(client)
    assert len(lines) == 1
    assert lines[0]["blocked"] == "order_disabled" and lines[0]["result"] is None


async def test_master_off_precedes_no_futures_account(tmp_path: Path) -> None:
    # 稽核 blocked 要記真正原因:總開關關閉時不可被 no_futures_account 遮蔽
    com = FakeCom()
    client = _client(com, tmp_path, enabled=False)
    _mark_ready(client, futures_account=None)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.submit_future_order(_fut_req(), contract="TXFI6", multiplier=200)
    assert ei.value.reason == "order_disabled"


async def test_not_ready_raises_and_audits(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)  # status=starting、loop 未綁
    with pytest.raises(CapitalNotReadyError):
        await client.submit_stock_order(_stock_req())
    assert com.sent == []
    assert _audit_lines(client)[-1]["blocked"] == "capital_not_ready"


# ---------------------------------------------------------------------------
# cancel / correct / decrease:雙帳號路由 + market 交叉驗證(SC-4)
# ---------------------------------------------------------------------------


async def test_cancel_sec_routes_full_account(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    res = await _drive(
        client, lambda: client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec"))
    )
    assert res.ok is True
    assert ("cancel", "1234567890A", "S1") in com.sent


async def test_cancel_fut_routes_futures_account(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    await _drive(client, lambda: client.cancel_order(CancelOrderRequest(seq_no="F1", market="fut")))
    assert ("cancel", "F9999999", "F1") in com.sent


async def test_cancel_fut_without_account_blocked(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.cancel_order(CancelOrderRequest(seq_no="F1", market="fut"))
    assert ei.value.reason == "no_futures_account"
    assert com.sent == []


async def test_market_mismatch_blocked_both_ways(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_fut_evt_raw("F1")))  # store 記 TF
    client.store.apply_reply(parse_onnewdata(_stock_evt_raw("S1")))  # store 記 TS
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.cancel_order(CancelOrderRequest(seq_no="F1", market="sec"))
    assert ei.value.reason == "market_mismatch"
    with pytest.raises(CapitalGateBlockedError) as ei2:
        await client.decrease_qty(DecreaseQtyRequest(seq_no="S1", market="fut", qty=1))
    assert ei2.value.reason == "market_mismatch"
    assert com.sent == []
    assert _audit_lines(client)[-1]["blocked"] == "market_mismatch"


async def test_unknown_seq_trusts_request_market(tmp_path: Path) -> None:
    # review R3:斷線時 store 空仍要能刪單 — store 查無(None)信 request 的 market 放行
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    res = await _drive(
        client, lambda: client.cancel_order(CancelOrderRequest(seq_no="ghost", market="fut"))
    )
    assert res.ok is True
    assert ("cancel", "F9999999", "ghost") in com.sent


async def test_decrease_fut_routes_futures_account(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_fut_evt_raw("F1")))
    res = await _drive(
        client, lambda: client.decrease_qty(DecreaseQtyRequest(seq_no="F1", market="fut", qty=1))
    )
    assert res.ok is True
    assert ("decrease", "F9999999", "F1", 1) in com.sent


async def test_correct_price_sec_amount_gate_in_lots(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path, max_amount=100_000.0)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_stock_evt_raw("S9")))  # 未成交 1000 股 = 1 張
    with pytest.raises(CapitalGateBlockedError) as ei:  # 200×1張×1000 = 200,000 > 100,000
        await client.correct_price(CorrectPriceRequest(seq_no="S9", market="sec", price=200.0))
    assert ei.value.reason is not None and "超過上限" in ei.value.reason
    assert com.sent == []
    res = await _drive(
        client,
        lambda: client.correct_price(CorrectPriceRequest(seq_no="S9", market="sec", price=95.0)),
    )
    assert res.ok is True
    # review A6:COM 介面收字串,證券兩位小數(送單同慣例)
    assert ("correct_price", "1234567890A", "S9", "95.00") in com.sent


async def test_correct_price_fut_multiplier_lookup(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path, max_amount=1_000_000.0)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_fut_evt_raw("F1", contract="TXFI6")))
    with pytest.raises(CapitalGateBlockedError) as ei:  # 23000×2口×200 = 9.2M > 1M
        await client.correct_price(CorrectPriceRequest(seq_no="F1", market="fut", price=23000.0))
    assert ei.value.reason is not None and "超過上限" in ei.value.reason
    assert com.sent == []


async def test_correct_price_weekly_contract_multiplier_50(tmp_path: Path) -> None:
    # 週選契約碼反查:最長前綴比對 → TX4 → 乘數 50,不再 fallback 1(review A1)
    com = FakeCom()
    client = _client(com, tmp_path, max_amount=1_000_000.0)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_fut_evt_raw("W1", contract="TX422000T6", price="22000")))
    with pytest.raises(CapitalGateBlockedError) as ei:  # 22000×2口×50 = 2.2M > 1M(fallback 1 只有 44,000 會放行)
        await client.correct_price(CorrectPriceRequest(seq_no="W1", market="fut", price=22000.0))
    assert ei.value.reason is not None and "超過上限" in ei.value.reason
    assert com.sent == []


async def test_correct_price_fut_unknown_product_falls_back_multiplier_1(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    com = FakeCom()
    client = _client(com, tmp_path, max_amount=1_000_000.0)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_fut_evt_raw("F2", contract="ZZZZZ9")))
    with caplog.at_level("WARNING"):
        res = await _drive(
            client,
            lambda: client.correct_price(
                CorrectPriceRequest(seq_no="F2", market="fut", price=23000.0)
            ),
        )
    assert res.ok is True  # 23000×2×1 = 46,000 ≤ 1M(multiplier=1 fallback)
    assert ("correct_price", "F9999999", "F2", "23000") in com.sent  # fut 整數價無小數尾(A6)
    assert any("multiplier=1" in r.message for r in caplog.records)


async def test_correct_price_unknown_seq_allowed_r3(tmp_path: Path) -> None:
    # remaining=None(store 查無)→ 金額/數量閘跳過,只驗價 > 0(review R3 逃生口)
    com = FakeCom()
    client = _client(com, tmp_path, max_amount=1.0)
    _mark_ready(client)
    res = await _drive(
        client,
        lambda: client.correct_price(CorrectPriceRequest(seq_no="ghost", market="sec", price=9.0)),
    )
    assert res.ok is True
    assert ("correct_price", "1234567890A", "ghost", "9.00") in com.sent


async def test_correct_price_fut_price_string_no_decimal_tail(tmp_path: Path) -> None:
    # review A6:期貨改價價格字串走 mapping.future_price_str(整數價無 ".00" 尾),
    # 證券才是兩位小數 — %.2f 全市場共用會讓期貨端收到 "23000.00"
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.apply_reply(parse_onnewdata(_fut_evt_raw("F1", contract="TXFI6")))
    res = await _drive(
        client,
        lambda: client.correct_price(
            CorrectPriceRequest(seq_no="F1", market="fut", price=23000.0)
        ),
    )
    assert res.ok is True
    assert ("correct_price", "F9999999", "F1", "23000") in com.sent


# ---------------------------------------------------------------------------
# 群益拒單透傳(review A2/C1):code≠0 → 後置審計 ok=False → BrokerRejectedError
# ---------------------------------------------------------------------------


async def test_com_reject_raises_broker_rejected_and_audits(tmp_path: Path) -> None:
    com = RejectingCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    with pytest.raises(BrokerRejectedError) as ei:
        await _drive(client, lambda: client.submit_stock_order(_stock_req()))
    assert ei.value.err_code == "1097"
    assert "查無委託" in ei.value.err_msg
    lines = _audit_lines(client)  # 後置審計先落(result ok=False)再 raise
    assert lines[-1]["result"]["ok"] is False
    assert lines[-1]["result"]["code"] == 1097


async def test_com_reject_cancel_and_future_paths(tmp_path: Path) -> None:
    com = RejectingCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    with pytest.raises(BrokerRejectedError):
        await _drive(
            client, lambda: client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec"))
        )
    with pytest.raises(BrokerRejectedError):
        await _drive(
            client,
            lambda: client.submit_future_order(_fut_req(), contract="TXFI6", multiplier=200),
        )


# ---------------------------------------------------------------------------
# timeout / COM 例外 / 執行緒亡故(SC-1)
# ---------------------------------------------------------------------------


async def test_write_timeout_returns_unknown_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_mod, "_WRITE_TIMEOUT_S", 0.01)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._loop = asyncio.get_running_loop()
    # 不 drain 佇列 = COM 卡死
    res = await client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec"))
    assert res.ok is False and res.code == -1 and res.seq_no is None
    assert res.message == "結果未知,勿重送"
    lines = _audit_lines(client)
    assert lines[-1]["result"]["message"] == "結果未知,勿重送"


async def test_route_cancel_late_result_audited_and_cancel_not_swallowed(tmp_path: Path) -> None:
    # review B1:route task 取消(cancel-chain)時真錢單可能已送出 —
    # CancelledError 不可吞、COM 晚到結果要補後置審計(late=true)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec")))
    for _ in range(200):  # 等命令入佇列(前置審計後)
        await asyncio.sleep(0.005)
        if not client._cmd_q.empty():
            break
    else:
        raise AssertionError("命令未入佇列")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    cmd = client._cmd_q.get_nowait()
    assert cmd is not None
    fn, fut = cmd
    fut.set_result(fn())  # COM 晚回(執行緒側 _settle 等價)
    await asyncio.sleep(0)  # 消化 done_callback
    lines = _audit_lines(client)
    late = [ln for ln in lines if ln.get("late")]
    assert len(late) == 1
    assert late[0]["result"]["ok"] is True and late[0]["result"]["seq_no"] == "OK"


async def test_timeout_then_late_result_appends_late_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # review B1:timeout 已審計「結果未知」,COM 晚回再補第二行(late=true)
    monkeypatch.setattr(client_mod, "_WRITE_TIMEOUT_S", 0.01)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._loop = asyncio.get_running_loop()
    res = await client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec"))
    assert res.message == "結果未知,勿重送"
    cmd = client._cmd_q.get_nowait()
    assert cmd is not None
    fn, fut = cmd
    fut.set_result(fn())
    await asyncio.sleep(0)
    lines = _audit_lines(client)
    assert len(lines) == 3  # 前置 + 結果未知後置 + late 補記
    assert lines[-1].get("late") is True
    assert lines[-1]["result"]["ok"] is True


async def test_com_exception_raises_capital_down_and_audits(tmp_path: Path) -> None:
    class BoomCom(FakeCom):
        def cancel_order(self, user_id: str, full_account: str, seq_no: str) -> tuple[str, int]:
            raise RuntimeError("COM died")

    com = BoomCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    with pytest.raises(CapitalDownError):
        await _drive(
            client, lambda: client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec"))
        )
    lines = _audit_lines(client)
    assert "COM 例外" in lines[-1]["result"]["message"]


def test_run_thread_exit_drops_status_and_drains_pending(tmp_path: Path) -> None:
    com = RecordingCom()
    client = _client(com, tmp_path)
    loop = asyncio.new_event_loop()
    try:
        client._loop = loop
        fut: asyncio.Future[tuple[str, int]] = loop.create_future()
        client._cmd_q.put(None)  # 終止訊號:init 成功後第一輪 break
        client._cmd_q.put(((lambda: ("OK", 0)), fut))  # 終止後殘留的命令
        client._run()
        loop.run_until_complete(asyncio.sleep(0))  # 消化 call_soon_threadsafe
        assert client.status == "error"
        assert client.last_error is not None
        assert fut.done() and isinstance(fut.exception(), RuntimeError)
    finally:
        loop.close()


def test_run_survives_closed_loop_on_result_settle(tmp_path: Path) -> None:
    # review B5:主圈 call_soon_threadsafe 撞上已關閉 loop(行程收尾競態)
    # 不可讓例外炸出 _run — 對齊 _drain_pending 的 RuntimeError guard
    com = RecordingCom()
    client = _client(com, tmp_path)
    loop = asyncio.new_event_loop()
    fut: asyncio.Future[tuple[str, int]] = loop.create_future()
    loop.close()
    client._loop = loop
    client._cmd_q.put(((lambda: ("OK", 0)), fut))
    client._run()  # 不得 raise:RuntimeError → log + break → finally 收尾
    assert client.status == "error"


def test_pump_once_swallows_exceptions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)  # 防洪水節流不拖慢測試
    com = FakeCom()
    client = _client(com, tmp_path)

    def boom() -> None:
        raise RuntimeError("COM 斷線")

    com.pump = boom  # type: ignore[method-assign]
    client._pump_once()  # 不得 raise


# ---------------------------------------------------------------------------
# 審計不對稱紀律(SC-9;design §9)
# ---------------------------------------------------------------------------


async def test_audit_pre_write_failure_fails_whole_request(tmp_path: Path) -> None:
    # audit_base 位置被檔案佔住 → mkdir 失敗 → 前置審計寫不進去 = 整筆失敗、錢不動
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._audit_base.parent.mkdir(parents=True, exist_ok=True)
    client._audit_base.write_text("occupied", encoding="utf-8")
    with pytest.raises(AuditWriteError):
        await client.submit_stock_order(_stock_req())
    assert com.sent == []


async def test_audit_post_write_failure_keeps_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 命令已出手後審計寫失敗只能 log:回失敗會誘發重送 → 真錢重複下單
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    calls = {"n": 0}
    real_append = client_mod.append_audit

    def flaky(base: Path, record: dict[str, Any], *, when: Any, prefix: str = "orders") -> None:
        calls["n"] += 1
        if calls["n"] >= 2:  # 前置成功、後置失敗
            raise AuditWriteError("disk full")
        real_append(base, record, when=when, prefix=prefix)

    monkeypatch.setattr(client_mod, "append_audit", flaky)
    res = await _drive(client, lambda: client.submit_stock_order(_stock_req()))
    assert res.ok is True and res.seq_no == "SEQ0001"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# close_position:sec/fut 組裝 + 防重送(SC-6)
# ---------------------------------------------------------------------------


async def test_close_sec_builds_reverse_order_and_blocks_second_inflight(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions([Position(market="sec", stock_no="2330", qty=1, kind="margin")])
    req = PositionCloseRequest(market="sec", key="2330", price=590.0)
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    assert com.sent[0][0] == "stock"
    fields = _sent_fields(com.sent[0])
    assert fields["sBuySell"] == 1 and fields["sFlag"] == 1  # 融資多 → 融資賣
    assert _audit_lines(client)[-1]["action"] == "close"
    with pytest.raises(CapitalGateBlockedError) as ei:  # in-flight 10s 防重送
        await client.close_position(req)
    assert ei.value.reason is not None and "在途" in ei.value.reason
    assert len(com.sent) == 1
    assert "在途" in _audit_lines(client)[-1]["blocked"]


async def test_close_inflight_unlocked_when_gate_blocks_submit(tmp_path: Path) -> None:
    # review A8:submit 被前置閘擋下(錢沒動)→ in-flight 鎖解除,
    # 立即重試看到的是真正的擋單原因,不是「在途」
    com = FakeCom()
    client = _client(com, tmp_path, enabled=False)
    _mark_ready(client)
    client.store.set_positions([Position(market="sec", stock_no="2330", qty=1, kind="cash")])
    req = PositionCloseRequest(market="sec", key="2330", price=590.0)
    for _ in range(2):  # 第二次不可被「在途」擋
        with pytest.raises(CapitalGateBlockedError) as ei:
            await client.close_position(req)
        assert ei.value.reason == "order_disabled"
    # 複合鍵("2330:cash")亦已解鎖 — 斷言空 dict 而非「某鍵不在」,避免改鍵後恆真變 vacuous
    assert client._close_inflight == {}
    assert com.sent == []


async def test_close_fut_inflight_unlocked_when_gate_blocks_submit(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path, enabled=False)
    _mark_ready(client)
    client.store.set_positions(
        [Position(market="fut", stock_no="TXFI6", qty=1, avg_price=23000.0)]
    )
    req = PositionCloseRequest(market="fut", key="TXFI6", price=22000.0)
    for _ in range(2):
        with pytest.raises(CapitalGateBlockedError) as ei:
            await client.close_position(req)
        assert ei.value.reason == "order_disabled"
    assert "TXFI6" not in client._close_inflight


async def test_close_sec_no_position_blocked(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.close_position(PositionCloseRequest(market="sec", key="2330", price=590.0))
    assert ei.value.reason is not None and "無部位可平" in ei.value.reason
    assert com.sent == []
    assert "無部位可平" in _audit_lines(client)[-1]["blocked"]


async def test_close_sec_blocked_by_same_side_active_order(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions([Position(market="sec", stock_no="3357", qty=1, kind="cash")])
    client.store.apply_reply(parse_onnewdata(_stock_evt_raw("S1", bs="S00R2")))  # 活躍賣單
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.close_position(PositionCloseRequest(market="sec", key="3357", price=90.0))
    assert ei.value.reason is not None and "活躍委託" in ei.value.reason
    assert com.sent == []


async def test_close_fut_builds_reverse_ioc_new_close_1(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(
        [Position(market="fut", stock_no="TXFI6", qty=2, avg_price=23000.0)]
    )
    req = PositionCloseRequest(market="fut", key="TXFI6", price=22000.0)
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    kind, _fields, is_option = com.sent[0]
    assert kind == "future" and is_option is False
    fields = _sent_fields(com.sent[0])
    assert fields["sBuySell"] == 1  # 多倉 → 反向賣
    assert fields["sNewClose"] == 1  # 倉別=平倉
    assert fields["sTradeType"] == 1  # IOC
    assert fields["bstrPrice"] == "22000"  # 限價貼漲跌停(req.price)
    assert fields["nQty"] == 2
    assert _audit_lines(client)[-1]["action"] == "close"
    with pytest.raises(CapitalGateBlockedError):  # 防重送同樣生效
        await client.close_position(req)
    assert len(com.sent) == 1


# ── 複合鍵 (stock_no, kind) 防回歸 ──────────────────────────────


def _sec_positions_two_kinds() -> list[Position]:
    return [
        Position(market="sec", stock_no="2330", qty=1, kind="cash"),
        Position(market="sec", stock_no="2330", qty=3, kind="margin"),
    ]


async def test_close_sec_with_kind_hits_exact_row(tmp_path: Path) -> None:
    # 同檔資+集保並存:帶 kind 精確鍵到融資列 → 送融資賣(送現股賣會變成賣掉集保部位)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(_sec_positions_two_kinds())
    req = PositionCloseRequest(market="sec", key="2330", price=590.0, kind="margin")
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    fields = _sent_fields(com.sent[0])
    assert fields["sBuySell"] == 1 and fields["sFlag"] == 1  # 融資多 → 融資賣
    assert fields["nQty"] == 3  # 融資列的張數,不是集保列的 1
    # §7 可重建性(review A-5)。審計兩條路各釘一次:
    # 成功路徑記的是實際送出的委託(close 請求已轉成 StockOrderRequest)→ 種類看 trade_kind
    assert _audit_lines(client)[-1]["req"]["trade_kind"] == "margin"
    with pytest.raises(CapitalGateBlockedError):  # 拒單路徑記的才是 close 請求原貌
        await client.close_position(req)
    assert _audit_lines(client)[-1]["req"]["kind"] == "margin"


async def test_close_sec_unaffected_by_same_named_fut_position(tmp_path: Path) -> None:
    """唯一匹配的掃描母體以 market 收斂(review A-2):同 stock_no 的他市場列不得
    讓本市場的唯一列被誤判成歧義。母體不對齊時失效樣態還會自相矛盾 —— position_for
    看到兩列回 None,而 _sec_no_position_reason 只數 sec 列(1 列)→ 擋單理由變成
    誤導的「無部位可平」(實際上部位就在那裡)。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(
        [
            Position(market="sec", stock_no="2330", qty=2, kind="margin"),
            Position(market="fut", stock_no="2330", qty=1, avg_price=590.0),
        ]
    )
    req = PositionCloseRequest(market="sec", key="2330", price=590.0)  # 舊 body:不帶 kind
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    fields = _sent_fields(com.sent[0])
    assert com.sent[0][0] == "stock" and fields["sFlag"] == 1  # 鍵到 sec 融資列


async def test_close_sec_without_kind_blocks_ambiguous_but_allows_unique(tmp_path: Path) -> None:
    # 舊 body(不帶 kind):多列 = 歧義,fail-safe 阻擋不猜;唯一列則照舊成功(backward compat)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(_sec_positions_two_kinds())
    req = PositionCloseRequest(market="sec", key="2330", price=590.0)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.close_position(req)
    assert ei.value.reason is not None and "請指定種類" in ei.value.reason
    assert com.sent == []
    assert "請指定種類" in _audit_lines(client)[-1]["blocked"]

    client.store.set_positions([Position(market="sec", stock_no="2330", qty=1, kind="cash")])
    res = await _drive(client, lambda: client.close_position(req))
    assert res.ok is True
    assert _sent_fields(com.sent[0])["sFlag"] == 0  # 現股賣


async def test_close_inflight_separates_kinds_but_locks_same_kind(tmp_path: Path) -> None:
    # P0-1 兩面:同檔兩種類的 in-flight 互不阻擋;同一種類第二次仍被 10s「在途」擋
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(_sec_positions_two_kinds())
    cash = PositionCloseRequest(market="sec", key="2330", price=590.0, kind="cash")
    margin = PositionCloseRequest(market="sec", key="2330", price=590.0, kind="margin")
    assert (await _drive(client, lambda: client.close_position(cash))).ok is True
    assert (await _drive(client, lambda: client.close_position(margin))).ok is True
    assert len(com.sent) == 2  # 種類不同 = 兩筆各自的平倉,不互擋
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.close_position(cash)
    assert ei.value.reason is not None and "在途" in ei.value.reason
    assert len(com.sent) == 2
    assert sorted(client._close_inflight) == ["2330:cash", "2330:margin"]


def test_balance_chain_keeps_both_kinds_of_same_stock(tmp_path: Path) -> None:
    # 全鏈:balance 兩列都留(不再 dedupe)→ profit 各自回填 → finalize 兩列並存
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    client._handle_balance(
        "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    )
    client._handle_balance("3357,T,0,0,0,0,2000,0,0,0,0,2000,0,0,2000,0,0,A123456789,1234567890")
    client._handle_balance("##")
    profit_margin = (
        "臺慶科,3357,新台幣,融資,3000,156.00,0.27,468000,464000,12345,150.55,451650,"
        "0,0,665,0,1404,135495,316155,89,,2.73,0,,Y"
    )
    client._handle_profit("000,查詢成功")
    client._handle_profit(profit_margin)
    client._handle_profit(profit_margin.replace(",融資,", ",現股,").replace(",150.55,", ",140.25,"))
    client._handle_profit("##,,,,")
    assert len(client.store.positions()) == 2
    m = client.store.position_for("3357", "margin")
    c = client.store.position_for("3357", "cash")
    assert m is not None and m.qty == 3 and m.avg_price == 150.55
    assert c is not None and c.qty == 2 and c.avg_price == 140.25  # 各拿自己種類的均價


def test_profit_row_for_dropped_stock_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """P1-3 兩段判別:balance 側丟掉的股號(零股不足 1 張)在損益報告仍有列 →
    靜默(否則每 60s 洗版 warning);真正的種類不符才 warning。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    with caplog.at_level("WARNING"):
        client._handle_balance(
            "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
        )
        client._handle_balance(  # 2330 只有 500 股(零股不足 1 張)→ balance 側丟掉
            "2330,T,0,0,0,0,500,0,0,0,0,500,0,0,500,0,0,A123456789,1234567890"
        )
        client._handle_balance("##")
        client._handle_profit(
            "台積電,2330,新台幣,現股,500,1000.00,0.27,468000,464000,12345,980.00,451650,"
            "0,0,665,0,1404,135495,316155,89,,2.73,0,,Y"
        )
        client._handle_profit("##,,,,")
    assert not [r for r in caplog.records if "種類不符" in r.message]
    assert client.store.position_for("3357", "margin") is not None  # 本輪照常發布

    caplog.clear()
    other = _client(FakeCom(), tmp_path / "b")  # 每輪查詢會 reset collector,對照用新 client
    _mark_ready(other, futures_account=None)
    with caplog.at_level("WARNING"):  # 對照:股號在但種類對不上 → 照樣 warning
        other._handle_balance(
            "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
        )
        other._handle_balance("##")
        other._handle_profit(
            "臺慶科,3357,新台幣,現股,3000,156.00,0.27,468000,464000,12345,150.55,451650,"
            "0,0,665,0,1404,135495,316155,89,,2.73,0,,Y"
        )
        other._handle_profit("##,,,,")
    assert any("種類不符" in r.message for r in caplog.records)
    p = other.store.position_for("3357", "margin")
    assert p is not None and p.avg_price is None  # 種類不符不回填


async def test_close_fut_no_position_blocked(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.close_position(PositionCloseRequest(market="fut", key="TXFI6", price=22000.0))
    assert ei.value.reason is not None and "無部位可平" in ei.value.reason


async def test_close_fut_without_futures_account_blocked(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    client.store.set_positions(
        [Position(market="fut", stock_no="TXFI6", qty=1, avg_price=23000.0)]
    )
    with pytest.raises(CapitalGateBlockedError) as ei:
        await client.close_position(PositionCloseRequest(market="fut", key="TXFI6", price=22000.0))
    assert ei.value.reason == "no_futures_account"
    assert com.sent == []


# ---------------------------------------------------------------------------
# 回報 → store → broadcast;balance 觸發(SC-5/6 的 client 面)
# ---------------------------------------------------------------------------


def test_reply_updates_store_marks_dirty_and_broadcasts(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    pushed: list[dict[str, object]] = []
    client.set_broadcast(pushed.append)
    client._handle_reply(_stock_evt_raw("S1"))
    orders = client.store.orders()
    assert len(orders) == 1 and orders[0].seq_no == "S1"
    assert pushed and pushed[0]["event"] == "capital_order"
    assert client._balance_due is None  # N 委託不觸發重查
    fill = [""] * 48
    fill[0], fill[1], fill[2], fill[3] = "S1", "TS", "D", "N"
    fill[6], fill[8], fill[11], fill[20] = "B00R2", "3357", "90.0000", "1000"
    client._handle_reply(",".join(fill))
    assert client._balance_due is not None  # 成交 → debounce 排程重查


def test_balance_chain_merges_sec_and_fut_positions(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    pushed: list[dict[str, object]] = []
    client.set_broadcast(pushed.append)
    bal = "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    client._handle_balance(bal)
    client._handle_balance("##")
    assert ("get_profit_loss_gw", "1234567890A") in com.sent
    assert client.store.positions() == []  # 期貨回完才合併寫入,不先落半套
    client._handle_profit("000,查詢成功")
    client._handle_profit(
        "臺慶科,3357,新台幣,融資,3000,156.00,0.27,468000,464000,12345,150.55,451650,"
        "0,0,665,0,1404,135495,316155,89,,2.73,0,,Y"
    )
    client._handle_profit("##,,,,")
    assert ("get_open_interest", "F9999999") in com.sent
    assert client.store.positions() == []
    client._handle_open_interest("TF,F9999999,TXFI6,B,2,0,23000.0")
    client._handle_open_interest("##")
    sec = client.store.position_for("3357")
    fut = client.store.position_for("TXFI6")
    assert sec is not None and sec.qty == 3 and sec.kind == "margin"
    assert sec.avg_price == 150.55  # 損益回填進 pending 再合併發布
    assert fut is not None and fut.market == "fut" and fut.qty == 2 and fut.avg_price == 23000.0
    assert any(p["event"] == "capital_position" for p in pushed)


def test_oi_same_contract_rows_netted(tmp_path: Path) -> None:
    # review A5:OI 同契約 B/S 兩列 → 淨額合併,不可兩列同 key 互蓋
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._handle_balance("##")
    client._handle_profit("##,,,,")
    client._handle_open_interest("TF,F9999999,TXFI6,B,3,0,23000.0")
    client._handle_open_interest("TF,F9999999,TXFI6,S,1,0,23100.0")
    client._handle_open_interest("##")
    fut = client.store.position_for("TXFI6")
    assert fut is not None and fut.qty == 2  # B3 + S(-1) 淨額


def test_oi_failure_keeps_previous_fut_positions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # review A7:OI 查詢 rc≠0 → 沿用上一輪 fut 部位,不可清空(閃斷把面板期貨部位歸零)
    class OiFailCom(FakeCom):
        def get_open_interest(self, user_id: str, futures_account: str) -> int:
            self.sent.append(("get_open_interest", futures_account))
            return 1

    com = OiFailCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(
        [Position(market="fut", stock_no="TXFI6", qty=2, avg_price=23000.0)]
    )
    bal = "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    with caplog.at_level("WARNING"):
        client._handle_balance(bal)
        client._handle_balance("##")
        client._handle_profit("##,,,,")
    fut = client.store.position_for("TXFI6")
    assert fut is not None and fut.qty == 2  # 舊 fut 沿用
    sec = client.store.position_for("3357")
    assert sec is not None and sec.qty == 3  # 新證券段照常發布
    assert any("沿用" in r.message for r in caplog.records)


def test_oi_pending_timeout_keeps_previous_fut_positions(tmp_path: Path) -> None:
    # review A7:pending watchdog 逾時同樣沿用舊 fut 部位
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client.store.set_positions(
        [Position(market="fut", stock_no="TXFI6", qty=1, avg_price=23000.0)]
    )
    bal = "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    client._handle_balance(bal)
    client._handle_balance("##")
    client._pending_deadline = 0.0  # 損益/OI 卡死 → 強制逾時
    client._pump_once()
    fut = client.store.position_for("TXFI6")
    assert fut is not None and fut.qty == 1


def test_balance_chain_without_futures_account_publishes_sec_only(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    bal = "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    client._handle_balance(bal)
    client._handle_balance("##")
    client._handle_profit("##,,,,")
    assert all(entry[0] != "get_open_interest" for entry in com.sent)
    sec = client.store.position_for("3357")
    assert sec is not None and sec.qty == 3


def test_pending_watchdog_publishes_sec_when_chain_stalls(tmp_path: Path) -> None:
    # 損益/期貨查詢卡住(零事件)時 pending 不可永久滯留 — 逾時以已收資料寫入
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    bal = "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    client._handle_balance(bal)
    client._handle_balance("##")
    assert client.store.positions() == []
    client._pending_deadline = 0.0  # 強制逾時
    client._pump_once()
    sec = client.store.position_for("3357")
    assert sec is not None and sec.qty == 3


def test_consecutive_fills_merge_into_single_requery(tmp_path: Path) -> None:
    """連續成交合併(既有語意):後到的成交推遲 due(重設),幫浦圈只在尾端查一次。
    改成「只有第一筆設 due」= 尾端成交等不到重查,庫存停在中途數字。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._handle_reply(_fill_evt_raw())
    first = client._balance_due
    client._handle_reply(_fill_evt_raw(qty="2000"))
    second = client._balance_due
    assert first is not None and second is not None
    assert second > first


def test_fill_schedules_balance_requery_within_half_second(tmp_path: Path) -> None:
    """SC-5:成交後庫存重查排在 0.5s 後(上界防拖慢、下界防 debounce 被整個拿掉)。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._handle_reply(_fill_evt_raw())
    assert client._balance_due is not None
    delay = client._balance_due - time.monotonic()
    assert 0.45 <= delay <= 0.55


def test_balance_query_guarded_while_chain_in_flight(tmp_path: Path) -> None:
    """SC-7(a):鏈進行中(balance 段)第二筆成交不得再發 GetRealBalance —
    群益 1019 + _pending_sec 被覆寫會整輪丟失部位;due 不清,留給鏈結束後補查。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._balance_due = time.monotonic() - 1.0
    client._maybe_query_balance()
    assert _balance_queries(com) == 1
    client._balance_due = time.monotonic() - 1.0  # 鏈進行中再成交(未餵 ## → 仍在 balance 段)
    client._maybe_query_balance()
    assert _balance_queries(com) == 1
    assert client._balance_due is not None  # 補查的前提:守門不得吃掉 due


def test_balance_query_guarded_while_pending_even_if_inflight_expired(tmp_path: Path) -> None:
    """SC-7(b):balance 段收完換 pending 段(profit/OI 未回)後,
    守門改由 _pending_sec 判(_poll_pending 8s 保底),inflight deadline 逾期也不放行。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._balance_due = time.monotonic() - 1.0
    client._maybe_query_balance()
    client._handle_balance(
        "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    )
    client._handle_balance("##")
    assert client._pending_sec is not None  # profit 尚未回,鏈掛在 pending 段
    client._balance_due = time.monotonic() - 1.0
    client._balance_inflight_until = time.monotonic() - 1.0
    client._maybe_query_balance()
    assert _balance_queries(com) == 1
    # T7:pending 段擋下同樣不得吃掉 due —— 吃掉的話鏈結束後沒人補查,該筆成交漏
    assert client._balance_due is not None


def test_balance_complete_hands_guard_over_to_pending(tmp_path: Path) -> None:
    """T8(A1 交棒白箱鎖):balance 段收齊 → `_pending_sec` 接手守門、
    `_balance_inflight_until` 同時清掉。漏清 inflight 不會馬上出錯(pending 判在前),
    但 pending 逾時 finalize 後殘留的舊 deadline 會再擋一次重查;漏設 pending 則
    balance 段 10s deadline 一過就放行第二次查詢(A1 要擋的正是這個)。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._balance_due = time.monotonic() - 1.0
    client._maybe_query_balance()
    assert client._balance_inflight_until is not None  # balance 段守門已武裝
    client._handle_balance(
        "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
    )
    client._handle_balance("##")
    assert client._pending_sec is not None
    assert client._balance_inflight_until is None


def test_balance_requeried_after_chain_completes(tmp_path: Path) -> None:
    """SC-7(c):鏈走完(無期貨帳號路徑)→ 下一輪幫浦圈補查,成交不漏。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client, futures_account=None)
    client._balance_due = time.monotonic() - 1.0
    client._maybe_query_balance()
    client._balance_due = time.monotonic() - 1.0  # 鏈進行中的第二筆成交
    client._maybe_query_balance()
    assert _balance_queries(com) == 1
    client._handle_balance("##")
    client._handle_profit("##,,,,")  # → _query_open_interest → 無期貨帳號 → finalize
    assert client._pending_sec is None
    client._maybe_query_balance()
    assert _balance_queries(com) == 2


def test_balance_inflight_guard_expires_when_chain_never_starts(tmp_path: Path) -> None:
    """SC-7(d):零事件死查詢(collector poll 在 _last_feed is None 早退,永不 flush)—
    deadline 逾期是唯一解卡通道,否則庫存永久停更。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._balance_due = time.monotonic() - 1.0
    client._maybe_query_balance()
    assert _balance_queries(com) == 1
    client._balance_due = time.monotonic() - 1.0
    client._balance_inflight_until = time.monotonic() - 1.0
    client._maybe_query_balance()
    assert _balance_queries(com) == 2


def test_balance_query_rc_failure_rearms_due_with_backoff(tmp_path: Path) -> None:
    """C1/T9:GetRealBalance rc≠0(1019「查詢處理中」)= 鏈根本沒啟動 →
    (a) 守門旗標必須清掉,不可佔著擋下一輪;
    (b) `_balance_due` 必須重新武裝 —— 發查詢前已把 due 清成 None,rc≠0 就這樣走掉
    等於整筆成交的庫存重查被吃掉,要等 60s stale 輪詢才補得回來(守門的
    「成交不漏」不變量破功)。退避 1s 而非還原舊 due:舊 due 已過期,下一圈幫浦
    (50ms)會立刻再打 1019 成緊迴圈。"""
    com = FakeCom()
    com.balance_rc = 1019
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._handle_reply(_fill_evt_raw())  # D 回報 → due 排程
    client._balance_due = time.monotonic() - 1.0  # due 到期(不 sleep;A8)
    client._maybe_query_balance()
    assert _balance_queries(com) == 1
    assert client._balance_inflight_until is None
    assert client._balance_due is not None
    delay = client._balance_due - time.monotonic()
    assert 0.9 <= delay <= 1.1


def test_maybe_query_balance_runs_in_degraded(tmp_path: Path) -> None:
    # degraded(回報斷線)也要輪詢 — 此時 60s 輪詢是部位唯一更新源
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._status = "degraded"
    client._balance_last_ts = 0.0
    client._maybe_query_balance()
    assert ("get_real_balance", "1234567890A") in com.sent


def test_reply_disconnect_degrades_and_keeps_store(tmp_path: Path) -> None:
    com = RecordingCom()
    client = _client(com, tmp_path)
    assert client._init_com() is True
    client.store.apply_reply(parse_onnewdata(_stock_evt_raw("S1")))
    client._handle_reply_disconnect(3002)
    assert client.status == "degraded"
    assert client.last_error is not None and "3002" in client.last_error
    assert len(client.store.orders()) == 1  # 不 clear store、不自動重連(review R7)


async def test_degraded_still_allows_writes(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._status = "degraded"
    res = await _drive(
        client, lambda: client.cancel_order(CancelOrderRequest(seq_no="S1", market="sec"))
    )
    assert res.ok is True  # 刪單是降風險操作,degraded 不擋


# ---------------------------------------------------------------------------
# 審計檔名 prefix(SC-9:群益走 capital-*.jsonl,與 TC4 trade 的 orders-* 分檔)
# ---------------------------------------------------------------------------


async def test_audit_files_use_capital_prefix(tmp_path: Path) -> None:
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    await _drive(client, lambda: client.submit_stock_order(_stock_req()))
    files = sorted(client._audit_base.glob("*.jsonl"))
    assert files, "審計檔未落地"
    assert all(f.name.startswith("capital-") for f in files)


# ---------------------------------------------------------------------------
# 本 app 送出的市價單記憶(SC-10):回報無價格別欄 → 送單成功時把 price_type 記進 store
# ---------------------------------------------------------------------------


_FIXED_YMD = "20260610"


def _freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 client 的日界釘死(review r1 IMPL-5):測試自己算 `time.strftime` 的話,
    等於拿被測程式的實作去驗它自己 —— 日界口徑改掉也照樣綠。"""
    monkeypatch.setattr(client_mod, "_today_ymd", lambda: _FIXED_YMD)


def _dated(raw: str, date: str = _FIXED_YMD) -> str:
    """把委託建立日(idx23)塞進回報字串;store 只在日期相符時帶出 price_type。"""
    arr = raw.split(",")
    arr[23] = date
    return ",".join(arr)


async def test_submit_notes_price_type_into_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """證券 + 期貨兩條送單路徑成功後,對應 seq 的委託列都帶得出 price_type。"""
    _freeze_today(monkeypatch)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    sec = await _drive(
        client,
        lambda: client.submit_stock_order(
            StockOrderRequest(
                stock_no="2330", buy_sell="buy", price=590.0, qty=2, price_type="market"
            )
        ),
    )
    fut = await _drive(
        client,
        lambda: client.submit_future_order(
            _fut_req(price_type="limit", time_in_force="IOC"), contract="TXFI6", multiplier=200
        ),
    )
    assert sec.seq_no == "SEQ0001" and fut.seq_no == "SEQF001"
    client.store.apply_reply(parse_onnewdata(_dated(_stock_evt_raw("SEQ0001"))))
    client.store.apply_reply(parse_onnewdata(_dated(_fut_evt_raw("SEQF001"))))
    by_seq = {o.seq_no: o for o in client.store.orders()}
    assert by_seq["SEQ0001"].price_type == "market"
    assert by_seq["SEQF001"].price_type == "limit"


async def test_broker_reject_does_not_note_price_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """群益拒單(code≠0)→ 沒有委託在市場上,不得留下「市價」標籤(E6)。"""
    _freeze_today(monkeypatch)
    com = RejectingCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    with pytest.raises(BrokerRejectedError):
        await _drive(
            client,
            lambda: client.submit_stock_order(
                StockOrderRequest(
                    stock_no="2330", buy_sell="buy", price=590.0, qty=2, price_type="market"
                )
            ),
        )
    client.store.apply_reply(parse_onnewdata(_dated(_stock_evt_raw("SEQ0001"))))
    assert client.store.orders()[0].price_type is None


async def test_late_result_notes_price_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """timeout 當下「結果未知」不記,COM 晚回帶 seq → 補記(review r1 IMPL-4)。
    不補的話,一次 timeout 就讓這張市價單在委託列表**永久**失標。"""
    _freeze_today(monkeypatch)
    monkeypatch.setattr(client_mod, "_WRITE_TIMEOUT_S", 0.01)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    client._loop = asyncio.get_running_loop()
    # 不 drain 佇列 = COM 卡死 → 結果未知
    res = await client.submit_stock_order(
        StockOrderRequest(stock_no="2330", buy_sell="buy", price=590.0, qty=2, price_type="market")
    )
    assert res.ok is False and res.seq_no is None
    client.store.apply_reply(parse_onnewdata(_dated(_stock_evt_raw("SEQ0001"))))
    assert client.store.orders()[0].price_type is None  # 結果未知的當下不記
    cmd = client._cmd_q.get_nowait()
    assert cmd is not None
    fn, fut = cmd
    fut.set_result(fn())  # COM 晚回(執行緒側 _settle 等價)
    await asyncio.sleep(0)  # 消化 done_callback
    assert client.store.orders()[0].price_type == "market"


async def test_correct_price_forgets_price_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """改價成功 → 這張單現在是限價單,「市價」標籤必須消失(review r1 IMPL-6):
    留著就是委託列表上唯一一條會**誤標**的路徑。"""
    _freeze_today(monkeypatch)
    com = FakeCom()
    client = _client(com, tmp_path)
    _mark_ready(client)
    await _drive(
        client,
        lambda: client.submit_stock_order(
            StockOrderRequest(
                stock_no="2330", buy_sell="buy", price=590.0, qty=2, price_type="market"
            )
        ),
    )
    client.store.apply_reply(parse_onnewdata(_dated(_stock_evt_raw("SEQ0001"))))
    assert client.store.orders()[0].price_type == "market"
    await _drive(
        client,
        lambda: client.correct_price(
            CorrectPriceRequest(seq_no="SEQ0001", market="sec", price=580.0)
        ),
    )
    assert client.store.orders()[0].price_type is None
