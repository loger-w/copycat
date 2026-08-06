"""SC-1 純函式層測試:sector_rotation 逐函式手算小樣本。

neigui `backend/tests/test_market_today.py:239-360`(rotation 八案)與 `:407-447`
(members 排序 / vol_ratio 邊界)等價搬移,手算 fixture 數字同源;copycat 側另補
`rows_to_chain_map` 三案(正常 parse / 任一欄 falsy 整列丟 / 同桶去重 —— R4)。
"""

from __future__ import annotations

import pytest

from copycat.sector_rotation import (
    compute_sector_members,
    compute_sector_rotation,
    rows_to_chain_map,
)

# ---------------------------------------------------------------------------
# rows_to_chain_map(neigui industry_chain `_rows_to_map` 搬)
# ---------------------------------------------------------------------------


def test_rows_to_chain_map_parses_industry_sub_stock() -> None:
    rows = [
        {
            "date": "2026-08-05",
            "industry": "半導體業",
            "sub_industry": "IC設計",
            "stock_id": "2454",
        },
        {
            "date": "2026-08-05",
            "industry": "半導體業",
            "sub_industry": "晶圓代工",
            "stock_id": "2330",
        },
        {
            "date": "2026-08-05",
            "industry": "電子零組件業",
            "sub_industry": "被動元件",
            "stock_id": "2327",
        },
    ]
    assert rows_to_chain_map(rows) == {
        "半導體業": {"IC設計": ["2454"], "晶圓代工": ["2330"]},
        "電子零組件業": {"被動元件": ["2327"]},
    }


def test_rows_to_chain_map_drops_row_when_any_field_falsy() -> None:
    """R4:sid / industry / sub 任一 falsy → **整列丟**(不進 "" 桶)。"""
    rows = [
        {"industry": "半導體業", "sub_industry": "IC設計", "stock_id": "2454"},
        {"industry": "半導體業", "stock_id": "2330"},  # 缺 sub_industry
        {"industry": "半導體業", "sub_industry": "", "stock_id": "3008"},  # sub 空字串
        {"sub_industry": "IC設計", "stock_id": "2379"},  # 缺 industry
        {"industry": "半導體業", "sub_industry": "IC設計"},  # 缺 stock_id
    ]
    out = rows_to_chain_map(rows)
    assert out == {"半導體業": {"IC設計": ["2454"]}}
    assert "" not in out
    assert "" not in out["半導體業"]


def test_rows_to_chain_map_skips_non_dict_rows() -> None:
    """列本身不是 dict(上游回殘表 / 壞快取)→ 跳過該列,同批其他列照收(review S-3)。

    `row.get` 在 str / None / list 上直接 AttributeError,而這支的兩個呼叫點一個在
    boot 路徑(`_restore_chain`)、一個在背景 task(`_refresh_chain`)—— 前者炸掉是
    整台 server 起不來,後者是 task 靜默死透而類股面板停在舊表上零錯誤訊號。
    """
    rows = [
        {"industry": "半導體業", "sub_industry": "IC設計", "stock_id": "2454"},
        "2330",  # type: ignore[list-item]  # 上游回字串列
        None,  # type: ignore[list-item]
        ["半導體業", "晶圓代工", "2330"],  # type: ignore[list-item]
        {"industry": "水泥工業", "sub_industry": "水泥製造", "stock_id": "1101"},
    ]
    assert rows_to_chain_map(rows) == {
        "半導體業": {"IC設計": ["2454"]},
        "水泥工業": {"水泥製造": ["1101"]},
    }


def test_rows_to_chain_map_dedups_same_stock_in_same_bucket() -> None:
    """同 (industry, sub) 內同 sid 只留一次;跨 sub 允許重複(N-to-M 對映)。"""
    rows = [
        {"industry": "半導體業", "sub_industry": "IC設計", "stock_id": "2454"},
        {"industry": "半導體業", "sub_industry": "IC設計", "stock_id": "2454"},
        {"industry": "半導體業", "sub_industry": "晶圓代工", "stock_id": "2454"},
    ]
    assert rows_to_chain_map(rows) == {
        "半導體業": {"IC設計": ["2454"], "晶圓代工": ["2454"]},
    }


# ---------------------------------------------------------------------------
# compute_sector_rotation(neigui test_market_today.py:239-355 等價搬)
# ---------------------------------------------------------------------------


