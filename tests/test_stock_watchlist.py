from __future__ import annotations

from pathlib import Path

import pytest

from copycat.stock_watchlist import (
    WATCHLIST_LIMIT,
    WatchlistError,
    load_watchlist,
    save_watchlist,
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


class TestPersistence:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "watchlist.json"
        save_watchlist(path, ["2330", "5483"])
        assert load_watchlist(path) == ["2330", "5483"]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_watchlist(tmp_path / "nope.json") == []

    def test_over_limit_rejected(self, tmp_path: Path) -> None:
        codes = [f"{1000 + i}" for i in range(WATCHLIST_LIMIT + 1)]
        with pytest.raises(WatchlistError, match="WATCHLIST_FULL"):
            save_watchlist(tmp_path / "w.json", codes)

    def test_bad_code_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="BAD_CODE"):
            save_watchlist(tmp_path / "w.json", ["2330", "bad code"])

    def test_duplicates_deduped_keeping_order(self, tmp_path: Path) -> None:
        path = tmp_path / "w.json"
        save_watchlist(path, ["2330", "5483", "2330"])
        assert load_watchlist(path) == ["2330", "5483"]
