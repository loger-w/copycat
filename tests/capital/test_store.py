"""聚合:key=13碼委託序號;同標的不同單絕不合併,合併的只有同一張單的事件(SC-5/6)。
treading-king test_capital_store.py 照搬改寫(pydantic model_copy → dataclasses.replace、
Position 建構補 market 欄)。"""

from __future__ import annotations

import dataclasses

import pytest

from copycat.capital.reply import ReplyRecord, parse_onnewdata
from copycat.capital.store import CapitalStore

SEQ_A = "2313091378319"
SEQ_B = "2313092917885"


def _evt(
    seq: str = SEQ_A,
    market: str = "TS",
    typ: str = "N",
    err: str = "N",
    bs: str = "B00R2",
    stock: str = "4989",
    price: str = "83.7000",
    qty: str = "1000",
    after: str = "",
    time: str = "10:05:22",
    pre: str = "A",
    date: str = "20260610",
) -> ReplyRecord:
    arr = [""] * 47
    arr[0], arr[1], arr[2], arr[3] = seq, market, typ, err
    arr[4], arr[5], arr[6], arr[7], arr[8] = "9999", "0000000", bs, "TW", stock
    arr[10], arr[11] = "X01AA", price
    arr[20], arr[22] = qty, after
    arr[23], arr[24] = date, time
    arr[31] = pre
    return parse_onnewdata(",".join(arr))


def test_order_then_partial_then_full_fill_aggregates() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))  # 委託 4 張
    s.apply_reply(_evt(typ="D", qty="1000", price="83.5000"))  # 成交 1
    o = s.orders()[0]
    assert o.status_label == "部分成交"
    assert o.order_qty == 4 and o.filled_qty == 1 and o.unit == "張"
    s.apply_reply(_evt(typ="D", qty="2000", price="83.7000"))
    s.apply_reply(_evt(typ="D", qty="1000", price="83.7000"))
    o = s.orders()[0]
    assert o.status_label == "全部成交"
    assert o.filled_qty == 4
    # 量加權均價 (83.5*1000 + 83.7*2000 + 83.7*1000) / 4000
    assert o.avg_fill_price is not None
    assert abs(o.avg_fill_price - 83.65) < 1e-9


def test_same_stock_different_seq_not_merged() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(seq=SEQ_A, stock="3357", qty="1000"))
    s.apply_reply(_evt(seq=SEQ_B, stock="3357", qty="1000", time="14:59:48"))
    assert len(s.orders()) == 2


def test_cancel_keeps_filled_and_order_qty() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    s.apply_reply(_evt(typ="D", qty="1000"))
    s.apply_reply(_evt(typ="C", qty="3000"))  # C 的 qty=剩量,不覆蓋
    o = s.orders()[0]
    assert o.status_label == "已刪單"
    assert o.order_qty == 4 and o.filled_qty == 1


def test_orders_sorted_by_date_then_time() -> None:
    """昨日收盤後掛的預約單(時間 14:59)不得壓在今日早盤單(09:05)上面。"""
    s = CapitalStore()
    s.apply_reply(_evt(seq=SEQ_A, date="20260610", time="14:59:48", pre="B"))
    s.apply_reply(_evt(seq=SEQ_B, date="20260611", time="09:05:01"))
    assert [o.seq_no for o in s.orders()] == [SEQ_B, SEQ_A]
    assert s.orders()[1].date == "20260610"


def test_preorder_status_and_flag() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", pre="B"))
    o = s.orders()[0]
    assert o.status_label == "預約中"
    assert o.pre_order is True


def test_replay_out_of_order_does_not_downgrade() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="D", qty="1000", price="83.7000"))  # 先到 D(亂序)
    s.apply_reply(_evt(typ="N", qty="1000"))  # 晚到 N 不得降級
    o = s.orders()[0]
    assert o.status_label == "全部成交"


def test_modify_qty_and_price() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000", price="83.0000"))
    s.apply_reply(_evt(typ="U", qty="1000", after="3000"))  # 改量:after 優先
    s.apply_reply(_evt(typ="P", price="84.0000"))  # 改價
    o = s.orders()[0]
    assert o.order_qty == 3
    assert o.price == 84.0


