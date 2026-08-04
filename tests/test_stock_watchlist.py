from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.stock_watchlist import (
    WATCHLIST_LIMIT,
    Group,
    Watchlist,
    WatchlistError,
    load_watchlist,
    normalize,
    save_watchlist,
    union,
    validate_code,
)


class TestValidateCode:
    def test_plain_and_etf_suffix_codes(self) -> None:
        assert validate_code("2330") is True
        assert validate_code("5483") is True
        assert validate_code("00637L") is True  # 字母尾碼 ETF(design r1-F6)
        assert validate_code("911616") is True

    def test_bad_codes(self) -> None:
        assert validate_code("") is False
        assert validate_code("233") is False  # 少於 4 位
        assert validate_code("ABCDEF") is False  # 無數字
        assert validate_code("23 30") is False
        assert validate_code("1234567") is False  # 超過 6 位


class TestWatchlistPersistence:
    """schema v3(stock-ui-round5 §🔴-4):codes(全體 = 訂閱池)+ groups(成員關係)."""

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "watchlist.json"
        wl: Watchlist = {
            "codes": ["2330", "5483", "3231"],
            "groups": [
                {"name": "主力", "codes": ["2330", "5483"]},
                {"name": "觀察", "codes": ["2330", "3231"]},
            ],
        }
        save_watchlist(path, wl)
        assert load_watchlist(path) == wl

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_watchlist(tmp_path / "nope.json") == {"codes": [], "groups": []}

    def test_v1_file_migrates_to_ungrouped(self, tmp_path: Path) -> None:
        """v1 從來沒有群組概念 → codes 原樣落未分組,不再包成假的「自選」組(🔴 行為改)."""
        path = tmp_path / "w.json"
        path.write_text(
            json.dumps({"_cache_version": 1, "codes": ["2330", "5483"]}), encoding="utf-8"
        )
        assert load_watchlist(path) == {"codes": ["2330", "5483"], "groups": []}

    def test_v2_file_migrates_codes_from_union(self, tmp_path: Path) -> None:
        """v2(有 groups 無 codes)→ codes = 聯集,畫面零差異(SC-17)."""
        path = tmp_path / "w.json"
        path.write_text(
            json.dumps(
                {
                    "_cache_version": 2,
                    "groups": [{"name": "主力", "codes": ["2330", "5483"]}],
                }
            ),
            encoding="utf-8",
        )
        wl = load_watchlist(path)
        assert wl == {
            "codes": ["2330", "5483"],
            "groups": [{"name": "主力", "codes": ["2330", "5483"]}],
        }

    def test_saved_file_is_v3(self, tmp_path: Path) -> None:
        path = tmp_path / "w.json"
        save_watchlist(path, {"codes": ["2330"], "groups": [{"name": "自選", "codes": ["2330"]}]})
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 3
        assert payload["codes"] == ["2330"]
        assert payload["groups"] == [{"name": "自選", "codes": ["2330"]}]

    def test_union_over_limit_rejected(self, tmp_path: Path) -> None:
        half = WATCHLIST_LIMIT // 2 + 1
        groups: list[Group] = [
            {"name": "a", "codes": [f"{1000 + i}" for i in range(half)]},
            {"name": "b", "codes": [f"{2000 + i}" for i in range(half)]},
        ]
        with pytest.raises(WatchlistError, match="WATCHLIST_FULL"):
            save_watchlist(tmp_path / "w.json", {"codes": [], "groups": groups})

    def test_ungrouped_codes_count_toward_limit(self, tmp_path: Path) -> None:
        """上限以 codes 計 —— 未分組的股票同樣佔額度."""
        codes = [f"{1000 + i}" for i in range(WATCHLIST_LIMIT + 1)]
        with pytest.raises(WatchlistError, match="WATCHLIST_FULL"):
            save_watchlist(tmp_path / "w.json", {"codes": codes, "groups": []})

    def test_shared_code_counts_once_toward_limit(self, tmp_path: Path) -> None:
        codes = [f"{1000 + i}" for i in range(WATCHLIST_LIMIT)]
        groups: list[Group] = [{"name": "a", "codes": codes}, {"name": "b", "codes": codes[:5]}]
        saved = save_watchlist(tmp_path / "w.json", {"codes": codes, "groups": groups})
        assert len(saved["codes"]) == WATCHLIST_LIMIT

    def test_bad_code_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="BAD_CODE"):
            save_watchlist(
                tmp_path / "w.json",
                {"codes": ["bad code"], "groups": [{"name": "a", "codes": ["bad code"]}]},
            )

    def test_bad_code_in_codes_only_rejected(self, tmp_path: Path) -> None:
        """未分組的 code 一樣要驗(它也會進訂閱池)."""
        with pytest.raises(WatchlistError, match="BAD_CODE"):
            save_watchlist(tmp_path / "w.json", {"codes": ["bad code"], "groups": []})

    def test_bad_group_name_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            save_watchlist(
                tmp_path / "w.json", {"codes": ["2330"], "groups": [{"name": "  ", "codes": ["2330"]}]}
            )
        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            save_watchlist(
                tmp_path / "w.json",
                {
                    "codes": ["2330", "5483"],
                    "groups": [
                        {"name": "a", "codes": ["2330"]},
                        {"name": "a", "codes": ["5483"]},
                    ],
                },
            )

    def test_codes_deduped_within_group_keeping_order(self, tmp_path: Path) -> None:
        path = tmp_path / "w.json"
        saved = save_watchlist(
            path,
            {"codes": ["2330", "5483"], "groups": [{"name": "a", "codes": ["2330", "5483", "2330"]}]},
        )
        assert saved["groups"] == [{"name": "a", "codes": ["2330", "5483"]}]

    def test_top_level_codes_deduped_keeping_order(self, tmp_path: Path) -> None:
        saved = save_watchlist(
            tmp_path / "w.json", {"codes": ["2330", "5483", "2330"], "groups": []}
        )
        assert saved["codes"] == ["2330", "5483"]

    def test_group_code_missing_from_codes_appended_to_tail(self, tmp_path: Path) -> None:
        """「加進群組」蘊含「加進自選」——正規化補進 codes 尾端,不報錯."""
        saved = save_watchlist(
            tmp_path / "w.json",
            {"codes": ["2330"], "groups": [{"name": "a", "codes": ["5483", "3231"]}]},
        )
        assert saved["codes"] == ["2330", "5483", "3231"]


