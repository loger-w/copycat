"""聚合:key=13碼委託序號;同標的不同單絕不合併,合併的只有同一張單的事件(SC-5/6)。
treading-king test_capital_store.py 照搬改寫(pydantic model_copy → dataclasses.replace、
Position 建構補 market 欄)。"""

from __future__ import annotations

import dataclasses

import pytest

from copycat.capital.balance import parse_balance_line
from copycat.capital.close import build_close_order
from copycat.capital.models import Position, PositionCloseRequest
from copycat.capital.reply import ReplyRecord, parse_onnewdata
from copycat.capital.store import CapitalStore
from tests.capital.balance_rows import RAW_T_BORROWLESS_SHORT

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


def test_set_positions_carries_profit_by_composite_key() -> None:
    """損益查詢回來前,新一輪庫存覆寫不可閃掉已知均價/損益基底;
    鍵含 kind → 同種類天然沿用、異種類是「另一列」(成本基礎不混用)。"""
    s = CapitalStore()
    # 損益回填後的列由 client._on_profit_complete 就地寫進 pending 再 set_positions(真鏈產物長這樣)
    s.set_positions(
        [
            Position(
                market="sec",
                stock_no="3357",
                qty=3,
                kind="margin",
                avg_price=311.75,
                avg_source="broker",
                pnl_base=-74636.0,
                pnl_base_price=288.0,
                pnl_cost=935000.0,
            )
        ]
    )
    s.set_positions(
        [
            Position(market="sec", stock_no="3357", qty=4, kind="margin"),
            Position(market="sec", stock_no="3357", qty=1, kind="cash"),
        ]
    )
    assert len(s.positions()) == 2  # 同檔資+集保並存各佔一列
    m = s.position_for("3357", "margin")
    assert m is not None and m.qty == 4
    assert m.avg_price == 311.75 and m.avg_source == "broker"  # 同種類:均價與來源成對沿用
    assert m.pnl_base == -74636.0 and m.pnl_base_price == 288.0 and m.pnl_cost == 935000.0
    c = s.position_for("3357", "cash")
    assert c is not None and c.qty == 1
    assert c.avg_price is None and c.avg_source is None  # 異種類(集保列)是另一列,不沿用融資成本
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
    """server 長跑跨日、seq 重用(review R7):記錄日與回報日(idx23,每筆回報覆寫)不符
    一律不帶 — 今日的限價單被標成「市價」是憑空的假訊息,寧可缺標籤;若 idx23 隨事件變日,
    昨日建立今日成交的單也因此掉標籤,那是 fail-safe 方向。日期缺(None)同樣不帶。"""
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


def test_price_type_binding_rejects_same_seq_different_order() -> None:
    """review R6 ST1:夜盤市價單記 (0824, 0825),隔日日盤同 seq 的**另一張單**(他處下的
    限價)不得被標成市價 —— 標的或方向任一不符就不帶出;完全相符才是同一張。

    s3 同時也是 N075 **已知未封的誤標窗**(08-28 user 拍板:程式不封洞):隔日他處下的
    **同檔同方向**限價單若又撞同 seq,輸入與 s3 逐字相同,store 分不出「同一張」與
    「另一張」→ 照樣標成市價。關窗的路徑與條件見 `store.note_price_type` docstring /
    next-time 08-28;到時 s3 的語意要重看,不是加一條新案。"""
    s = CapitalStore()
    s.note_price_type(
        SEQ_A, "market", "20260824", trade_date="20260825", stock_no="2330", buy_sell="B"
    )
    s.apply_reply(_evt(seq=SEQ_A, date="20260825", stock="2317", bs="B00R2"))  # 標的不同
    assert s.orders()[0].price_type is None
    s2 = CapitalStore()
    s2.note_price_type(
        SEQ_A, "market", "20260824", trade_date="20260825", stock_no="2330", buy_sell="B"
    )
    s2.apply_reply(_evt(seq=SEQ_A, date="20260825", stock="2330", bs="S00R2"))  # 方向不同
    assert s2.orders()[0].price_type is None
    s3 = CapitalStore()
    s3.note_price_type(
        SEQ_A, "market", "20260824", trade_date="20260825", stock_no="2330", buy_sell="B"
    )
    s3.apply_reply(_evt(seq=SEQ_A, date="20260825", stock="2330", bs="B00R2"))  # 同一張
    assert s3.orders()[0].price_type == "market"