def test_compute_sector_rotation_none_when_chain_missing() -> None:
    assert compute_sector_rotation([{"stock_id": "2330", "change_rate": 1.0}], None) is None
    assert compute_sector_rotation([{"stock_id": "2330", "change_rate": 1.0}], {}) is None


def test_compute_sector_rotation_hand_calc_and_sort() -> None:
    chain = {
        "半導體業": {
            "IC設計": ["2454"],
            "晶圓代工": ["2330"],
        },
        "電子零組件業": {
            "被動元件": ["2412"],
        },
    }
    universe = [
        {"stock_id": "2454", "change_rate": 5.0, "total_volume": 100, "yesterday_volume": 50},
        {"stock_id": "2330", "change_rate": 1.0, "total_volume": 200, "yesterday_volume": 100},
        {"stock_id": "2412", "change_rate": -2.0, "total_volume": 30, "yesterday_volume": 60},
    ]
    out = compute_sector_rotation(universe, chain)
    assert out is not None
    industries = out["industries"]
    # avg desc: 半導體業 avg=(5+1)/2=3.0 > 電子零組件業 avg=-2.0
    assert [i["name"] for i in industries] == ["半導體業", "電子零組件業"]

    semi = industries[0]
    assert semi["members"] == 2
    assert semi["avg_change_rate"] == pytest.approx(3.0)
    # vol_ratio = (100+200)/(50+100) = 300/150 = 2.0
    assert semi["vol_ratio"] == pytest.approx(2.0)
    # subs desc by avg: IC設計(5.0) > 晶圓代工(1.0)
    assert [s["name"] for s in semi["subs"]] == ["IC設計", "晶圓代工"]

    electronic = industries[1]
    assert electronic["vol_ratio"] == pytest.approx(30 / 60)


def test_compute_sector_rotation_dedup_same_stock_multiple_subs_same_industry() -> None:
    """一檔多桶:同產業內同 stock_id 出現在兩個 sub → industry 層去重一票。"""
    chain = {
        "半導體業": {
            "IC設計": ["2330"],
            "晶圓代工": ["2330"],  # 同股同產業另一 sub
        },
    }
    universe = [
        {"stock_id": "2330", "change_rate": 4.0, "total_volume": 100, "yesterday_volume": 50},
    ]
    out = compute_sector_rotation(universe, chain)
    assert out is not None
    semi = out["industries"][0]
    assert semi["members"] == 1  # 去重後只算一次,不是 2
    assert semi["avg_change_rate"] == pytest.approx(4.0)
    # sub 層各自獨立,兩個 sub 各自都有這檔(不去重)
    assert {s["name"] for s in semi["subs"]} == {"IC設計", "晶圓代工"}
    assert all(s["members"] == 1 for s in semi["subs"])


def test_compute_sector_rotation_change_rate_null_excluded() -> None:
    chain = {"半導體業": {"IC設計": ["2454", "2330"]}}
    universe = [
        {"stock_id": "2454", "change_rate": 5.0},
        {"stock_id": "2330", "change_rate": None},  # 剔除
    ]
    out = compute_sector_rotation(universe, chain)
    assert out is not None
    assert out["industries"][0]["members"] == 1
    assert out["industries"][0]["avg_change_rate"] == pytest.approx(5.0)


def test_compute_sector_rotation_vol_ratio_missing_field_excludes_from_both_sides() -> None:
    """量比分子分母同步剔除 —— 缺 yesterday_volume 的股不進 Σtotal_volume,
    避免不對稱剔除高估量比。"""
    chain = {"半導體業": {"IC設計": ["2454", "2330"]}}
    universe = [
        {"stock_id": "2454", "change_rate": 1.0, "total_volume": 1000, "yesterday_volume": 500},
        {"stock_id": "2330", "change_rate": 2.0, "total_volume": 9999},  # yesterday_volume 缺
    ]
    out = compute_sector_rotation(universe, chain)
    assert out is not None
    # 若未同步剔除,分子會誤含 2330 的 9999 → vol_ratio 被高估
    assert out["industries"][0]["vol_ratio"] == pytest.approx(1000 / 500)


def test_compute_sector_rotation_vol_ratio_denominator_zero_after_exclusion() -> None:
    """剔除後分母 0 → vol_ratio None(不是 members 0 —— avg 仍算)。"""
    chain = {"半導體業": {"IC設計": ["2454"]}}
    universe = [
        {"stock_id": "2454", "change_rate": 1.0},  # 兩個 volume 欄都缺
    ]
    out = compute_sector_rotation(universe, chain)
    assert out is not None
    assert out["industries"][0]["members"] == 1
    assert out["industries"][0]["vol_ratio"] is None


