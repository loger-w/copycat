from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.stock_watchlist import (
    WATCHLIST_LIMIT,
    WatchlistError,
    load_watchlist_groups,
    save_watchlist_groups,
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


class TestGroupsPersistence:
    """groups schema v2(stock-ui-upgrade SC-6);舊 list persistence 測試隨 API 替換遷移."""

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "watchlist.json"
        groups = [
            {"name": "主力", "codes": ["2330", "5483"]},
            {"name": "觀察", "codes": ["2330", "3231"]},
        ]
        save_watchlist_groups(path, groups)
        assert load_watchlist_groups(path) == groups

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_watchlist_groups(tmp_path / "nope.json") == []

    def test_v1_file_migrates_to_single_group(self, tmp_path: Path) -> None:
        path = tmp_path / "w.json"
        path.write_text(
            json.dumps({"_cache_version": 1, "codes": ["2330", "5483"]}), encoding="utf-8"
        )
        assert load_watchlist_groups(path) == [{"name": "自選", "codes": ["2330", "5483"]}]

    def test_saved_file_is_v2(self, tmp_path: Path) -> None:
        path = tmp_path / "w.json"
        save_watchlist_groups(path, [{"name": "自選", "codes": ["2330"]}])
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 2
        assert payload["groups"] == [{"name": "自選", "codes": ["2330"]}]

    def test_union_over_limit_rejected(self, tmp_path: Path) -> None:
        half = WATCHLIST_LIMIT // 2 + 1
        groups = [
            {"name": "a", "codes": [f"{1000 + i}" for i in range(half)]},
            {"name": "b", "codes": [f"{2000 + i}" for i in range(half)]},
        ]
        with pytest.raises(WatchlistError, match="WATCHLIST_FULL"):
            save_watchlist_groups(tmp_path / "w.json", groups)

    def test_shared_code_counts_once_toward_limit(self, tmp_path: Path) -> None:
        codes = [f"{1000 + i}" for i in range(WATCHLIST_LIMIT)]
        groups = [{"name": "a", "codes": codes}, {"name": "b", "codes": codes[:5]}]
        saved = save_watchlist_groups(tmp_path / "w.json", groups)
        assert len(union(saved)) == WATCHLIST_LIMIT

    def test_bad_code_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="BAD_CODE"):
            save_watchlist_groups(tmp_path / "w.json", [{"name": "a", "codes": ["bad code"]}])

    def test_bad_group_name_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            save_watchlist_groups(tmp_path / "w.json", [{"name": "  ", "codes": ["2330"]}])
        with pytest.raises(WatchlistError, match="BAD_GROUP"):
            save_watchlist_groups(
                tmp_path / "w.json",
                [{"name": "a", "codes": ["2330"]}, {"name": "a", "codes": ["5483"]}],
            )

    def test_codes_deduped_within_group_keeping_order(self, tmp_path: Path) -> None:
        path = tmp_path / "w.json"
        saved = save_watchlist_groups(path, [{"name": "a", "codes": ["2330", "5483", "2330"]}])
        assert saved == [{"name": "a", "codes": ["2330", "5483"]}]


class TestUnion:
    def test_union_keeps_first_seen_order(self) -> None:
        groups = [
            {"name": "a", "codes": ["2330", "5483"]},
            {"name": "b", "codes": ["3231", "2330"]},
        ]
        assert union(groups) == ["2330", "5483", "3231"]

    def test_union_empty(self) -> None:
        assert union([]) == []
