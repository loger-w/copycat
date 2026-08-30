"""OnRealBalanceReport 解析(SC-6)。樣本 = treading-king 2026-06-11 正式環境真實回報
(ID/帳號去敏)照搬;OnOpenInterest 為合成治具(欄序 prod 實測後校正)。"""

from __future__ import annotations

import logging
import time

import pytest

from copycat.capital.balance import (
    STALE_WINDOW_S,
    BalanceCollector,
    ProfitRow,
    merge_fut_positions,
    parse_balance_line,
    parse_open_interest_line,
    parse_profit_line,
)
from copycat.capital.models import Position
from tests.capital.balance_rows import (
    RAW_C_MARGIN,
    RAW_END,
    RAW_L_SHORT,
    RAW_T_BOUGHT,
    RAW_T_FLAT,
    balance_variant,
)
from tests.capital.profit_rows import RAW_PNL_MARGIN, RAW_PNL_ROW, pnl_variant


# ── merge_fut_positions:同契約淨額合併(review A5)──────────────


def test_merge_fut_positions_nets_buy_and_sell(caplog: pytest.LogCaptureFixture) -> None:
    rows = [
        Position(market="fut", stock_no="TXFI6", qty=3, avg_price=23000.0),
        Position(market="fut", stock_no="TXFI6", qty=-1, avg_price=22900.0),
    ]
    with caplog.at_level("WARNING"):
        out = merge_fut_positions(rows)
    assert len(out) == 1
    assert out[0].qty == 2  # B 正 S 負相加
    assert any("TXFI6" in r.message for r in caplog.records)  # 合併發生要留痕


def test_merge_fut_positions_same_side_sums() -> None:
    rows = [
        Position(market="fut", stock_no="TXFI6", qty=2, avg_price=23000.0),
        Position(market="fut", stock_no="TXFI6", qty=1, avg_price=23100.0),
    ]
    out = merge_fut_positions(rows)
    assert len(out) == 1 and out[0].qty == 3


def test_merge_fut_positions_distinct_contracts_untouched() -> None:
    rows = [
        Position(market="fut", stock_no="TXFI6", qty=2),
        Position(market="fut", stock_no="MXFI6", qty=-1),
    ]
    out = merge_fut_positions(rows)
    assert [(p.stock_no, p.qty) for p in out] == [("TXFI6", 2), ("MXFI6", -1)]


def test_merge_fut_positions_zero_net_dropped() -> None:
    rows = [
        Position(market="fut", stock_no="TXFI6", qty=1),
        Position(market="fut", stock_no="TXFI6", qty=-1),
    ]
    assert merge_fut_positions(rows) == []  # 淨額 0 = 無部位,不佔一列


def test_parse_cash_position() -> None:
    p = parse_balance_line(RAW_T_BOUGHT)
    assert p is not None
    assert p.stock_no == "2493"
    assert p.qty == 1  # 即時庫存[14]=1000 股 → 1 張
    assert p.kind == "cash"
    assert p.market == "sec"
    assert p.avg_price is None  # 此報告無均價欄([16] 是維持率),均價待損益試算 API


def test_parse_margin_position() -> None:
    p = parse_balance_line(RAW_C_MARGIN)
    assert p is not None
    assert p.stock_no == "3357"
    assert p.qty == 3
    assert p.kind == "margin"  # 平倉反向映射要送融資賣,不是現股賣
    assert p.avg_price is None  # [16]=155.63 是維持率,絕不可當均價/價格


def test_parse_short_position_negative_qty() -> None:
    p = parse_balance_line(RAW_L_SHORT)
    assert p is not None
    assert p.qty == -2  # 融券放空 → 負張數(close 映射靠 qty>0 判多空)
    assert p.kind == "short"


def test_parse_short_negative_shares_defensive() -> None:
    """融券列真實符號未實測:若 [14] 回的是負股數,floor division 會把幅度多算一張
    再負負得正 — 防禦寫法兩種符號都要對。"""
    raw = balance_variant(RAW_L_SHORT, {14: "-2000"})
    p = parse_balance_line(raw)
    assert p is not None
    assert p.qty == -2 and p.kind == "short"