def test_compute_sector_rotation_zero_members_industry_skipped() -> None:
    """成員 0 的產業(chain 內股票在 universe 全缺或 change_rate 全 null)略過。"""
    chain = {
        "半導體業": {"IC設計": ["2454"]},
        "冷門業": {"冷門子業": ["9999"]},  # 9999 不在 universe
    }
    universe = [{"stock_id": "2454", "change_rate": 1.0}]
    out = compute_sector_rotation(universe, chain)
    assert out is not None
    assert [i["name"] for i in out["industries"]] == ["半導體業"]


def test_compute_sector_rotation_empty_universe_returns_empty_industries() -> None:
    chain = {"半導體業": {"IC設計": ["2454"]}}
    out = compute_sector_rotation([], chain)
    assert out == {"industries": []}


# ---------------------------------------------------------------------------
# compute_sector_members(neigui test_market_today.py:363-425 等價搬)
# ---------------------------------------------------------------------------


def test_compute_sector_members_unknown_industry_returns_none() -> None:
    chain = {"半導體業": {"IC設計": ["2454"]}}
    assert compute_sector_members([], chain, {}, "不存在的產業") is None


def test_compute_sector_members_unknown_sub_industry_returns_none() -> None:
    chain = {"半導體業": {"IC設計": ["2454"]}}
    universe = [{"stock_id": "2454", "change_rate": 1.0}]
    assert compute_sector_members(universe, chain, {}, "半導體業", "不存在子業") is None


def test_compute_sector_members_sub_industry_filters_and_sorts() -> None:
    chain = {"半導體業": {"IC設計": ["2454", "2330"], "晶圓代工": ["3008"]}}
    universe = [
        {
            "stock_id": "2454",
            "change_rate": -1.0,
            "total_volume": 100,
            "yesterday_volume": 50,
            "total_amount": 999,
        },
        {
            "stock_id": "2330",
            "change_rate": 5.0,
            "total_volume": 0,
            "yesterday_volume": 100,
            "total_amount": 111,
        },
    ]
    name_map = {"2454": "聯發科", "2330": "台積電"}
    out = compute_sector_members(universe, chain, name_map, "半導體業", "IC設計")
    assert out == {
        "industry": "半導體業",
        "sub_industry": "IC設計",
        "members": [
            {
                "stock_id": "2330",
                "name": "台積電",
                "change_rate": 5.0,
                "vol_ratio": pytest.approx(0.0),
                "total_amount": 111,
            },
            {
                "stock_id": "2454",
                "name": "聯發科",
                "change_rate": -1.0,
                "vol_ratio": pytest.approx(2.0),
                "total_amount": 999,
            },
        ],
    }


def test_compute_sector_members_no_sub_industry_unions_all_subs() -> None:
    chain = {"半導體業": {"IC設計": ["2454"], "晶圓代工": ["2330"]}}
    universe = [
        {"stock_id": "2454", "change_rate": 1.0},
        {"stock_id": "2330", "change_rate": 2.0},
    ]
    out = compute_sector_members(universe, chain, {}, "半導體業")
    assert out is not None
    assert out["sub_industry"] is None
    assert {m["stock_id"] for m in out["members"]} == {"2454", "2330"}


def test_compute_sector_members_null_change_rate_sorted_last() -> None:
    chain = {"半導體業": {"IC設計": ["A", "B", "C"]}}
    universe = [
        {"stock_id": "A", "change_rate": None},
        {"stock_id": "B", "change_rate": 3.0},
        {"stock_id": "C", "change_rate": -1.0},
    ]
    out = compute_sector_members(universe, chain, {}, "半導體業", "IC設計")
    assert out is not None
    assert [m["stock_id"] for m in out["members"]] == ["B", "C", "A"]


def test_compute_sector_members_vol_ratio_missing_or_zero_denominator_is_none() -> None:
    chain = {"半導體業": {"IC設計": ["A", "B"]}}
    universe = [
        {"stock_id": "A", "change_rate": 1.0, "total_volume": 100},  # yesterday_volume 缺
        {"stock_id": "B", "change_rate": 1.0, "total_volume": 100, "yesterday_volume": 0},
    ]
    out = compute_sector_members(universe, chain, {}, "半導體業", "IC設計")
    assert out is not None
    assert all(m["vol_ratio"] is None for m in out["members"])
