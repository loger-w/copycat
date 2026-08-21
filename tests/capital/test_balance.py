"""OnRealBalanceReport 解析(SC-6)。樣本 = treading-king 2026-06-11 正式環境真實回報
(ID/帳號去敏)照搬;OnOpenInterest 為合成治具(欄序 prod 實測後校正)。"""

from __future__ import annotations

import pytest

from copycat.capital.balance import (
    BalanceCollector,
    ProfitRow,
    merge_fut_positions,
    parse_balance_line,
    parse_open_interest_line,
    parse_profit_line,
)
from copycat.capital.models import Position


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


# 今日買進 1 張現股:昨庫 0、今委買/買成 1000、即時庫存[14]=1000
RAW_T_BOUGHT = "2493,T,0,0,0,0,0,1000,0,1000,0,1000,0,0,1000,0,,A123456789,1234567890"
# 當沖軋平:買賣各 1000、即時庫存 0 → 不佔一列
RAW_T_FLAT = "3042,T,0,0,0,0,0,1000,1000,1000,1000,0,0,0,0,0,,A123456789,1234567890"
# 融資 3 張(昨日庫存):[1]=C、[2][3]=資額度(千元)、[16]=即時維持率(會跳動,不是價格!)
RAW_C_MARGIN = "3357,C,2000,1944,0,0,3000,0,0,0,0,3000,0,0,3000,0,155.63,A123456789,1234567890"
# 融券 2 張(依官方欄位表構造):qty 應為負
RAW_L_SHORT = "9105,L,0,0,2000,2000,0,0,0,0,0,2000,0,0,2000,0,130.25,A123456789,1234567890"
# 查詢結束標記
RAW_END = "##,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,"


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
    raw = RAW_L_SHORT.replace(",2000,0,130.25,", ",-2000,0,130.25,")
    p = parse_balance_line(raw)
    assert p is not None
    assert p.qty == -2 and p.kind == "short"


def test_parse_cash_negative_shares_keeps_short_direction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """現股列負股數(疑當沖先賣/無券賣出未回補;2026-08-20 user 實報空單方向錯)——
    舊 abs() 會把真空單顯示成多單,平倉映射再送賣單 = 對空單加倉(真金風險)。
    方向必須保留;kind 歸類(daytrade_sell?)待首筆實錄校準,整列 warning 就是蒐證通道。"""
    raw = RAW_T_BOUGHT.replace(",1000,0,,", ",-1000,0,,")
    with caplog.at_level("WARNING"):
        p = parse_balance_line(raw)
    assert p is not None
    assert p.qty == -1 and p.kind == "cash"
    assert any("負股數" in r.message and "2493" in r.message for r in caplog.records)


def test_parse_margin_negative_shares_keeps_short_direction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = RAW_C_MARGIN.replace(",3000,0,155.63,", ",-3000,0,155.63,")
    with caplog.at_level("WARNING"):
        p = parse_balance_line(raw)
    assert p is not None
    assert p.qty == -3 and p.kind == "margin"
    assert any("負股數" in r.message for r in caplog.records)


def test_parse_short_negative_shares_no_daytrade_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 融券列負股數是既有防禦路徑(符號未實測),不屬「疑當沖賣」蒐證對象,不洗版
    raw = RAW_L_SHORT.replace(",2000,0,130.25,", ",-2000,0,130.25,")
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
    bad = RAW_T_BOUGHT.replace(",1000,0,,", ",x,0,,")  # [14] 數字壞 → 整筆略過
    assert parse_balance_line(bad) is None


def test_unknown_kind_skipped() -> None:
    # 未知庫存種類寧缺勿錯:平倉映射依 kind 送單,猜錯=送錯單種
    assert parse_balance_line(RAW_T_BOUGHT.replace(",T,", ",Z,")) is None


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


def test_collector_new_query_resets_staging() -> None:
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.feed(RAW_T_BOUGHT)
    c.reset()  # 新一輪查詢
    c.feed(RAW_END)
    assert got == [[]]  # staging 已清,flush 空集合(全部出清的合法狀態)


def test_collector_abandoned_round_ignores_late_end_marker() -> None:
    """零事件死查詢逾期解卡 = 放棄一輪,但那一輪還欠一個 `##`(COM 回呼不帶查詢識別,
    遲到的終止符無法從內容分辨屬哪一輪)。放棄後的第一個「零列 ##」必須忽略 —
    flush 空集合會以全量取代語意把庫存整批清空(平倉鍵跟著鎖住)。"""
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.abandon()
    c.feed(RAW_END)  # 放棄輪遲到的終止符 → 吞掉,不 flush、不關閉本輪
    assert got == []
    c.feed(RAW_T_BOUGHT)  # 新一輪真回應照常收
    c.feed(RAW_END)
    assert len(got) == 1
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["2493"]


def test_collector_reset_after_abandon_clears_stale_debt() -> None:
    # 正常 reset(發查詢路徑)= 上一輪已正常收尾 → 欠帳歸零,真空帳戶的空 ## 照常 flush
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.abandon()
    c.reset()
    c.feed(RAW_END)
    assert got == [[]]


def test_collector_rows_clear_stale_debt() -> None:
    # 有 row 抵達 = 活的回應(不論屬哪一輪),flush 它就是最新快照 → 欠帳歸零
    got: list[list[object]] = []
    c = BalanceCollector(on_complete=got.append)
    c.abandon()
    c.feed(RAW_C_MARGIN)
    c.feed(RAW_END)
    assert len(got) == 1
    assert [p.stock_no for p in got[0] if isinstance(p, Position)] == ["3357"]


# 未實現-彙總(4-2-p)= 2026-06-11 正式環境真實回報(ID/帳號去敏)。
# 實際 30 欄(比文件 25 欄多尾端含費均價等);[1]=股票代號、[10]=平均買進(券賣)成本。
# 第一筆=查詢結果(000,訊息可空);總計列股號為空。
RAW_PNL_ROW = "揚博,2493,新台幣,現股,1000,180.00,-0.50,180000.00,179414.00,1368.00,178.05,178046.00,178000.00,46.00,46.00,0.00,540.00,0,0,0,0.00,0.77,0,,Y,1,0,178.628000,A123456789,1234567890"
RAW_PNL_MARGIN = "臺慶科,3357,新台幣,融資,3000,288.00,-7.50,864000.00,301364.00,-74636.00,311.75,376240.00,935000.00,240.00,221.00,0.00,2592.00,376000,559000,583,0.00,-7.98,0,,Y,2,3,312.950000,A123456789,1234567890"
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
    bad = RAW_PNL_ROW.replace(",1368.00,", ",x,")
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
    row = parse_profit_line(RAW_PNL_ROW.replace(",Y,1,0,", ",Y,2,0,"))
    assert row is not None and row.kind == "cash"


def test_parse_profit_line_unknown_kind_is_none(caplog: pytest.LogCaptureFixture) -> None:
    # 標籤與 [25] 都對不上 → kind=None:回填端視為不符、略過(寧缺均價,不可套錯成本
    # 基礎;融券代碼未實證前不猜)。整列進 log 才有下一步診斷素材;kind_raw 保留原文。
    raw = RAW_PNL_ROW.replace(",現股,", ",信用,").replace(",Y,1,0,", ",Y,7,0,")
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
    assert parse_profit_line(RAW_PNL_ROW.replace("178.05", "x")) is None  # 均價壞
    assert parse_profit_line(RAW_PNL_ROW.replace("178.05", "0")) is None  # 均價 0 不出垃圾


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
