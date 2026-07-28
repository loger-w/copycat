"""capital reply 解碼測試(SC-5)。fixture = treading-king 2026-06-10 正式環境真實回報
(帳號欄已匿名化)照搬;期權筆為依同格式構造的合成治具。"""

from __future__ import annotations

import dataclasses

from copycat.capital.reply import parse_onnewdata

# 現股買 預約單(收盤後掛)→ 之後被刪;Type=N 委託
RAW_N_PREORDER = "2313091595225,TS,N,N,9999,0000000,B00R2,TW,3357,,00000,293.0000,,,,,,,,,1000,,,20260610,14:59:48,,0000000,0671,PI,20260611,1000000055420,B,3357,,,,,,,,,,,,,,,2313092917892"
# 同一張單的刪單回報;Type=C,qty=原委託剩量
RAW_C_PREORDER = "2313091595225,TS,C,N,9999,0000000,B00R2,TW,3357,,00000,293.0000,,,,,,,,,1000,,,20260610,14:59:48,,0000000,0671,PI,20260611,1000000055420,B,3357,,,,,,,,,,,,,,,2313092917892"
# 融資賣 盤中成交(Type=D,idx38 有成交序號)
RAW_D_MARGIN_SELL = "2313092627047,TS,D,N,9999,0000000,S03R2,TW,4989,,S01Q7,83.7000,,,,,,,,,1000,,,20260610,12:46:31,,0000000,0671,PI,20260610,1020000573620,A,4989,,,,,,00006702389,,,,,,,,,2313092627047"
# 期貨 新倉買(TF;qty=口)
RAW_TF_NEW = "2315596711743,TF,N,N,F020000,4528443,BNR20,TW,QEF06,,u5834,873.0000,,,,,,,,,1,,,20260610,12:16:59,,0000000,0673,PI,20260610,2110001321199,A,FIQEF,202606,,,,,,,A,20260610,,,,N,,2315596711743"
# 選擇權 當沖賣(TO;合成治具,格式對齊 RAW_TF_NEW;idx6[1]=Y 當沖)
RAW_TO_DAYTRADE_SELL = "2315596711750,TO,N,N,F020000,4528443,SYR20,TW,TXO20000I6,,u5835,120.0000,,,,,,,,,2,,,20260610,12:20:00,,0000000,0673,PI,20260610,2110001321200,A,TXO,202606,,,,,,,A,20260610,,,,N,,2315596711750"


def test_parse_preorder_new() -> None:
    r = parse_onnewdata(RAW_N_PREORDER)
    assert r.seq_no == "2313091595225"
    assert r.market == "TS"
    assert r.status_raw == "N"
    assert r.status_label == "委託"
    assert r.order_err == "N"
    assert r.buy_sell == "B"
    assert r.flag_label == "現股"
    assert r.stock_no == "3357"
    assert r.price == 293.0
    assert r.qty == 1000
    assert r.time == "14:59:48"
    assert r.pre_order is True  # idx31 = B
    assert r.error_msg is None
    # 真實樣本:預約單 KeyNo(idx0)≠ 尾欄序號(idx47)— 刪改 API 吃哪個待首測,先解出來供 log 比對
    assert r.alt_seq_no == "2313092917892"
    assert r.alt_seq_no != r.seq_no


def test_parse_date_field() -> None:
    """idx23=委託建立日 — 排序鍵用,昨日預約單才不會壓在今日單上面。"""
    r = parse_onnewdata(RAW_N_PREORDER)
    assert r.date == "20260610"


def test_parse_cancel() -> None:
    r = parse_onnewdata(RAW_C_PREORDER)
    assert r.status_raw == "C"
    assert r.status_label == "刪單"
    assert r.seq_no == "2313091595225"


def test_parse_fill_margin_sell() -> None:
    r = parse_onnewdata(RAW_D_MARGIN_SELL)
    assert r.status_raw == "D"
    assert r.status_label == "成交"
    assert r.buy_sell == "S"
    assert r.flag_label == "融資"
    assert r.price == 83.7
    assert r.qty == 1000
    assert r.pre_order is False  # idx31 = A
    assert r.book_no == "S01Q7"
    assert r.alt_seq_no == r.seq_no  # 盤中單 KeyNo 與尾欄序號相同


def test_parse_futures_flag() -> None:
    r = parse_onnewdata(RAW_TF_NEW)
    assert r.market == "TF"
    assert r.buy_sell == "B"
    assert r.flag_label == "新倉"  # 期權 idx6[1] = Y當沖/N新倉/O平倉
    assert r.qty == 1


def test_parse_option_daytrade_flag() -> None:
    # 期權市場(TO)同走 _FUT_FLAG 單碼解讀:idx6="SYR20" → S 賣 + Y 當沖
    r = parse_onnewdata(RAW_TO_DAYTRADE_SELL)
    assert r.market == "TO"
    assert r.buy_sell == "S"
    assert r.flag_label == "當沖"
    assert r.stock_no == "TXO20000I6"
    assert r.price == 120.0
    assert r.qty == 2


def test_parse_option_close_flag() -> None:
    arr = RAW_TO_DAYTRADE_SELL.split(",")
    arr[6] = "BOR20"  # B 買 + O 平倉
    r = parse_onnewdata(",".join(arr))
    assert r.buy_sell == "B"
    assert r.flag_label == "平倉"


def test_parse_order_err_failed() -> None:
    # OrderErr=Y + idx44 錯誤訊息(無真實樣本,依官方 spec 構造)
    arr = RAW_N_PREORDER.split(",")
    arr[3] = "Y"
    arr[44] = "委託失敗:超過漲跌停"
    r = parse_onnewdata(",".join(arr))
    assert r.order_err == "Y"
    assert r.error_msg == "委託失敗:超過漲跌停"


def test_parse_after_qty() -> None:
    # U 改量:idx22 AfterQty(無真實樣本,依官方 spec 構造)
    arr = RAW_N_PREORDER.split(",")
    arr[2] = "U"
    arr[20] = "1000"  # 減量數
    arr[22] = "2000"  # 改後量
    r = parse_onnewdata(",".join(arr))
    assert r.status_label == "改量"
    assert r.after_qty == 2000


def test_parse_garbage_does_not_crash() -> None:
    r = parse_onnewdata("xxx")
    assert r.seq_no == "xxx"
    assert r.market is None  # 只有一欄,idx1 起全部缺
    assert r.qty == 0


def test_parse_invalid_side_yields_no_flag() -> None:
    # 官方 spec:刪單失敗等情況 idx6[0] 可能是 0(非 B/S)→ 不得解出半截 flag
    # 用期貨 fixture:_FUT_FLAG.get("N")="新倉" 才能暴露 side=None 但 flag 非 None 的語意矛盾
    arr = RAW_TF_NEW.split(",")
    arr[6] = "0NR20"
    r = parse_onnewdata(",".join(arr))
    assert r.buy_sell is None
    assert r.flag_label is None


def test_reply_record_is_dataclass() -> None:
    # pydantic → dataclass 改寫合約:replace 可產生變體(store 測試靠這個構造 err 事件)
    r = parse_onnewdata(RAW_N_PREORDER)
    r2 = dataclasses.replace(r, order_err="Y", error_msg="x")
    assert r2.order_err == "Y" and r2.seq_no == r.seq_no