def test_order_err_marks_failed() -> None:
    s = CapitalStore()
    e = dataclasses.replace(_evt(typ="N"), order_err="Y", error_msg="超過漲跌停")
    s.apply_reply(e)
    o = s.orders()[0]
    assert o.status_label == "失敗"
    assert o.error_msg == "超過漲跌停"


def test_action_failure_does_not_kill_live_order() -> None:
    # C/P/U/B + OrderErr 是「動作被拒」(如撮合中拒刪、改價超過漲跌停),原單仍掛在市場;
    # 標整張單失敗會讓活單從面板消失(刪/改鈕不見),user 跟丟真錢委託。
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    e = dataclasses.replace(_evt(typ="C", qty="4000"), order_err="Y", error_msg="刪單失敗")
    s.apply_reply(e)
    o = s.orders()[0]
    assert o.status_label == "委託成功"  # 單還活著
    assert o.actionable is True  # 可以再刪一次
    assert o.error_msg == "刪單失敗"  # 動作失敗的原因要看得到
    # 之後真的成交,照常累計
    s.apply_reply(_evt(typ="D", qty="1000"))
    o = s.orders()[0]
    assert o.status_label == "部分成交" and o.filled_qty == 1


def test_partial_fill_before_order_event_stays_actionable() -> None:
    # 亂序重播:部分成交的 D 先到、N 晚到。order_qty 未知時不得斷言「全部成交」,
    # 否則 _RANK 終態鎖死,還有 3 張掛在市場的活單會從面板上不可刪改。
    s = CapitalStore()
    s.apply_reply(_evt(typ="D", qty="1000", price="83.5000"))  # D 先到(只是部分)
    assert s.orders()[0].status_label == "部分成交"
    s.apply_reply(_evt(typ="N", qty="4000"))  # N 晚到補量
    o = s.orders()[0]
    assert o.status_label == "部分成交"
    assert o.actionable is True
    assert o.order_qty == 4 and o.filled_qty == 1
    s.apply_reply(_evt(typ="D", qty="3000", price="83.5000"))  # 補滿才升全部成交
    assert s.orders()[0].status_label == "全部成交"


def test_d_without_price_first_event_does_not_latch_terminal() -> None:
    # 不採計的成交(無價)不可在 order_qty 未知時把單鎖成「全部成交」終態
    s = CapitalStore()
    s.apply_reply(_evt(typ="D", qty="1000", price=""))
    assert s.orders()[0].status_label is None
    s.apply_reply(_evt(typ="N", qty="4000"))
    o = s.orders()[0]
    assert o.status_label == "委託成功" and o.actionable is True


def test_futures_unit_and_no_division() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(market="TF", bs="BNR20", stock="QEF06", qty="1", price="873.0000"))
    o = s.orders()[0]
    assert o.unit == "口" and o.order_qty == 1 and o.market == "TF"


def test_option_market_unit_and_no_division() -> None:
    # 期權四市場(TF/TO/OF/OO)都是口、不除 1000
    for market in ("TO", "OF", "OO"):
        s = CapitalStore()
        s.apply_reply(_evt(market=market, bs="SYR20", stock="TXO20000I6", qty="2", price="120.0"))
        o = s.orders()[0]
        assert o.unit == "口" and o.order_qty == 2 and o.market == market


def test_odd_lot_market_unit_is_share_without_division() -> None:
    # 零股(TL/TC)= 股、不除 1000。unit 字面值自閃電梯掛單顯示起是前端過濾鍵
    # (現股梯排除零股單),標成「張」會讓零股單漏進張梯 → 量級錯千倍。
    for market in ("TL", "TC"):
        s = CapitalStore()
        s.apply_reply(_evt(market=market, stock="2330", qty="500", price="1000.0000"))
        o = s.orders()[0]
        assert o.unit == "股" and o.order_qty == 500 and o.market == market


def test_no_seq_dropped() -> None:
    s = CapitalStore()
    e = dataclasses.replace(_evt(), seq_no=None)
    s.apply_reply(e)
    assert s.orders() == []


def test_remaining_shares() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    s.apply_reply(_evt(typ="D", qty="1000"))
    assert s.remaining_shares(SEQ_A) == 3000
    assert s.remaining_shares("nope") is None