def test_parse_cash_negative_shares_keeps_short_direction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """現股列負股數 = 無券當沖先賣未回補(2026-08-20 user 實報空單方向錯;2026-08-28 prod 8358
    實錄校準 kind)—— 舊 abs() 會把真空單顯示成多單,平倉映射再送賣單 = 對空單加倉(真金風險)。
    方向保留、kind 歸 daytrade_sell(_CLOSE_MAP 回補 = 現股買);整列 DEBUG 留痕(每輪都會看到,
    不洗 INFO;review 2026-08-30 F-03)。"""
    raw = balance_variant(RAW_T_BOUGHT, {14: "-1000"})
    with caplog.at_level("DEBUG"):
        p = parse_balance_line(raw)
    assert p is not None
    assert p.qty == -1 and p.kind == "daytrade_sell"
    hits = [r for r in caplog.records if "負股數" in r.message and "2493" in r.message]
    assert hits and all(r.levelno == logging.DEBUG for r in hits)  # DEBUG 這一格是不洗版的依據,釘住
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_parse_margin_negative_shares_keeps_short_direction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = balance_variant(RAW_C_MARGIN, {14: "-3000"})
    with caplog.at_level("WARNING"):
        p = parse_balance_line(raw)
    assert p is not None
    assert p.qty == -3 and p.kind == "margin"
    assert any("負股數" in r.message for r in caplog.records)


def test_parse_short_negative_shares_no_daytrade_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 融券列負股數是既有防禦路徑(符號未實測),不屬「疑當沖賣」蒐證對象,不洗版
    raw = balance_variant(RAW_L_SHORT, {14: "-2000"})
    with caplog.at_level("WARNING"):
        parse_balance_line(raw)
    assert not [r for r in caplog.records if "負股數" in r.message]


def test_daytrade_flat_skipped() -> None:
    # 當沖軋平(即時庫存 0)不佔一列
    assert parse_balance_line(RAW_T_FLAT) is None


def test_unparseable_or_short_line_skipped() -> None:
    assert parse_balance_line(RAW_END) is None  # 結束標記
    assert parse_balance_line("") is None
    assert parse_balance_line("2493,T,0,0") is None  # 欄位不足
    bad = balance_variant(RAW_T_BOUGHT, {14: "x"})  # [14] 數字壞 → 整筆略過
    assert parse_balance_line(bad) is None


def test_unknown_kind_skipped() -> None:
    # 未知庫存種類寧缺勿錯:平倉映射依 kind 送單,猜錯=送錯單種
    assert parse_balance_line(balance_variant(RAW_T_BOUGHT, {1: "Z"})) is None


def test_collector_flush_on_end_marker() -> None:
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.feed(RAW_T_BOUGHT)
    c.feed(RAW_C_MARGIN)
    assert got == []  # 未收到結束標記不 flush
    c.feed(RAW_END)
    assert len(got) == 1
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["2493", "3357"]


def test_collector_timeout_flush() -> None:
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append, timeout_s=0.0)
    c.feed(RAW_T_BOUGHT)
    c.poll()  # timeout=0 → 任何 elapsed 都該 flush(沒等到 ## 的保險)
    assert len(got) == 1


def test_collector_timeout_flush_closes_round() -> None:
    # timeout 保險先 flush 後,殘餘事件與遲到的 ## 不可再 flush —
    # on_complete 是全量取代語意,二次 flush 會把部位整批換成尾段幾檔或空集合
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append, timeout_s=0.0)
    c.feed(RAW_T_BOUGHT)
    c.poll()  # timeout flush(部分清單)
    assert len(got) == 1
    c.feed(RAW_C_MARGIN)  # 同一輪殘餘事件 → 丟棄
    c.feed(RAW_END)  # 遲到的結束標記 → 不得 flush 空/尾段集合
    c.poll()
    assert len(got) == 1
    c.reset()  # 下一輪查詢重新開張
    c.feed(RAW_C_MARGIN)
    c.feed(RAW_END)
    assert len(got) == 2
    assert [p.stock_no for p in got[1] if isinstance(p, Position)] == ["3357"]


