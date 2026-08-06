"""SC-1 純函式層測試:market_breadth 逐函式手算小樣本 + 漲跌停毫元邊界。

邏輯來源 = neigui(market_today / finmind_realtime / market_universe),
差異只有漲跌停判定改毫元精確等值(見 test_compute_breadth_limit_* 註解)。
"""

from __future__ import annotations

import datetime as _dt

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
    assert classify_stock_id("001") == "warrant"  # 3 位指數 row
    assert classify_stock_id("") == "warrant"
    assert classify_stock_id("  2330  ") is None  # 前後空白先 strip


def test_filter_universe_partitions_and_watch_list_wins() -> None:
    out = filter_universe(
        ["2330", "0050", "030171", "2317", "001"],
        watch_list={"2317"},
    )
    assert out["universe"] == {"2330"}
    assert out["excluded"]["etf"] == ["0050"]
    assert out["excluded"]["warrant"] == ["030171", "001"]
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
        "change_rate": 1.5,
        "volume_ratio": 1.5,
        "total_amount": 12345,
        "limit_up": False,
        "limit_down": False,
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