def test_remaining_shares_zero_for_terminal_order() -> None:
    # 已刪單 order-filled 差額不是「未成交量」:不歸零的話,死單改價會過金額閘、留給券商兜底
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    s.apply_reply(_evt(typ="D", qty="1000"))
    s.apply_reply(_evt(typ="C", qty="3000"))
    assert s.remaining_shares(SEQ_A) == 0


def test_market_of() -> None:
    s = CapitalStore()
    s.apply_reply(_evt(typ="N"))
    assert s.market_of(SEQ_A) == "TS"
    assert s.market_of("nope") is None


def test_orders_sorted_by_last_event_time() -> None:
    # spec:每筆事件更新 last_time、列表照 last_time 倒序 — 有新回報的單要浮頂,
    # 盤中確認刪改/成交結果不用往下捲找
    s = CapitalStore()
    s.apply_reply(_evt(seq=SEQ_A, typ="N", time="09:00:00"))
    s.apply_reply(_evt(seq=SEQ_B, typ="N", time="09:01:00"))
    assert [o.seq_no for o in s.orders()] == [SEQ_B, SEQ_A]
    s.apply_reply(_evt(seq=SEQ_A, typ="D", qty="1000", time="09:02:00"))  # A 有新事件 → 浮頂
    assert [o.seq_no for o in s.orders()] == [SEQ_A, SEQ_B]


def test_actionable_only_for_live_orders() -> None:
    # actionable 由後端 _RANK 單一決定(前端不再自己抄狀態表):tier 1/2 活單 true、終態/未知 false
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    assert s.orders()[0].actionable is True
    s.apply_reply(_evt(typ="D", qty="1000"))
    assert s.orders()[0].actionable is True  # 部分成交仍可刪改
    s.apply_reply(_evt(typ="C", qty="3000"))
    assert s.orders()[0].actionable is False  # 已刪單
    s2 = CapitalStore()
    s2.apply_reply(_evt(typ="X"))  # 未知事件型別,狀態 None
    assert s2.orders()[0].actionable is False


def test_d_without_price_not_counted() -> None:
    # 成交無價整筆不採計(量與均價分子綁定)→ 均價不被稀釋、remaining 高估=金額閘更嚴(安全方向)
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    s.apply_reply(_evt(typ="D", qty="1000", price="100.0000"))
    s.apply_reply(_evt(typ="D", qty="1000", price=""))  # 無價
    o = s.orders()[0]
    assert o.filled_qty == 1
    assert o.avg_fill_price is not None
    assert abs(o.avg_fill_price - 100.0) < 1e-9
    assert s.remaining_shares(SEQ_A) == 3000


def test_d_with_order_err_not_counted() -> None:
    # D 帶 err 不採計量、標失敗:少算成交=閘更嚴,維持保守方向
    s = CapitalStore()
    s.apply_reply(_evt(typ="N", qty="4000"))
    e = dataclasses.replace(_evt(typ="D", qty="1000"), order_err="Y", error_msg="異常")
    s.apply_reply(e)
    o = s.orders()[0]
    assert o.filled_qty == 0
    assert o.status_label == "失敗"


def test_clear_resets_orders_keeps_positions() -> None:
    from copycat.capital.models import Position

    s = CapitalStore()
    s.apply_reply(_evt(typ="N"))
    s.set_positions([Position(market="sec", stock_no="2330", qty=1, avg_price=500.0)])
    s.clear()
    assert s.orders() == []
    assert len(s.positions()) == 1


def test_set_positions_replaces_not_merges() -> None:
    # 整批「取代」:已出清的部位不可殘留,否則面板損益顯示錯
    from copycat.capital.models import Position

    s = CapitalStore()
    s.set_positions([Position(market="sec", stock_no="2330", qty=5, avg_price=575.0)])
    s.set_positions([Position(market="sec", stock_no="2317", qty=1, avg_price=100.0)])
    assert [p.stock_no for p in s.positions()] == ["2317"]


