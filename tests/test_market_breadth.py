"""SC-1 純函式層測試:market_breadth 逐函式手算小樣本 + 漲跌停毫元邊界。

邏輯來源 = neigui(market_today / finmind_realtime / market_universe),
差異只有漲跌停判定改毫元精確等值(見 test_compute_breadth_limit_* 註解)。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from copycat.market_breadth import (
    PRIMARY_INDUSTRY_OVERRIDE,
    assemble_universe,
    build_name_map,
    build_type_map,
    classify_stock_id,
    compute_breadth,
    dedup_sector_map,
    filter_universe,
    max_tick_datetime,
    parse_active_disposition,
)

# ---------------------------------------------------------------------------
# classify_stock_id / filter_universe(neigui market_universe 搬)
# ---------------------------------------------------------------------------


def test_classify_stock_id_buckets() -> None:
    assert classify_stock_id("2330") is None  # 4 位純數字非 00 → 普通股 candidate
    assert classify_stock_id("0050") == "etf"
    assert classify_stock_id("00679B") == "etf"  # 00 前綴優先於長度判定
    assert classify_stock_id("030171") == "warrant"  # 6 位權證
    assert classify_stock_id("2330A") == "warrant"  # 含非 digit
    # 3 位指數 row:`00` 前綴判定先於長度 → 落 etf 桶(neigui 原語意;兩桶都排除)
    assert classify_stock_id("001") == "etf"
    assert classify_stock_id("036") == "warrant"  # 非 00 前綴的指數 row → 長度不合
    assert classify_stock_id("") == "warrant"
    assert classify_stock_id("  2330  ") is None  # 前後空白先 strip


def test_filter_universe_partitions_and_watch_list_wins() -> None:
    out = filter_universe(
        ["2330", "0050", "030171", "2317", "001", "036"],
        watch_list={"2317"},
    )
    assert out["universe"] == {"2330"}
    assert out["excluded"]["etf"] == ["0050", "001"]  # 001 走 00 前綴 → etf 桶
    assert out["excluded"]["warrant"] == ["030171", "036"]
    assert out["excluded"]["watch_list"] == ["2317"]


def test_filter_universe_watch_list_precedes_classify() -> None:
    # 同時是 ETF + 處置股 → 歸 watch_list 桶(watch_list 優先語意)
    out = filter_universe(["0050"], watch_list={"0050"})
    assert out["excluded"]["watch_list"] == ["0050"]
    assert out["excluded"]["etf"] == []


# ---------------------------------------------------------------------------
# build_type_map / build_name_map / dedup_sector_map(neigui finmind_realtime 搬)
# ---------------------------------------------------------------------------


def test_build_type_map_latest_date_wins() -> None:
    rows = [
        {"stock_id": "2330", "type": "twse", "date": "2026-01-01"},
        {"stock_id": "2330", "type": "tpex", "date": "2026-02-01"},
        {"stock_id": "6488", "type": "tpex", "date": "2026-01-01"},
    ]
    assert build_type_map(rows) == {"2330": "tpex", "6488": "tpex"}


def test_build_type_map_skips_unknown_type_without_blocking() -> None:
    # type 非 twse/tpex 的 row 不寫入也不佔位,較舊的合法 row 仍應勝出
    rows = [
        {"stock_id": "2330", "type": "otc", "date": "2026-03-01"},
        {"stock_id": "2330", "type": "twse", "date": "2026-01-01"},
        {"stock_id": "001", "type": None, "date": "2026-03-01"},
    ]
    assert build_type_map(rows) == {"2330": "twse"}


def test_build_name_map_latest_date_wins_and_skips_missing() -> None:
    rows = [
        {"stock_id": "2330", "stock_name": "舊名", "date": "2026-01-01"},
        {"stock_id": "2330", "stock_name": "台積電", "date": "2026-02-01"},
        {"stock_id": "6488", "stock_name": None, "date": "2026-02-01"},
        {"stock_id": None, "stock_name": "無代號", "date": "2026-02-01"},
    ]
    assert build_name_map(rows) == {"2330": "台積電"}


def test_dedup_sector_map_override_and_tie_break() -> None:
    rows = [
        # override 命中 → 忽略 row 上的 industry_category
        {"stock_id": "2330", "type": "twse", "industry_category": "光電業", "date": "2026-01-01"},
        # 同 date tie → industry ASC(光 U+5149 < 電 U+96FB)
        {"stock_id": "1234", "type": "twse", "industry_category": "電子工業", "date": "2026-01-01"},
        {"stock_id": "1234", "type": "twse", "industry_category": "光電業", "date": "2026-01-01"},
        # date DESC 優先於 industry ASC(水 U+6C34 < 食 U+98DF,但 02-01 較新)
        {"stock_id": "4321", "type": "twse", "industry_category": "水泥工業", "date": "2026-01-01"},
        {"stock_id": "4321", "type": "twse", "industry_category": "食品工業", "date": "2026-02-01"},
        # industry 空 → 其他
        {"stock_id": "5678", "type": "tpex", "industry_category": None, "date": "2026-01-01"},
        # type 非 twse/tpex → 整檔不進 map
        {"stock_id": "9999", "type": "otc", "industry_category": "電子工業", "date": "2026-01-01"},
    ]
    assert dedup_sector_map(rows) == {
        "2330": "半導體業",
        "1234": "光電業",
        "4321": "食品工業",
        "5678": "其他",
    }


def test_primary_industry_override_table_shape() -> None:
    assert PRIMARY_INDUSTRY_OVERRIDE["2330"] == "半導體業"
    # bug sector-override-phantom:金融保險無「業」尾(TaiwanStockInfo 真實字串)
    assert PRIMARY_INDUSTRY_OVERRIDE["2882"] == "金融保險"
    assert len(PRIMARY_INDUSTRY_OVERRIDE) == 10


# ---------------------------------------------------------------------------
# parse_active_disposition(neigui market_universe._parse_active_disposition 搬)
# ---------------------------------------------------------------------------


def test_parse_active_disposition_inclusive_bounds() -> None:
    today = _dt.date(2026, 8, 6)
    rows = [
        {"stock_id": "1111", "period_start": "2026-08-06", "period_end": "2026-08-20"},  # 起日
        {"stock_id": "2222", "period_start": "2026-07-20", "period_end": "2026-08-06"},  # 迄日
        {"stock_id": "3333", "period_start": "2026-07-01", "period_end": "2026-08-05"},  # 已過
        {"stock_id": "4444", "period_start": "2026-08-07", "period_end": "2026-08-20"},  # 未到
    ]
    assert parse_active_disposition(rows, today) == {"1111", "2222"}


def test_parse_active_disposition_skips_bad_rows() -> None:
    today = _dt.date(2026, 8, 6)
    rows = [
        {"stock_id": "1111", "period_start": "not-a-date", "period_end": "2026-08-20"},
        {"stock_id": "2222", "period_start": "2026-08-01"},  # 缺 period_end
        {"period_start": "2026-08-01", "period_end": "2026-08-20"},  # 缺 stock_id
    ]
    assert parse_active_disposition(rows, today) == set()


# ---------------------------------------------------------------------------
# max_tick_datetime(neigui _max_tick_date 搬;回台北 naive)
# ---------------------------------------------------------------------------


def test_max_tick_datetime_z_suffix_converts_to_taipei_naive() -> None:
    rows = [{"date": "2026-08-06T02:23:45Z"}]
    assert max_tick_datetime(rows) == _dt.datetime(2026, 8, 6, 10, 23, 45)


def test_max_tick_datetime_naive_kept_and_max_wins() -> None:
    rows = [
        {"date": "2026-08-06 10:23:45"},
        {"date": "2026-08-06 10:25:01"},
        {"date": "2026-08-06 09:00:00"},
    ]
    assert max_tick_datetime(rows) == _dt.datetime(2026, 8, 6, 10, 25, 1)


def test_max_tick_datetime_mixed_z_and_naive_comparable() -> None:
    # 混用 aware/naive 若不歸一會在 max() 炸 TypeError
    rows = [{"date": "2026-08-06T02:23:45Z"}, {"date": "2026-08-06 10:25:01"}]
    assert max_tick_datetime(rows) == _dt.datetime(2026, 8, 6, 10, 25, 1)


def test_max_tick_datetime_none_cases() -> None:
    assert max_tick_datetime([]) is None
    assert max_tick_datetime([{"date": None}, {"foo": 1}]) is None
    assert max_tick_datetime([{"date": "garbage"}]) is None


def test_max_tick_datetime_upper_bound_drops_future_rows() -> None:
    """越界(遠超本機時鐘)的單一髒 row 不得決定整份快照的時刻(review P1-2)。"""
    rows = [
        {"date": "2026-08-06 09:29:30"},
        {"date": "2026-08-06 09:30:10"},
        {"date": "2026-08-06 13:30:00"},  # 髒 row:上游偶發回收盤時刻
    ]
    bound = _dt.datetime(2026, 8, 6, 9, 40)

    assert max_tick_datetime(rows, upper_bound=bound) == _dt.datetime(2026, 8, 6, 9, 30, 10)
    # 不給 bound = 舊行為(全收)
    assert max_tick_datetime(rows) == _dt.datetime(2026, 8, 6, 13, 30)


def test_max_tick_datetime_upper_bound_inclusive_and_all_dropped() -> None:
    """邊界含等值(恰在界上的 row 仍算數);全部越界 → None(呼叫端視同該輪失敗)。"""
    bound = _dt.datetime(2026, 8, 6, 9, 40)

    assert max_tick_datetime([{"date": "2026-08-06 09:40:00"}], upper_bound=bound) == bound
    assert max_tick_datetime([{"date": "2026-08-06 13:30:00"}], upper_bound=bound) is None


def test_max_tick_datetime_upper_bound_applies_after_taipei_normalisation() -> None:
    """Z 尾(UTC)先歸一成台北 naive 才比界 —— 否則 8 小時偏移會把正常 row 判成越界。"""
    rows = [{"date": "2026-08-06T02:23:45Z"}]  # = 台北 10:23:45
    assert max_tick_datetime(rows, upper_bound=_dt.datetime(2026, 8, 6, 10, 30)) == _dt.datetime(
        2026, 8, 6, 10, 23, 45
    )


# ---------------------------------------------------------------------------
# assemble_universe(白名單 → filter_universe 順序)
# ---------------------------------------------------------------------------


def test_assemble_universe_whitelist_then_filter() -> None:
    rows = [
        {"stock_id": "2330", "close": 1.0},
        {"stock_id": "0050", "close": 2.0},  # 在白名單內但結構是 ETF
        {"stock_id": "2317", "close": 3.0},  # 在白名單內但處置股
        {"stock_id": "001", "close": 4.0},  # 指數 row,不在白名單
        {"stock_id": "6488", "close": 5.0},  # 不在白名單(未收錄)
    ]
    primary_sector = {"2330": "半導體業", "0050": "其他", "2317": "其他電子業"}
    out = assemble_universe(rows, primary_sector, watch_list={"2317"})
    assert [r["stock_id"] for r in out] == ["2330"]
    # 回傳的是原 row 物件(欄位不被裁切)
    assert out[0]["close"] == 1.0


def test_assemble_universe_empty_sector_map_removes_all() -> None:
    rows = [{"stock_id": "2330"}]
    assert assemble_universe(rows, {}, watch_list=set()) == []


# ---------------------------------------------------------------------------
# compute_breadth — 分桶 / 排除 / rows 輸出
# ---------------------------------------------------------------------------

_TYPE_MAP = {"2330": "twse", "2317": "twse", "6488": "tpex", "5483": "tpex"}
_NAME_MAP = {"2330": "台積電", "6488": "環球晶"}


def test_compute_breadth_buckets_by_change_rate() -> None:
    rows = [
        {"stock_id": "2330", "change_rate": 1.5, "close": 1000.0, "change_price": 15.0},
        {"stock_id": "2317", "change_rate": 0.0, "close": 200.0, "change_price": 0.0},
        {"stock_id": "6488", "change_rate": -2.0, "close": 500.0, "change_price": -10.0},
        {"stock_id": "5483", "change_rate": 0.0, "close": 100.0, "change_price": 0.0},
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["twse"] == {"limit_up": 0, "up": 1, "flat": 1, "down": 0, "limit_down": 0}
    assert out["tpex"] == {"limit_up": 0, "up": 0, "flat": 1, "down": 1, "limit_down": 0}


def test_compute_breadth_skips_null_change_rate_and_unknown_market() -> None:
    rows = [
        {"stock_id": "2330", "change_rate": 1.0, "close": 100.0, "change_price": 1.0},
        {"stock_id": "2317", "change_rate": None, "close": 100.0, "change_price": 1.0},
        {"stock_id": "001", "change_rate": 1.0, "close": 100.0, "change_price": 1.0},
        {"stock_id": None, "change_rate": 1.0},
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert [r["stock_id"] for r in out["rows"]] == ["2330"]
    assert out["twse"]["up"] == 1


def test_compute_breadth_returns_none_when_empty() -> None:
    assert compute_breadth([], _TYPE_MAP, _NAME_MAP) is None
    assert compute_breadth([{"stock_id": "001", "change_rate": 1.0}], _TYPE_MAP, _NAME_MAP) is None


def test_compute_breadth_row_shape() -> None:
    rows = [
        {
            "stock_id": "2330",
            "change_rate": 1.5,
            "close": 1000.0,
            "change_price": 15.0,
            "total_volume": 300,
            "yesterday_volume": 200,
            "total_amount": 12345,
        },
        # name_map 查無 → fallback stock_id;yesterday_volume 0 → volume_ratio None
        {
            "stock_id": "5483",
            "change_rate": -1.0,
            "close": 100.0,
            "change_price": -1.0,
            "total_volume": 100,
            "yesterday_volume": 0,
            "total_amount": None,
        },
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0] == {
        "stock_id": "2330",
        "name": "台積電",
        "market": "twse",
        "close": 1000.0,
        "change_rate": 1.5,
        "volume_ratio": 1.5,
        "total_amount": 12345,
        "limit_up": False,
        "limit_down": False,
        "touched_limit_up": False,
        "touched_limit_down": False,
    }
    assert out["rows"][1]["name"] == "5483"
    assert out["rows"][1]["volume_ratio"] is None


# ---------------------------------------------------------------------------
# compute_breadth — 漲跌停毫元邊界(手算數字直接釘)
# ---------------------------------------------------------------------------


def test_compute_breadth_limit_up_exact_milli() -> None:
    # prev = 100.000 元 → 100_000 毫;cand = 110_000,110 元段 tick = 500 毫
    # → 漲停 110_000 毫 = 110.0 元
    rows = [{"stock_id": "2330", "change_rate": 10.0, "close": 110.0, "change_price": 10.0}]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["twse"]["limit_up"] == 1
    assert out["twse"]["up"] == 0  # 桶互斥:漲停不重複計入上漲
    assert out["rows"][0]["limit_up"] is True


def test_compute_breadth_one_tick_below_limit_up_is_plain_up() -> None:
    # 109.5 元 = 109_500 毫,距漲停整整一個 tick(500 毫)
    rows = [{"stock_id": "2330", "change_rate": 9.5, "close": 109.5, "change_price": 9.5}]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["twse"] == {"limit_up": 0, "up": 1, "flat": 0, "down": 0, "limit_down": 0}


def test_compute_breadth_half_tick_below_limit_up_is_plain_up() -> None:
    # 109.8 元距漲停 200 毫 < 半 tick(250 毫)—— neigui float 版會判成漲停,
    # 毫元精確等值版明確判為「上漲」(SC-1 刻意收緊處)。
    rows = [{"stock_id": "2330", "change_rate": 9.8, "close": 109.8, "change_price": 9.8}]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["twse"]["limit_up"] == 0
    assert out["twse"]["up"] == 1


def test_compute_breadth_limit_down_exact_milli() -> None:
    # prev = 100_000 毫;cand = 90_000,90 元段 tick = 100 毫 → 跌停 90_000 毫
    rows = [{"stock_id": "6488", "change_rate": -10.0, "close": 90.0, "change_price": -10.0}]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["tpex"] == {"limit_up": 0, "up": 0, "flat": 0, "down": 0, "limit_down": 1}
    assert out["rows"][0]["limit_down"] is True


def test_compute_breadth_one_tick_above_limit_down_is_plain_down() -> None:
    # 90.1 元 = 90_100 毫,距跌停整整一個 tick(100 毫)
    rows = [{"stock_id": "6488", "change_rate": -9.9, "close": 90.1, "change_price": -9.9}]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["tpex"] == {"limit_up": 0, "up": 0, "flat": 0, "down": 1, "limit_down": 0}


def test_compute_breadth_limit_across_tick_zone_boundary() -> None:
    # prev = 45.5 元 = 45_500 毫。
    # 漲:cand = 45_500*11//10 = 50_050 → 已跨進 50–100 元段(tick 100 毫)
    #     → floor 至 50_000 毫 = 50.0 元
    # 跌:cand = 45_500*9//10 = 40_950 → 10–50 元段(tick 50 毫)→ 40_950 毫
    up_rows = [{"stock_id": "2330", "change_rate": 9.89, "close": 50.0, "change_price": 4.5}]
    down_rows = [{"stock_id": "2330", "change_rate": -10.0, "close": 40.95, "change_price": -4.55}]
    up_out = compute_breadth(up_rows, _TYPE_MAP, _NAME_MAP)
    down_out = compute_breadth(down_rows, _TYPE_MAP, _NAME_MAP)
    assert up_out is not None and down_out is not None
    assert up_out["twse"]["limit_up"] == 1
    assert down_out["twse"]["limit_down"] == 1


def test_compute_breadth_no_limit_judgement_when_prev_close_unusable() -> None:
    rows = [
        # close 缺 → 不判 limit,只按 change_rate 正負分桶
        {"stock_id": "2330", "change_rate": 10.0, "close": None, "change_price": 10.0},
        # change_price 缺 → 同上
        {"stock_id": "2317", "change_rate": 10.0, "close": 110.0, "change_price": None},
        # prev_close = 0 → 不判 limit(避免 0 價推導出荒謬漲停)
        {"stock_id": "6488", "change_rate": 1.0, "close": 5.0, "change_price": 5.0},
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["twse"] == {"limit_up": 0, "up": 2, "flat": 0, "down": 0, "limit_down": 0}
    assert out["tpex"] == {"limit_up": 0, "up": 1, "flat": 0, "down": 0, "limit_down": 0}
    assert all(not r["limit_up"] and not r["limit_down"] for r in out["rows"])


# ---------------------------------------------------------------------------
# compute_breadth — 觸及未鎖(touched)/ close 直通(R3 漲跌停列表)
# ---------------------------------------------------------------------------


def test_compute_breadth_touched_limit_up_when_high_hits_but_close_backs_off() -> None:
    # prev = 105.0 − 5.0 = 100.0 元 → 漲停 110.0 元;high 摸到但收 105 → 觸及未鎖
    rows = [
        {
            "stock_id": "2330",
            "change_rate": 5.0,
            "close": 105.0,
            "change_price": 5.0,
            "high": 110.0,
            "low": 104.0,
        }
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["touched_limit_up"] is True
    assert out["rows"][0]["touched_limit_down"] is False
    assert out["rows"][0]["limit_up"] is False
    # 家數桶不受 touched 影響(觸及未鎖仍是「上漲」)
    assert out["twse"] == {"limit_up": 0, "up": 1, "flat": 0, "down": 0, "limit_down": 0}


def test_compute_breadth_touched_limit_down_when_low_hits_but_close_backs_off() -> None:
    # prev = 95.0 + 5.0 = 100.0 元 → 跌停 90.0 元;low 摜到但收 95 → 觸及未鎖
    rows = [
        {
            "stock_id": "6488",
            "change_rate": -5.0,
            "close": 95.0,
            "change_price": -5.0,
            "high": 99.0,
            "low": 90.0,
        }
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["touched_limit_down"] is True
    assert out["rows"][0]["touched_limit_up"] is False
    assert out["rows"][0]["limit_down"] is False


def test_compute_breadth_touched_is_false_when_already_locked() -> None:
    """已鎖停板的列不重複算「觸及未鎖」—— 前端狀態歸屬才不會兩個 badge 打架。"""
    rows = [
        {
            "stock_id": "2330",
            "change_rate": 10.0,
            "close": 110.0,
            "change_price": 10.0,
            "high": 110.0,
            "low": 105.0,
        },
        {
            "stock_id": "6488",
            "change_rate": -10.0,
            "close": 90.0,
            "change_price": -10.0,
            "high": 95.0,
            "low": 90.0,
        },
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["limit_up"] is True
    assert out["rows"][0]["touched_limit_up"] is False
    assert out["rows"][1]["limit_down"] is True
    assert out["rows"][1]["touched_limit_down"] is False


def test_compute_breadth_touched_false_when_high_low_missing() -> None:
    """舊 fixture / 剪裁快照無 high/low → 兩向皆 False(不得炸,也不得亂猜)。"""
    rows = [{"stock_id": "2330", "change_rate": 5.0, "close": 105.0, "change_price": 5.0}]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["touched_limit_up"] is False
    assert out["rows"][0]["touched_limit_down"] is False


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("", id="空字串"),
        pytest.param("-", id="破折號"),
        pytest.param("N/A", id="非數值字串"),
        pytest.param({}, id="非純量"),
        pytest.param(True, id="bool"),
    ],
)
def test_compute_breadth_touched_tolerates_non_numeric_high_low(bad: object) -> None:
    """`high`/`low` 非數值(未成交檔位常見的空字串 / `"-"`)→ 不判 touched,**不得拋**。

    `round(x * 1000)` 對 str / dict 直接 TypeError,而那個例外從 `_apply` 一路逃到
    `_poll_loop` 的傘罩被吞掉:`_fail()` 沒被呼叫 → 退避不動、stale 不亮,面板只是
    凍在最後一則。一列髒值就足以讓**整片**家數停止更新且零錯誤訊號。
    """
    rows = [
        {
            "stock_id": "2330",
            "change_rate": 5.0,
            "close": 105.0,
            "change_price": 5.0,
            "high": bad,
            "low": bad,
        },
        # 同輪的正常列:整輪不得被前一列的髒值中斷
        {
            "stock_id": "6488",
            "change_rate": 5.0,
            "close": 105.0,
            "change_price": 5.0,
            "high": 110.0,
            "low": 104.0,
        },
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["touched_limit_up"] is False
    assert out["rows"][0]["touched_limit_down"] is False
    assert out["rows"][1]["touched_limit_up"] is True


def test_compute_breadth_touched_needs_exact_milli_equality() -> None:
    # 漲停 110.0 元;high 109.5(一個整 tick 500 毫之下)→ 不算觸及
    rows = [
        {
            "stock_id": "2330",
            "change_rate": 5.0,
            "close": 105.0,
            "change_price": 5.0,
            "high": 109.5,
            "low": 104.0,
        }
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["touched_limit_up"] is False


def test_compute_breadth_touched_false_when_prev_close_unusable() -> None:
    """前收不可用(change_price 缺)→ 無漲跌停價可比,touched 一律 False。"""
    rows = [
        {
            "stock_id": "2330",
            "change_rate": 5.0,
            "close": 105.0,
            "change_price": None,
            "high": 110.0,
            "low": 90.0,
        }
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["touched_limit_up"] is False
    assert out["rows"][0]["touched_limit_down"] is False


def test_compute_breadth_close_passes_through_including_none() -> None:
    """`close` 直通 snapshot 原值(前端現價欄);缺值列不得補 0 假裝有價。"""
    rows = [
        {"stock_id": "2330", "change_rate": 1.5, "close": 105.0, "change_price": 5.0},
        {"stock_id": "6488", "change_rate": 1.5, "close": None, "change_price": 5.0},
    ]
    out = compute_breadth(rows, _TYPE_MAP, _NAME_MAP)
    assert out is not None
    assert out["rows"][0]["close"] == 105.0
    assert out["rows"][1]["close"] is None


# ---------------------------------------------------------------------------
# SC-1 parity oracle —— 真 FinMind rows,expected 由 neigui 現碼全管線算出
# ---------------------------------------------------------------------------

_PARITY_PATH = Path(__file__).parent / "fixtures" / "breadth_parity.json"


def _bucket_of(row: dict) -> str:
    """rows 逐檔的桶(與 record_breadth_parity.py 的推導同式)。"""
    if row["limit_up"]:
        return "limit_up"
    if row["limit_down"]:
        return "limit_down"
    if row["change_rate"] > 0:
        return "up"
    if row["change_rate"] < 0:
        return "down"
    return "flat"


def test_breadth_parity() -> None:
    """copycat 全管線 vs neigui 全管線:counts 全等 + 逐檔 bucket 全等。

    這是 **oracle 對照**不是 TDD 紅測試(實作完成後才寫,天然綠)。fixture
    由 `tests/fixtures/record_breadth_parity.py` 一次性手跑錄製(真 FinMind
    原始 rows + neigui 現碼算出的 expected),重錄方式見該腳本檔頭。
    """
    fixture = json.loads(_PARITY_PATH.read_text(encoding="utf-8"))
    today = _dt.date.fromisoformat(fixture["today"])

    # fixture 自身健檢:oracle 必須真的涵蓋 limit 判定,否則 parity 是空談
    expected_counts = fixture["expected_counts"]
    assert expected_counts["twse"] and expected_counts["tpex"]
    limit_total = sum(
        expected_counts[m][b] for m in ("twse", "tpex") for b in ("limit_up", "limit_down")
    )
    assert limit_total > 0, "fixture 對漲跌停判定零覆蓋,需盤中重錄"

    # 時刻推導也吃這份真 rows(review TC-5):engine 的 trade_date / 分鐘鍵全建立在
    # 它上面,而 fixture 帶著真 FinMind 的 `date` 欄格式(Z 尾 / 台北 naive 都可能)
    snapshot_dt = max_tick_datetime(fixture["snapshot_rows"])
    assert snapshot_dt is not None
    assert snapshot_dt.date().isoformat() == fixture["today"]

    stock_info = fixture["stock_info_rows"]
    primary_sector = dedup_sector_map(stock_info)
    type_map = build_type_map(stock_info)
    name_map = build_name_map(stock_info)
    watch_list = parse_active_disposition(fixture["disposition_rows"], today)

    universe = assemble_universe(fixture["snapshot_rows"], primary_sector, watch_list)
    assert len(universe) == fixture["row_counts"]["universe"]

    out = compute_breadth(universe, type_map, name_map)
    assert out is not None
    assert {"twse": out["twse"], "tpex": out["tpex"]} == expected_counts

    actual_buckets = {r["stock_id"]: _bucket_of(r) for r in out["rows"]}
    assert actual_buckets == fixture["expected_rows_buckets"]