class _FakeClock:
    """collector 可注入時鐘:欠帳時間窗的窗內/窗外兩態不能靠 sleep 20s 來測。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_collector_new_query_resets_staging() -> None:
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.feed(RAW_T_BOUGHT)
    c.reset()  # 新一輪查詢
    c.feed(RAW_END)
    assert got == [[]]  # staging 已清,flush 空集合(全部出清的合法狀態)


def test_collector_abandoned_round_ignores_late_end_marker() -> None:
    """零事件死查詢逾期解卡 = 放棄一輪,但那一輪還欠一個 `##`(COM 回呼不帶查詢識別,
    遲到的終止符無法從內容分辨屬哪一輪)。放棄後窗內的第一個「零列 ##」必須忽略 —
    flush 空集合會以全量取代語意把庫存整批清空(平倉鍵跟著鎖住)。"""
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.reset()  # 發查詢(= 開始等這一輪的回應;abandon 只對 awaiting 的 collector 記帳)
    c.abandon()
    c.feed(RAW_END)  # 放棄輪遲到的終止符 → 吞掉,不 flush、不關閉本輪
    assert got == []
    c.feed(RAW_T_BOUGHT)  # 新一輪真回應照常收
    c.feed(RAW_END)
    assert len(got) == 1
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["2493"]


def test_collector_reset_after_abandon_clears_stale_debt() -> None:
    # 正常 reset(發查詢路徑)= 上一輪已正常收尾 → 欠帳窗關掉,真空帳戶的空 ## 照常 flush
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.reset()
    c.abandon()
    c.reset()
    c.feed(RAW_END)
    assert got == [[]]


def test_collector_stale_window_expires_and_empty_round_flushes() -> None:
    """T5:欠帳計數有**時間窗**上限 —— 窗外的零列 `##` = 帳戶這一輪真的空了,欠帳作廢、必須 flush。
    (純計數的失效模式:連續死查詢每輪各記一筆,真空帳戶的空回應被無限期吞掉。)"""
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, clock=clock)
    c.reset()
    c.abandon()
    clock.now += STALE_WINDOW_S - 0.5  # 窗內
    c.feed(RAW_END)
    assert got == []
    c.reset(keep_abandoned=True)
    c.abandon()  # 又一輪死查詢(計數式在這裡開始自我延續)
    clock.now += STALE_WINDOW_S + 0.5  # 窗外
    c.feed(RAW_END)
    assert got == [[]]


def test_collector_abandon_clears_partial_round() -> None:
    """T7:abandon 必須把本輪已收的殘列清掉。留著的話 (a) 新一輪的列會接在舊列後面
    flush 出混合快照;(b) `_last_feed` 不清 → 幫浦圈的 timeout poll 會把殘列
    當成「全部部位」flush 出去(全量取代語意 = 沒收到的那些檔全消失)。"""
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.reset()
    c.feed(RAW_C_MARGIN)  # 本輪只收到一列就卡死
    c.abandon()
    c.poll(now_monotonic=time.monotonic() + 5.0)  # timeout 保險不得 flush 殘列
    assert got == []
    # 放棄到下一次 reset(發查詢)之間正是要防守的空窗:此時抵達的列屬新回應,
    # 不可與被放棄那輪的殘列混在同一份快照裡
    c.feed(RAW_T_BOUGHT)
    c.feed(RAW_END)
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["2493"]  # 舊列沒混進來


def test_collector_abandon_after_flush_is_noop() -> None:
    """F4:abandon() 只對「還在等這一輪回應」的 collector 記帳(`_awaiting` 守門)。
    pending watchdog 逾時會對 profit/OI 兩段一起呼叫,已正常收尾的那一段若也開窗,
    下一輪合法的空回應(帳戶真的沒部位)就被白吞一次 → 幽靈部位多掛一輪。"""
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.reset()
    c.feed(RAW_END)  # 本輪正常收尾
    assert got == [[]]
    c.abandon()  # watchdog 對已收尾的段呼叫 → no-op
    assert c._stale_until is None and c._owed == 0
    c.reset()
    c.feed(RAW_END)
    assert got == [[], []]  # 下一輪的空回應照常 flush


def test_collector_rows_then_end_marker_flush_and_consume_debt() -> None:
    # 帶列的 `##` 照 flush(那批列就是它的快照)並消耗一筆欠帳;rows 本身不動欠帳
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.reset()
    c.abandon()
    c.feed(RAW_C_MARGIN)
    c.feed(RAW_END)
    assert len(got) == 1
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["3357"]
    assert c._owed == 0  # 帶列的 ## 也消耗了那一筆


# 未實現-彙總(4-2-p)= 2026-06-11 正式環境真實回報(ID/帳號去敏);實列本體在 `profit_rows`
# (`RAW_PNL_ROW` / `RAW_PNL_MARGIN`,[1]=股票代號、[10]=平均買進(券賣)成本)。
# 第一筆=查詢結果(000,訊息可空);總計列股號為空 —— 這兩種只有 parser 邊界用得到,留在這裡。
RAW_PNL_TOTAL = ",,新台幣,9999,0,0.00,0.00,1599000.00,940891.00,-91721.00,0.00,1032932.00,1684500.00,432.00,409.00,0.00,4797.00,595000,652000,583,0.00,0.00,0,,N,3,0,0.000000,A123456789,1234567890"
RAW_PNL_STATUS = "000,"


def test_parse_profit_line() -> None:
    # 均價之外還要 [9]損益(含費稅息)/[5]報告市價/[12]成交價金 —— 前端「券商基底+即時平移」口徑用;
    # [3]交易種類也要解析:同檔多種庫存並存時每種類一列,回填只認同種類(成本基礎不可混用)
    assert parse_profit_line(RAW_PNL_ROW) == ProfitRow(
        "2493", 178.05, 1368.0, 180.0, 178000.0, "cash", "現股"
    )
    assert parse_profit_line(RAW_PNL_MARGIN) == ProfitRow(
        "3357", 311.75, -74636.0, 288.0, 935000.0, "margin", "融資"
    )


def test_parse_profit_line_pnl_fields_optional() -> None:
    # 損益欄壞掉只丟那幾欄,均價仍要保住(均價是主要產出)
    bad = pnl_variant(RAW_PNL_ROW, {9: "x"})
    assert parse_profit_line(bad) == ProfitRow(
        "2493", 178.05, None, 180.0, 178000.0, "cash", "現股"
    )


# 2026-08-20 prod 實錄(ID/帳號去敏):SKCOM 中文欄位整列損毀(Big5 被當 CP1252 再
# best-fit 壓回 ASCII,「現股」→'2{aN'、「融資」→'?A﹐e',不可逆)— 系統 ACP=950 正常,
# 損壞在 SKCOM 自身鏈路。數字欄不受影響;[25] = 種類代碼(現股=1/融資=2,與 06-11
# 乾淨樣本交叉一致)是標籤損毀時唯一可靠的種類來源。
RAW_PNL_GARBLED_CASH = "Ap?v,3450,?O1o,2{aN,1000,553.00,-14.00,553000.00,551199.00,-17947.00,569.15,569146.00,569000.00,146.00,142.00,0.00,1659.00,0,0,0,0.00,-3.14,0,,Y,1,0,571.005000,A123456789,1234567890"
RAW_PNL_GARBLED_MARGIN = "￥|ou¯e,5608,?O1o,?A﹐e,5000,17.05,-0.45,85250.00,34938.00,188.00,16.96,34775.00,84750.00,25.00,21.00,0.00,255.00,34750,50000,10,0.00,0.22,0,,Y,2,3,17.010000,A123456789,1234567890"


def test_parse_profit_line_garbled_label_falls_back_to_kind_code() -> None:
    # 標籤亂碼 → 退 [25] 種類代碼:現股=1 / 融資=2(prod 2026-08-20 + fixture 06-11 雙源一致)
    cash = parse_profit_line(RAW_PNL_GARBLED_CASH)
    assert cash is not None and cash.kind == "cash" and cash.avg_price == 569.15
    assert cash.kind_raw == "2{aN"
    margin = parse_profit_line(RAW_PNL_GARBLED_MARGIN)
    assert margin is not None and margin.kind == "margin" and margin.avg_price == 16.96


def test_parse_profit_line_label_wins_over_kind_code() -> None:
    # 標籤可解時以標籤為準([25] 語意屬觀察歸納,非官方文件;可解標籤是更強證據)
    row = parse_profit_line(pnl_variant(RAW_PNL_ROW, {25: "2"}))
    assert row is not None and row.kind == "cash"


def test_parse_profit_line_unknown_kind_is_none(caplog: pytest.LogCaptureFixture) -> None:
    # 標籤與 [25] 都對不上 → kind=None:回填端視為不符、略過(寧缺均價,不可套錯成本
    # 基礎;融券代碼未實證前不猜)。整列進 log 才有下一步診斷素材;kind_raw 保留原文。
    raw = pnl_variant(RAW_PNL_ROW, {3: "信用", 25: "7"})
    with caplog.at_level("WARNING"):
        row = parse_profit_line(raw)
    assert row is not None and row.kind is None
    assert row.kind_raw == "信用"
    assert any("信用" in r.message and "揚博" in r.message for r in caplog.records)


def test_parse_profit_line_fallback_hit_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    # 亂碼標籤但 [25] 有解 → 不洗版(修好就該安靜;2026-08-20 修前每分鐘 3 發)
    with caplog.at_level("WARNING"):
        parse_profit_line(RAW_PNL_GARBLED_CASH)
    assert not [r for r in caplog.records if "種類標籤未知" in r.message]


def test_parse_profit_skips_status_total_end_and_junk() -> None:
    assert parse_profit_line(RAW_PNL_STATUS) is None  # 查詢結果列(訊息可空)
    assert parse_profit_line(RAW_PNL_TOTAL) is None  # 總計列(股號空)不出垃圾
    assert parse_profit_line("##,,,,") is None  # 結束標記
    assert parse_profit_line("") is None
    assert parse_profit_line("名,3357,新台幣,現股,1000") is None  # 欄位不足
    assert parse_profit_line(pnl_variant(RAW_PNL_ROW, {10: "x"})) is None  # 均價壞
    assert parse_profit_line(pnl_variant(RAW_PNL_ROW, {10: "0"})) is None  # 均價 0 不出垃圾


def test_collector_with_profit_parser() -> None:
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append, parse=parse_profit_line)
    c.feed(RAW_PNL_STATUS)
    c.feed(RAW_PNL_ROW)
    c.feed(RAW_PNL_TOTAL)
    c.feed("##")
    assert got == [[ProfitRow("2493", 178.05, 1368.0, 180.0, 178000.0, "cash", "現股")]]


# OnOpenInterest(GetOpenInterestGW nFormat=1)— 合成治具,欄序 prod 實測後校正。
# 假定欄序(群益手冊慣例):市場,帳號,商品,買賣別,口數,當沖口數,平均成本,...
RAW_OI_LONG = "TF,1234567890,TXFI6,B,2,0,23000.000000,0,0"
RAW_OI_SHORT = "TO,1234567890,TXO20000I6,S,1,0,120.500000,0,0"


def test_parse_open_interest_long() -> None:
    p = parse_open_interest_line(RAW_OI_LONG)
    assert p is not None
    assert p.market == "fut"
    assert p.stock_no == "TXFI6"
    assert p.qty == 2
    assert p.avg_price == 23000.0


def test_parse_open_interest_short_negative_qty() -> None:
    p = parse_open_interest_line(RAW_OI_SHORT)
    assert p is not None
    assert p.qty == -1  # S 賣方 → 負口數(close 映射靠 qty>0 判多空)
    assert p.stock_no == "TXO20000I6"
    assert p.avg_price == 120.5


def test_parse_open_interest_end_marker_and_no_data() -> None:
    assert parse_open_interest_line("##") is None  # 結束標記
    assert parse_open_interest_line("TF,1234567890,查無資料") is None  # 含「無資料」訊息列
    assert parse_open_interest_line("") is None


def test_parse_open_interest_unparseable_returns_none() -> None:
    # 防禦性解析:欄位不足/買賣別非 B/S/口數壞/口數 0 → None(caller log)
    assert parse_open_interest_line("TF,1234567890,TXFI6") is None
    assert parse_open_interest_line("TF,1234567890,TXFI6,X,2,0,23000.0") is None
    assert parse_open_interest_line("TF,1234567890,TXFI6,B,x,0,23000.0") is None
    assert parse_open_interest_line("TF,1234567890,TXFI6,B,0,0,23000.0") is None


def test_parse_open_interest_bad_avg_price_kept_as_none() -> None:
    # 成本價附屬欄壞掉不丟整筆(口數/方向是主要產出)
    p = parse_open_interest_line("TF,1234567890,TXFI6,B,2,0,x,0,0")
    assert p is not None
    assert p.qty == 2 and p.avg_price is None


def test_collector_two_abandoned_rounds_swallow_two_late_end_markers() -> None:
    """R7 review P0(2026-08-22):欠帳是**計數 + 時間窗**,不是一次性時間戳。
    連續兩輪零事件死查詢各欠一個 `##`;COM 解卡後兩個遲到終止符接連抵達 ——
    第一個吞掉即關窗的話,第二個零列 `##` 照 flush 空集合,把有庫存清成無部位(原 bug 兩輪重現)。"""
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, clock=clock)
    c.reset()
    c.abandon()  # 第 1 輪死查詢
    c.reset(keep_abandoned=True)
    c.abandon()  # 第 2 輪死查詢
    c.reset(keep_abandoned=True)  # 第 3 輪查詢出手
    clock.now += 1.0
    c.feed(RAW_END)  # 第 1 輪遲到 ##
    c.feed(RAW_END)  # 第 2 輪遲到 ##
    assert got == []  # 兩個都是欠帳,一個都不得 flush
    c.feed(RAW_C_MARGIN)  # 第 3 輪真回應
    c.feed(RAW_END)
    assert len(got) == 1
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["3357"]


def test_collector_rows_do_not_cancel_remaining_debt() -> None:
    """R7 review P1(2026-08-22):rows 抵達不可把欠帳整個清掉 —— 損益段第一筆固定是
    `000` 查詢結果表頭,它一到就關窗的話,欠帳窗對 profit 段形同虛設。
    語意:每個 `##` 消耗一筆欠帳;帶列的 `##` 照 flush(那批列就是它的快照),
    之後窗內的零列 `##` 仍按剩餘欠帳吞掉。"""
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, clock=clock)
    c.reset()
    c.abandon()
    c.reset(keep_abandoned=True)
    c.abandon()  # 欠兩筆
    c.reset(keep_abandoned=True)
    c.feed(RAW_C_MARGIN)  # 某一輪的列 + ## → flush,消耗一筆
    c.feed(RAW_END)
    assert len(got) == 1
    c.reset(keep_abandoned=True)
    clock.now += 1.0
    c.feed(RAW_END)  # 剩下那一筆欠帳的零列 ## → 吞掉
    assert len(got) == 1
    c.feed(RAW_END)  # 欠帳已清 → 零列 ## 照 flush(真空帳戶)
    assert got[-1] == []


def test_collector_profit_header_then_swallowed_end_marker_does_not_timeout_flush() -> None:
    """R7 review round-2 P0(2026-08-22):損益段遲到回應 = `000` 表頭(parse 成 None,staging 仍空)
    + `##`。終止符被當欠帳吞掉後,`_last_feed` 若仍停在表頭抵達時刻,幫浦圈 1s 後的 `poll()`
    會以 timeout 保險 flush 空集合 —— 均價/含費稅基底整批洗掉(balance 段則是清空部位)。"""
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, parse=parse_profit_line, clock=clock)
    c.reset()
    c.abandon()
    c.reset(keep_abandoned=True)
    clock.now += 1.0
    c.feed(RAW_PNL_STATUS)  # 放棄輪遲到的表頭
    c.feed(RAW_END)  # 放棄輪遲到的終止符 → 吞掉
    assert got == []
    clock.now += 1.5
    c.poll()  # timeout 保險不得把吞掉的那一輪 flush 成空集合
    assert got == []
    c.feed(RAW_PNL_STATUS)  # 新一輪真回應
    c.feed(RAW_PNL_ROW)
    c.feed(RAW_END)
    assert len(got) == 1 and [r.stock_no for r in got[0] if isinstance(r, ProfitRow)] == ["2493"]


def test_collector_closed_round_terminator_still_consumes_debt() -> None:
    """放棄輪的 `##` 若在本輪已 flush(`_closed`)後才到,仍須消耗一筆欠帳 ——
    否則欠帳殘留到下一輪,白吞一次合法的零列回應(真空帳戶多掛一輪幽靈部位)。"""
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, clock=clock)
    c.reset()
    c.abandon()
    c.reset(keep_abandoned=True)
    c.feed(RAW_C_MARGIN)
    clock.now += 1.5
    c.poll()  # 本輪由 timeout 保險 flush
    assert len(got) == 1
    c.feed(RAW_END)  # 放棄輪遲到的 ## 在 _closed 期間抵達
    assert c._owed == 0


# ── N017:欠帳是**逐筆** deadline,不是一個被續命的共用窗 ─────────────


def test_collector_expired_debt_does_not_ride_on_a_later_abandon() -> None:
    """N017:`abandon()` 原本把**單一** `_stale_until` 推到 now+20 —— 等於替所有未清欠帳續命。

    profit / OI 兩段的 abandon 相距可達 60s(pending watchdog 一輪一次):第 1 筆欠帳
    早在 t+20 就該過期,卻跟著第 2 筆的窗一起活著 → 解卡後接連抵達的兩個零列 `##`
    被吞掉兩個,而其中第二個是**合法的空回應**(帳戶真的沒部位)→ 幽靈部位多掛一輪。

    逐筆 deadline 下:第 1 筆在 t=61 早已過期被作廢,只剩第 2 筆能吞一個;
    第二個零列 `##` 照 flush 空集合。
    """
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, clock=clock)
    c.reset()
    c.abandon()  # 第 1 筆欠帳,deadline = t0 + 20
    clock.now += 60.0  # 下一輪 watchdog(第 1 筆早已過期)
    c.reset(keep_abandoned=True)
    c.abandon()  # 第 2 筆欠帳,deadline = t0 + 80
    clock.now += 1.0
    c.reset(keep_abandoned=True)
    c.feed(RAW_END)  # 遲到的零列 ## #1 → 消耗僅存的那一筆欠帳
    assert got == []
    c.feed(RAW_END)  # 合法的空回應:欠帳已清光,必須 flush
    assert got == [[]]


def test_collector_debt_deadlines_expire_independently() -> None:
    """逐筆 deadline 的第二面:兩筆欠帳**分別**到期。
    第 1 筆過期後仍在窗內的第 2 筆照樣擋得住一個零列 `##`(不是「過期一筆就全清」)。"""
    got: list[list[object]] = []
    clock = _FakeClock()
    c = BalanceCollector(on_complete=got.append, clock=clock)
    c.reset()
    c.abandon()  # deadline = t0 + 20
    clock.now += 15.0
    c.reset(keep_abandoned=True)
    c.abandon()  # deadline = t0 + 35
    clock.now += 10.0  # t0+25:第 1 筆過期、第 2 筆仍在窗內
    c.reset(keep_abandoned=True)
    c.feed(RAW_END)
    assert got == []  # 第 2 筆欠帳吞掉它
    c.feed(RAW_END)
    assert got == [[]]  # 沒有第三筆可吞


# ── N018-1:吞終止符的 WARNING 要指名是哪一段 collector ─────────────


def test_swallowed_terminator_warning_names_the_collector(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """三段(balance / profit / oi)共用同一句「忽略放棄輪遲到的終止符」——
    prod log 分不出被抑制的是哪一段部位更新。名字由建構參數帶入。"""
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append, parse=parse_profit_line, name="oi")
    c.reset()
    c.abandon()
    with caplog.at_level("WARNING"):
        c.feed(RAW_END)
    assert got == []
    assert any("oi" in r.getMessage() for r in caplog.records)


# ── N018-2:重連落地用專用 clear(),不走 reset() ────────────────────


def test_clear_does_not_mark_awaiting() -> None:
    """`reset()` 的語意是「發新查詢」→ `_awaiting = True`。重連落地(`_set_status("ok")`)
    根本沒有在途查詢,拿 reset 當清點會讓 collector 進入「等回應中」——
    下一次 watchdog 的 `abandon()` 於是記帳成功,白吞一輪合法的空回應。"""
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.reset()
    c.abandon()
    c.clear()
    assert c._stale_until is None and c._owed == 0
    c.abandon()  # 沒在等回應 → no-op
    assert c._stale_until is None and c._owed == 0
    c.reset()
    c.feed(RAW_END)
    assert got == [[]]  # 合法的空回應沒被吞