def test_apply_profit_rows_fills_existing_only() -> None:
    """複合鍵回填:同 (股號, 種類) 才落地;kind=None(未知標籤)整列略過,不可覆蓋已知均價。"""
    from copycat.capital.balance import ProfitRow
    from copycat.capital.models import Position

    s = CapitalStore()
    s.set_positions([Position(market="sec", stock_no="3357", qty=3, kind="margin")])
    s.apply_profit_rows(
        [
            ProfitRow("3357", 311.75, -74636.0, 288.0, 935000.0, kind="margin"),
            # 未知標籤:寧缺均價也不可套錯成本基礎 → 整列略過(不得蓋掉上一列的融資均價)
            ProfitRow("3357", 999.0, 1.0, 2.0, 3.0, kind=None),
            ProfitRow("9999", 1.0, None, None, None, kind="cash"),  # 查無股號忽略
        ]
    )
    p = s.position_for("3357", "margin")
    assert p is not None
    assert p.avg_price == 311.75
    assert p.pnl_base == -74636.0
    assert p.pnl_base_price == 288.0
    assert p.pnl_cost == 935000.0
    assert len(s.positions()) == 1


def test_set_positions_carries_profit_by_composite_key() -> None:
    """損益查詢回來前,新一輪庫存覆寫不可閃掉已知均價/損益基底;
    鍵含 kind → 同種類天然沿用、異種類是「另一列」(成本基礎不混用)。"""
    from copycat.capital.balance import ProfitRow
    from copycat.capital.models import Position

    s = CapitalStore()
    s.set_positions([Position(market="sec", stock_no="3357", qty=3, kind="margin")])
    s.apply_profit_rows([ProfitRow("3357", 311.75, -74636.0, 288.0, 935000.0, kind="margin")])
    s.set_positions(
        [
            Position(market="sec", stock_no="3357", qty=4, kind="margin"),
            Position(market="sec", stock_no="3357", qty=1, kind="cash"),
        ]
    )
    assert len(s.positions()) == 2  # 同檔資+集保並存各佔一列
    m = s.position_for("3357", "margin")
    assert m is not None and m.qty == 4
    assert m.avg_price == 311.75
    assert m.pnl_base == -74636.0 and m.pnl_base_price == 288.0 and m.pnl_cost == 935000.0
    c = s.position_for("3357", "cash")
    assert c is not None and c.qty == 1
    assert c.avg_price is None  # 集保列是另一列,不沿用融資成本
    assert c.pnl_base is None and c.pnl_base_price is None and c.pnl_cost is None


def test_position_for_kind_exact_unique_and_ambiguous() -> None:
    """position_for 三態:kind 精確鍵到 / kind=None 唯一列 fallback / kind=None 多列回 None(不猜)。"""
    from copycat.capital.models import Position

    s = CapitalStore()
    s.set_positions(
        [
            Position(market="sec", stock_no="3357", qty=3, kind="margin"),
            Position(market="sec", stock_no="3357", qty=1, kind="cash"),
            Position(market="sec", stock_no="2330", qty=2, kind="cash"),
        ]
    )
    m = s.position_for("3357", "margin")
    assert m is not None and m.qty == 3 and m.kind == "margin"
    assert s.position_for("3357", "short") is None  # 精確查:無此種類
    assert s.position_for("3357") is None  # 多列歧義:不猜
    only = s.position_for("2330")
    assert only is not None and only.qty == 2  # 唯一列 → fallback 成立
    assert s.position_for("9999") is None


def test_position_for_market_filters_scan_scope() -> None:
    """唯一匹配的掃描母體以 market 收斂:sec 股號與期交所契約碼碰巧同字串時,
    兩邊各自仍是「唯一列」— 不靠「兩套代碼不重疊」這個隱形不變量(review A-2)。"""
    from copycat.capital.models import Position

    s = CapitalStore()
    s.set_positions(
        [
            Position(market="sec", stock_no="2330", qty=2, kind="margin"),
            Position(market="fut", stock_no="2330", qty=-1, kind="cash"),
        ]
    )
    assert s.position_for("2330") is None  # 不分 market:兩列 → 歧義
    f = s.position_for("2330", market="fut")
    assert f is not None and f.market == "fut" and f.qty == -1
    e = s.position_for("2330", market="sec")
    assert e is not None and e.market == "sec" and e.qty == 2
    # 精確鍵也受 market 約束(否則 fut 列會被當成 sec 的 cash 列鍵到)
    assert s.position_for("2330", "cash", market="sec") is None