def test_price_type_binding_none_means_unbound() -> None:
    """綁定值 None(該路徑沒有可綁的值,如期貨單只綁方向)→ 該欄不參與比對,舊行為不變。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260610", buy_sell="B")  # 只綁方向
    s.apply_reply(_evt(seq=SEQ_A, date="20260610", stock="9999", bs="B00R2"))
    assert s.orders()[0].price_type == "market"


def test_note_price_type_prunes_other_days() -> None:
    """review r1 IMPL-7:_price_types 只增不減,server 長跑數週就是一路長。
    寫入時同鎖 prune 掉其他日期的項 —— 它們早已因日期不符而不會帶出。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260610")
    s.note_price_type(SEQ_B, "market", "20260611")  # 換日 → 昨日那筆該被清掉
    s.apply_reply(_evt(seq=SEQ_A, date="20260610"))
    s.apply_reply(_evt(seq=SEQ_B, date="20260611"))
    by_seq = {o.seq_no: o for o in s.orders()}
    assert by_seq[SEQ_A].price_type is None  # 已 prune(即使日期本來相符)
    assert by_seq[SEQ_B].price_type == "market"


def test_forget_price_type_drops_label() -> None:
    """review r1 IMPL-6:改價後標籤必須作廢 —— 市價單改成限價還標「市價」
    是唯一一條會誤標的路徑。查無此 seq 時 forget 是 no-op(不 raise)。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260610")
    s.apply_reply(_evt(seq=SEQ_A, date="20260610"))
    assert s.orders()[0].price_type == "market"
    s.forget_price_type(SEQ_A)
    assert s.orders()[0].price_type is None
    s.forget_price_type("NO_SUCH_SEQ")


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


# ---------------------------------------------------------------------------
# N075:夜盤跨午夜的日界 —— 記本機日 + 交易日兩個候選,任一相符即帶出
# ---------------------------------------------------------------------------


def test_price_type_matches_trade_date_for_night_session() -> None:
    """夜盤 23:50 送出的市價單:本機日是 20260824,但它屬於 20260825 那個交易日。
    群益回報的 idx23 若是**交易日**,原本的「本機日必須相等」會讓標籤整段消失
    (使用者在委託列表看到一張沒有「市價」標的市價單,零錯誤訊號)。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260824", trade_date="20260825")
    s.apply_reply(_evt(seq=SEQ_A, date="20260825"))
    assert s.orders()[0].price_type == "market"


def test_price_type_still_matches_local_day_for_night_session() -> None:
    """同一筆夜盤單,群益回報若用的是**本機日曆日**(語意未實證,兩種都要接得住)——
    加法設計的意義就在這裡:比對集合是舊行為的超集,永遠不會因為改動而失標。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260824", trade_date="20260825")
    s.apply_reply(_evt(seq=SEQ_A, date="20260824"))
    assert s.orders()[0].price_type == "market"


def test_price_type_still_rejects_unrelated_day() -> None:
    """fail-safe 方向不得變鬆:兩個候選之外的任何一天照樣不帶(seq 重用誤標路徑不重開)。
    尤其是**昨日**(20260823)—— 那正是 ±1 日窗會多接受、而交易日口徑不會的那一天。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260824", trade_date="20260825")
    s.apply_reply(_evt(seq=SEQ_A, date="20260823"))
    assert s.orders()[0].price_type is None