class TestNormalize:
    """純函數版正規化(save_watchlist 內部同一份;零寫早退的比較基準)."""

    def test_idempotent(self) -> None:
        wl: Watchlist = {
            "codes": ["2330", "2330"],
            "groups": [{"name": " 主力 ", "codes": ["5483", "5483", "3231"]}],
        }
        once = normalize(wl)
        assert once == {
            "codes": ["2330", "5483", "3231"],
            "groups": [{"name": "主力", "codes": ["5483", "3231"]}],
        }
        assert normalize(once) == once

    def test_group_members_appended_to_codes(self) -> None:
        assert normalize({"codes": [], "groups": [{"name": "a", "codes": ["2330"]}]})["codes"] == [
            "2330"
        ]

    def test_rejects_bad_input_without_touching_disk(self) -> None:
        with pytest.raises(WatchlistError, match="BAD_CODE"):
            normalize({"codes": ["bad code"], "groups": []})
        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            normalize({"codes": [], "groups": [{"name": " ", "codes": []}]})
        with pytest.raises(WatchlistError, match="WATCHLIST_FULL"):
            normalize({"codes": [f"{1000 + i}" for i in range(WATCHLIST_LIMIT + 1)], "groups": []})

    def test_matches_save_watchlist_result(self, tmp_path: Path) -> None:
        wl: Watchlist = {
            "codes": ["2330"],
            "groups": [{"name": "a", "codes": ["5483", "2330"]}],
        }
        assert normalize(wl) == save_watchlist(tmp_path / "w.json", wl)


class TestUnion:
    def test_union_keeps_first_seen_order(self) -> None:
        groups: list[Group] = [
            {"name": "a", "codes": ["2330", "5483"]},
            {"name": "b", "codes": ["3231", "2330"]},
        ]
        assert union(groups) == ["2330", "5483", "3231"]

    def test_union_empty(self) -> None:
        assert union([]) == []