def test_set_positions_warns_on_duplicate_composite_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """同 (股號, 種類) 重複列 = last-wins 靜默丟資料;fut 側的淨額合併有 warning 對照,
    sec 側也要留痕(review A-3)。不恢復 dedupe:重複鍵本身是上游異常訊號。"""
    from copycat.capital.models import Position

    s = CapitalStore()
    with caplog.at_level("WARNING"):
        s.set_positions(
            [
                Position(market="sec", stock_no="2330", qty=1, kind="cash"),
                Position(market="sec", stock_no="2330", qty=4, kind="cash"),
                Position(market="sec", stock_no="2330", qty=3, kind="margin"),
            ]
        )
    assert len(s.positions()) == 2  # cash 一列(後到者)+ margin 一列
    p = s.position_for("2330", "cash")
    assert p is not None and p.qty == 4
    assert any("重複" in r.message for r in caplog.records)


def test_set_positions_quiet_without_duplicate_keys(caplog: pytest.LogCaptureFixture) -> None:
    # 資+集保並存是穩定狀態(每 60s 都會走到)— 不同種類不得誤報,否則 warning 洗版
    from copycat.capital.models import Position

    s = CapitalStore()
    with caplog.at_level("WARNING"):
        s.set_positions(
            [
                Position(market="sec", stock_no="2330", qty=1, kind="cash"),
                Position(market="sec", stock_no="2330", qty=3, kind="margin"),
            ]
        )
    assert caplog.records == []


def test_fut_position_keyed_by_contract() -> None:
    # 期貨部位:stock_no=期交所契約碼、market="fut" — 同 key 全量取代語意不變
    from copycat.capital.models import Position

    s = CapitalStore()
    s.set_positions([Position(market="fut", stock_no="TXFI6", qty=-2, avg_price=23000.0)])
    p = s.position_for("TXFI6")
    assert p is not None
    assert p.market == "fut" and p.qty == -2


# ---------------------------------------------------------------------------
# 本 app 送出的市價單記憶(SC-10):回報無價格別欄 → 送單結果與回報到達序不保證
# ---------------------------------------------------------------------------


def test_price_type_noted_before_reply_arrives() -> None:
    """送單結果先回、N 回報後到(E5):dict 獨立於 _Agg,回報建立列時仍帶得出來。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260610")
    s.apply_reply(_evt(seq=SEQ_A, date="20260610"))
    assert s.orders()[0].price_type == "market"


def test_price_type_noted_after_reply_arrives() -> None:
    """N 回報先到、送單結果後回:同樣要帶得出來(兩序皆成立才是與到達序無關)。"""
    s = CapitalStore()
    s.apply_reply(_evt(seq=SEQ_A, date="20260610"))
    assert s.orders()[0].price_type is None
    s.note_price_type(SEQ_A, "market", "20260610")
    assert s.orders()[0].price_type == "market"


def test_price_type_not_applied_across_days() -> None:
    """server 長跑跨日、seq 重用(review R7):記錄日與委託日不符一律不帶 —
    今日的限價單被標成「市價」是憑空的假訊息,寧可缺標籤。日期缺(None)同樣不帶。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260610")
    s.apply_reply(_evt(seq=SEQ_A, date="20260611"))
    assert s.orders()[0].price_type is None
    # 委託日缺值 → 無從比對,不帶
    s2 = CapitalStore()
    s2.note_price_type(SEQ_B, "market", "20260610")
    s2.apply_reply(_evt(seq=SEQ_B, date=""))
    assert s2.orders()[0].date is None
    assert s2.orders()[0].price_type is None


def test_price_type_survives_clear_and_replay() -> None:
    """clear() 只清委託聚合(回報重連重播前必做);送單意圖不是回報事件,
    清掉的話重播後本 app 送的市價單全體失標。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260610")
    s.apply_reply(_evt(seq=SEQ_A, date="20260610"))
    s.clear()
    assert s.orders() == []
    s.apply_reply(_evt(seq=SEQ_A, date="20260610"))
    assert s.orders()[0].price_type == "market"