def test_note_price_type_prune_keeps_overlapping_candidates() -> None:
    """prune 規則同步改成「候選集合不相交才刪」:夜盤那筆(0824/0825)與隔天日盤那筆
    (0825/0825)屬同一個交易日,前者不可被順手清掉 —— 否則夜盤單在日盤第一張單送出的
    瞬間失標。"""
    s = CapitalStore()
    s.note_price_type(SEQ_A, "market", "20260824", trade_date="20260825")
    s.note_price_type(SEQ_B, "market", "20260825", trade_date="20260825")
    s.apply_reply(_evt(seq=SEQ_A, date="20260825"))
    s.apply_reply(_evt(seq=SEQ_B, date="20260825"))
    by_seq = {o.seq_no: o for o in s.orders()}
    assert by_seq[SEQ_A].price_type == "market"
    assert by_seq[SEQ_B].price_type == "market"


# ---------------------------------------------------------------------------
# 成交樂觀套用(F5):apply_reply 回傳「部位有沒有變」,規則見 CapitalStore._apply_fill_locked
# ---------------------------------------------------------------------------


def _fut_evt(seq: str, typ: str, bs: str = "BN", qty: str = "1", price: str = "873.0") -> ReplyRecord:
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TF", typ, "N"
    arr[6], arr[8], arr[11], arr[20] = bs, "QEF06", price, qty
    arr[32], arr[33] = "FIQEF", "202606"
    return parse_onnewdata(",".join(arr))


def test_fill_opens_position_immediately_with_fill_price() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    assert s.apply_reply(_evt(typ="N", qty="2000")) is False  # 委託不動部位
    assert s.apply_reply(_evt(typ="D", qty="2000", price="83.5000")) is True
    p = s.position_for("4989")
    assert p is not None and (p.market, p.qty, p.kind, p.avg_price) == ("sec", 2, "cash", 83.5)


def test_partial_fills_apply_only_whole_lot_increments() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    assert s.apply_reply(_evt(typ="D", qty="500", price="80.0000")) is False  # 半張不套
    assert s.apply_reply(_evt(typ="D", qty="500", price="82.0000")) is True  # 湊滿 1 張
    p = s.position_for("4989")
    assert p is not None and p.qty == 1 and p.avg_price == 81.0  # 這張單的成交均價
    assert s.apply_reply(_evt(typ="D", qty="1000", price="84.0000")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 2 and p.avg_price == pytest.approx(82.5)


def test_fill_adds_to_existing_position_weighted_and_clears_pnl_snapshot() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    s.set_positions(
        [
            Position(
                market="sec", stock_no="4989", qty=1, avg_price=80.0, pnl_base=100.0,
                pnl_base_price=81.0, pnl_cost=80000.0,
            )
        ]
    )
    assert s.apply_reply(_evt(typ="D", qty="1000", price="84.0000")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 2 and p.avg_price == 82.0
    assert (p.pnl_base, p.pnl_base_price, p.pnl_cost) == (None, None, None)


def test_fill_reducing_position_keeps_avg_and_zero_removes_row() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    s.set_positions([Position(market="sec", stock_no="4989", qty=2, avg_price=80.0)])
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", bs="S00R2", qty="1000", price="90.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 1 and p.avg_price == 80.0
    assert s.apply_reply(_evt(seq=SEQ_B, typ="D", bs="S00R2", qty="1000", price="91.0")) is True
    assert s.position_for("4989") is None


def test_fill_with_unknown_prior_avg_leaves_avg_none() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    s.set_positions([Position(market="sec", stock_no="4989", qty=3, avg_price=None)])
    assert s.apply_reply(_evt(typ="D", qty="1000", price="84.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 4 and p.avg_price is None


def test_short_sell_fill_is_negative_lots_under_short_kind() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    assert s.apply_reply(_evt(typ="D", bs="S04R2", qty="1000", price="84.0")) is True
    p = s.position_for("4989", "short")
    assert p is not None and p.qty == -1 and p.kind == "short"
    assert s.position_for("4989", "cash") is None


def test_unknown_or_odd_lot_fills_are_not_applied() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    assert s.apply_reply(_evt(typ="D", bs="B08R2", qty="1000")) is False  # 無券買向:無部位語意
    assert s.apply_reply(_evt(typ="D", bs="B09R2", qty="1000")) is False  # 未知資券別:不在對映表
    assert s.apply_reply(_evt(typ="D", market="TL", qty="1000")) is False  # 零股市場
    assert s.positions() == []


def test_future_fill_applies_under_exchange_contract_code() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    assert s.apply_reply(_fut_evt("F1", "N")) is False
    assert s.apply_reply(_fut_evt("F1", "D", qty="2", price="873.0")) is True
    p = s.position_for("QEFF6")
    assert p is not None and (p.market, p.qty, p.kind, p.avg_price) == ("fut", 2, "cash", 873.0)
    assert s.apply_reply(_fut_evt("F2", "D", bs="SO", qty="1", price="880.0")) is True
    p = s.position_for("QEFF6")
    assert p is not None and p.qty == 1 and p.avg_price == 873.0


def test_option_fill_is_not_applied() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = "O1", "TO", "D", "N"
    arr[6], arr[8], arr[11], arr[20] = "SY", "TXO2200006", "50.0", "1"
    arr[33] = "202606"
    assert s.apply_reply(parse_onnewdata(",".join(arr))) is False
    assert s.positions() == []


def test_broker_snapshot_overrides_optimistic_fill() -> None:
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    s.apply_reply(_evt(typ="D", qty="1000", price="84.0"))
    s.set_positions([Position(market="sec", stock_no="4989", qty=3, avg_price=None)])
    p = s.position_for("4989")
    assert p is not None and p.qty == 3 and p.avg_price == 84.0  # 均價沿用既有語意(損益回填前)


def test_partial_lot_residue_is_carried_to_next_lot() -> None:
    """1500 股 @80 → 只套 1 張、只消化 1000 股價金;再 500 股 @90 → 第 2 張 = 殘 500@80 + 500@90 = 85,
    部位均價 = 165000 / 2000 = 82.5(與整張單真實均價一致)。"""
    s = CapitalStore()
    s.set_positions([])  # 首次快照落地後才開樂觀套用(review F-02)
    assert s.apply_reply(_evt(typ="D", qty="1500", price="80.0000")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 1 and p.avg_price == 80.0
    assert s.apply_reply(_evt(typ="D", qty="500", price="90.0000")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 2 and p.avg_price == pytest.approx(82.5)


def test_fill_before_first_snapshot_is_not_applied_but_counted_after(cap: None = None) -> None:
    """開機 / 重播:快照落地前的成交只累計不套(review F-02);快照落地時把它們標成已套用,
    之後的成交才套增量 —— 昨日庫存 10 張、今日賣 3 張重播不會變成 -3 張幻影空單。"""
    s = CapitalStore()
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", bs="S00R2", qty="3000", price="80.0")) is False
    assert s.positions() == []
    s.set_positions([Position(market="sec", stock_no="4989", qty=7, avg_price=80.0)])  # 券商:10 − 3
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", bs="S00R2", qty="1000", price="81.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 6  # 只套快照之後的 1 張


def test_clear_then_replay_does_not_double_apply() -> None:
    """重連重播:clear() 關掉樂觀套用,同一批 D 重播不會把部位翻倍(review F-02)。"""
    s = CapitalStore()
    s.set_positions([])
    assert s.apply_reply(_evt(typ="D", qty="1000", price="84.0")) is True
    assert s.position_for("4989") is not None
    s.clear()
    assert s.apply_reply(_evt(typ="D", qty="1000", price="84.0")) is False
    p = s.position_for("4989")
    assert p is not None and p.qty == 1


def test_flip_position_takes_fill_avg_regardless_of_magnitude() -> None:
    """反手翻倉看號不看幅度(review F-03):+3 口 @900 賣 5 口 @800 → -2 口 @800。"""
    s = CapitalStore()
    s.set_positions([Position(market="fut", stock_no="QEFF6", qty=3, avg_price=900.0)])
    assert s.apply_reply(_fut_evt("F9", "D", bs="SO", qty="5", price="800.0")) is True
    p = s.position_for("QEFF6")
    assert p is not None and p.qty == -2 and p.avg_price == 800.0


def test_unknown_option_family_and_adjusted_codes_are_not_applied() -> None:
    """契約碼守門等值比對(review F-04):`TE122000`(未白名單選擇權)與 `EE106`(調整碼)不套。"""
    s = CapitalStore()
    s.set_positions([])
    for code, market in (("TE122000", "TO"), ("EE106", "TF")):
        arr = [""] * 48
        arr[0], arr[1], arr[2], arr[3] = f"X{code}", market, "D", "N"
        arr[6], arr[8], arr[11], arr[20] = "BN", code, "50.0", "1"
        arr[33] = "202606"
        assert s.apply_reply(parse_onnewdata(",".join(arr))) is False, code
    assert s.positions() == []


# ---- fix/breakeven-avg-source-daytrade-tax(2026-08-26)----
# 群益損益試算「均價」= 成交價 + 買進手續費(prod 4991:469.50 → 469.62),樂觀套用的均價是純成交價;
# 前端要分得出來源才能算同一條打平線 → Position.avg_source;當沖稅減半要知道「今天進來幾張」→ today_qty。


def test_optimistic_fill_marks_avg_source_fill_and_counts_today_qty() -> None:
    s = CapitalStore()
    s.set_positions([])
    assert s.apply_reply(_evt(typ="D", qty="1000", price="469.5")) is True
    p = s.position_for("4989")
    assert p is not None
    assert p.avg_source == "fill"
    assert p.today_qty == 1


def test_snapshot_carries_avg_source_with_avg_and_recounts_today_qty() -> None:
    """快照落地:均價沿用時來源一起沿用;today_qty 由當日成交(_orders = 當日 backlog)重算:
    今天買 3 張、券商說共 5 張 → today_qty 3(其餘 2 張是過往庫存)。"""
    s = CapitalStore()
    s.set_positions(
        [Position(market="sec", stock_no="4989", qty=2, avg_price=80.02, avg_source="broker")]
    )
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", qty="3000", price="81.0")) is True
    s.set_positions([Position(market="sec", stock_no="4989", qty=5, avg_price=None)])
    p = s.position_for("4989")
    assert p is not None and p.qty == 5
    assert p.avg_source == "broker"  # 沿用均價 → 來源跟著沿用(損益回填標的 broker),不退成 None / fill
    assert p.today_qty == 3


def test_today_qty_nets_same_day_sells_and_clamps_to_holding() -> None:
    """今天買 3 賣 1 → 今天淨進 2;券商持有 1(其餘已出)→ clamp 到 1。"""
    s = CapitalStore()
    s.set_positions([])
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", qty="3000", price="81.0")) is True
    assert s.apply_reply(_evt(seq=SEQ_B, typ="D", bs="S00R2", qty="1000", price="82.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 2 and p.today_qty == 2
    s.set_positions([Position(market="sec", stock_no="4989", qty=1, avg_price=None)])
    p = s.position_for("4989")
    assert p is not None and p.today_qty == 1


def test_today_qty_is_per_kind_and_zero_for_futures() -> None:
    """融資今天買 1 張不算進現股列的 today_qty;期貨列恆 0(當沖稅制不同,前端不吃)。"""
    s = CapitalStore()
    s.set_positions([Position(market="sec", stock_no="4989", qty=2, avg_price=None)])
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", bs="B03R2", qty="1000", price="81.0")) is True
    cash = s.position_for("4989", "cash")
    margin = s.position_for("4989", "margin")
    assert cash is not None and cash.today_qty == 0
    assert margin is not None and margin.today_qty == 1
    s.set_positions([Position(market="fut", stock_no="QEFF6", qty=1, avg_price=100.0)])
    fut = s.position_for("QEFF6", market="fut")
    assert fut is not None and fut.today_qty == 0


def test_today_qty_excludes_fills_that_arrived_on_a_previous_day() -> None:
    """跨日長跑(review 2026-08-26 P1):昨天成交的 3 張到了今天不再是「今天進來的」,
    即使 _orders 沒被清 —— today_qty 看成交到達日,不看聚合有沒有清。"""
    clock = ["20260826"]
    s = CapitalStore(today=lambda: clock[0])
    s.set_positions([])
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", qty="3000", price="81.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.today_qty == 3
    clock[0] = "20260827"
    s.set_positions([Position(market="sec", stock_no="4989", qty=3, avg_price=None)])
    p = s.position_for("4989")
    assert p is not None and p.qty == 3 and p.today_qty == 0
    assert s.apply_reply(_evt(seq=SEQ_B, typ="D", qty="1000", price="82.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 4 and p.today_qty == 1


def test_today_qty_net_at_or_below_zero_with_inventory_is_zero() -> None:
    """昨庫存 10、今買 5、今賣 6 → 券商把今天的 5 買 6 賣先互抵成當沖,剩 1 張賣的是庫存 →
    今天「還在手上」的當沖段 = 0(review P3:語意 = 今日淨買進,不是今日買進總量)。"""
    s = CapitalStore()
    s.set_positions([Position(market="sec", stock_no="4989", qty=10, avg_price=80.0)])
    assert s.apply_reply(_evt(seq=SEQ_A, typ="D", qty="5000", price="81.0")) is True
    assert s.apply_reply(_evt(seq=SEQ_B, typ="D", bs="S00R2", qty="6000", price="82.0")) is True
    p = s.position_for("4989")
    assert p is not None and p.qty == 9 and p.today_qty == 0


# ---- fix/borrowless-short-calibration(2026-08-30;2026-08-28 prod 8358 無券當沖實錄)----
# 09:23:38 無券賣 1 張 @512 成交(reply idx6 = S08 → flag_label「無券」)→ 09:23:39 群益庫存段回
# 現股 T 列 -1000(不是融券 L 列)→ 09:52:07 現股買 1 張 @523 回補,部位歸零。
# 症狀:空單存續期間 today_qty = 0 → 前端賣出稅用 0.3% 而非當沖 0.15%(差 512×0.15% ≈ 1 檔);
# 負現股列 kind=cash 平倉鍵被鎖(user 手動買回)。


SEQ_C = "2313093000001"


def _fill_8358(seq: str, bs: str, qty: str, price: str) -> ReplyRecord:
    return _evt(seq=seq, typ="D", bs=bs, stock="8358", qty=qty, price=price)


def _borrowless_short_store() -> CapitalStore:
    s = CapitalStore()
    s.set_positions([])
    assert s.apply_reply(_fill_8358(SEQ_A, "S08R2", "1000", "512.0000")) is True  # 無券賣要套得上
    row = parse_balance_line(RAW_T_BORROWLESS_SHORT)
    assert row is not None
    s.set_positions([row])
    return s


def test_borrowless_short_counts_today_qty_after_broker_snapshot() -> None:
    """無券賣成交 + 群益負現股列落地 → 該空單今天賣出的 1 張要進 today_qty(前端當沖稅減半吃這格)。"""
    s = _borrowless_short_store()
    p = s.position_for("8358")
    assert p is not None and p.market == "sec" and p.qty == -1
    assert p.today_qty == 1


def test_borrowless_short_position_is_closable_with_cash_buy() -> None:
    """群益負現股列 = 無券空單:平倉鍵要能組出「現股買」回補單(交易所自動沖銷),不再鎖住。"""
    s = _borrowless_short_store()
    p = s.position_for("8358")
    assert p is not None
    order = build_close_order(p, PositionCloseRequest(market="sec", key="8358", price=523.0))
    assert (order.buy_sell, order.trade_kind, order.qty) == ("buy", "cash", 1)


def test_borrowless_short_buyback_fill_nets_to_zero_without_phantom_rows() -> None:
    """回補是現股買(reply idx6 = B00):樂觀套用要沖掉空單列、不能另開一列現股多單。"""
    s = _borrowless_short_store()
    assert s.apply_reply(_fill_8358(SEQ_B, "B00R2", "1000", "523.0000")) is True
    assert s.positions() == []


def test_cash_buy_offsets_borrowless_short_first_then_opens_long_with_residue() -> None:
    """無券空 2 張:現股買 1 → 空單剩 -1(均價不動、沒開現股列);再買 3 → 空單消、餘 2 張開現股多單
    (均價 = 這張單成交價)。交易所對同股號自動沖銷,樂觀套用要照同一語意。"""
    s = CapitalStore()
    s.set_positions([])
    assert s.apply_reply(_fill_8358(SEQ_A, "S08R2", "2000", "512.0000")) is True
    ds = s.position_for("8358", "daytrade_sell")
    assert ds is not None and ds.qty == -2 and ds.avg_price == 512.0 and ds.today_qty == 2
    assert s.apply_reply(_fill_8358(SEQ_B, "B00R2", "1000", "520.0000")) is True
    ds = s.position_for("8358", "daytrade_sell")
    assert ds is not None and ds.qty == -1 and ds.avg_price == 512.0 and ds.today_qty == 1
    assert s.position_for("8358", "cash") is None
    assert s.apply_reply(_fill_8358(SEQ_C, "B00R2", "3000", "523.0000")) is True
    assert s.position_for("8358", "daytrade_sell") is None
    cash = s.position_for("8358", "cash")
    assert cash is not None and cash.qty == 2 and cash.avg_price == 523.0
    assert cash.avg_source == "fill"


# ---- pr-152 review 收修(2026-08-30)----


def test_borrowless_sell_offsets_cash_long_first_then_opens_short_with_residue() -> None:
    """F-02:持現股多單時從閃電梯送「無券」賣(回報 idx6 S08):先沖同股號現股多單(交易所對同股號自動
    沖銷,與買向 B00 先沖空單對稱),餘量才開 daytrade_sell 空單列 —— 否則多長一列已解鎖平倉的空單,
    快照落地前 ~2 s 點下去就是一張非預期的現股買。"""
    s = CapitalStore()
    s.set_positions(
        [Position(market="sec", stock_no="8358", qty=5, avg_price=500.0, avg_source="broker")]
    )
    assert s.apply_reply(_fill_8358(SEQ_A, "S08R2", "1000", "512.0000")) is True
    cash = s.position_for("8358", "cash")
    assert cash is not None and cash.qty == 4 and cash.avg_price == 500.0  # 減碼:均價不動
    assert s.position_for("8358", "daytrade_sell") is None
    assert s.apply_reply(_fill_8358(SEQ_B, "S08R2", "6000", "513.0000")) is True
    assert s.position_for("8358", "cash") is None
    ds = s.position_for("8358", "daytrade_sell")
    assert ds is not None and ds.qty == -2 and ds.avg_price == 513.0 and ds.avg_source == "fill"
    assert ds.today_qty == 2


def test_borrowless_buy_side_fill_does_not_count_into_daytrade_today_qty() -> None:
    """F-08:無券**買向**(B08)在 `_apply_fill_locked` 已拒套(無部位語意),`_today_net_lots_locked`
    對 daytrade_sell 桶要同一把尺 —— 只計賣向;否則 B08 被算成 +1 淨買進,空單的 today_qty 靜默少 1。"""
    s = _borrowless_short_store()
    assert s.apply_reply(_fill_8358(SEQ_B, "B08R2", "1000", "520.0000")) is False
    row = parse_balance_line(RAW_T_BORROWLESS_SHORT)
    assert row is not None
    s.set_positions([row])  # 拒套的成交仍在聚合裡;下一輪快照落地會重算 today_qty —— 這一步才是 finding 顯形點
    ds = s.position_for("8358", "daytrade_sell")
    assert ds is not None and ds.qty == -1 and ds.today_qty == 1


def test_clear_drops_snapshot_watermark_no_phantom_reapply() -> None:
    """clear(重連重播前)必須連水位一起丟:重播的成交是歷史,若被當成
    「水位後增量」重套,首刷落地會幻影加倉(與 review F-02 同類洞,方向相反)。"""
    s = CapitalStore()
    s.set_positions([])  # 開機首刷
    s.begin_snapshot()  # 鏈出手(水位 = 空單集)
    s.clear()  # 重連重播前
    s.apply_reply(_evt(typ="D", qty="2000", price="80.0"))  # 重播歷史成交(seeded 關,不套)
    s.set_positions([])  # 重連後首刷:今天已出光,庫存快照為空 = 真相
    assert s.position_for("4989") is None
