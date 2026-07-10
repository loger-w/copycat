"""backfill_tc4 單元測試:時間索引與種子匯入 parity、缺檔偵測、分頁抓取."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from copycat.data.backfill_tc4 import (
    _date_to_utc_window,
    _fetch_1k,
    _find_missing,
    _needs_refetch,
    _tc4_symbol,
)


def _raw_bar(time_utc: str, volume: str = "5") -> dict[str, str]:
    return {
        "Time": time_utc,
        "Open": "10.0",
        "High": "10.1",
        "Low": "9.9",
        "Close": "10.05",
        "Volume": volume,
        "UpVolume": "3",
        "DownVolume": "2",
        "UnchVolume": "0",
        "QryIndex": "",
    }


class _FakeApi:
    """無狀態 fake:qry index "0" 永遠回同一頁,末筆 QryIndex 空 → 結束分頁."""

    def __init__(self, bars: list[dict[str, str]]) -> None:
        self._bars = bars

    def SubHistory(self, *args: Any) -> None:  # noqa: N802 - TC4 API 命名
        return None

    def GetHistory(self, *args: Any) -> dict[str, Any]:  # noqa: N802
        return {"HisData": self._bars if args[-1] == "0" else []}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("copycat.data.backfill_tc4.time.sleep", lambda _s: None)


def test_fetch_0901_bar_maps_to_index_0() -> None:
    bars = _fetch_1k(_FakeApi([_raw_bar("10100")]), "s", "2330", "2026-07-03")
    assert [b.m for b in bars] == [0]  # 09:01 = 索引 0(models.taipei_min 同源)


def test_fetch_1330_close_auction_maps_to_index_269() -> None:
    bars = _fetch_1k(_FakeApi([_raw_bar("53000")]), "s", "2330", "2026-07-03")
    assert [b.m for b in bars] == [269]


def test_fetch_keeps_zero_volume_bars_for_seed_parity() -> None:
    # 種子匯入(parse_raw_bar)保留試撮零量根;backfill 不可自行過濾
    bars = _fetch_1k(
        _FakeApi([_raw_bar("52600", volume="0"), _raw_bar("53000")]),
        "s",
        "2330",
        "2026-07-03",
    )
    assert [b.m for b in bars] == [265, 269]
    assert bars[0].volume == 0.0


def test_fetch_paginates_until_empty_qry_index() -> None:
    page1 = [_raw_bar("10100"), _raw_bar("10200")]
    page1[-1]["QryIndex"] = "2"
    page2 = [_raw_bar("10300")]

    class _Paged(_FakeApi):
        def __init__(self) -> None:
            super().__init__([])
            self._pages = {"0": page1, "2": page2}

        def GetHistory(self, *args: Any) -> dict[str, Any]:  # noqa: N802
            return {"HisData": self._pages.get(args[-1], [])}

    bars = _fetch_1k(_Paged(), "s", "2330", "2026-07-03")
    assert [b.m for b in bars] == [0, 1, 2]


def test_date_to_utc_window() -> None:
    assert _date_to_utc_window("2026-07-03") == ("2026070300", "2026070306")


def test_tc4_symbol_uses_tws_segment() -> None:
    assert _tc4_symbol("2330") == "TC.S.TWS.2330"


def test_needs_refetch_true_for_missing_legacy_and_corrupt(tmp_path: Path) -> None:
    missing = tmp_path / "none.json"
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps([{"m": 0}]), encoding="utf-8")
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"bars": []}), encoding="utf-8")
    assert _needs_refetch(missing)
    assert _needs_refetch(legacy)
    assert _needs_refetch(corrupt)
    assert not _needs_refetch(ok)


def test_find_missing_dedups_and_reads_events(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    events.write_text(
        "stock_id,t1_date\n2330,2026-07-03\n2330,2026-07-03\n1101,2026-07-04\n",
        encoding="utf-8",
    )
    have = tmp_path / "1k" / "1101"
    have.mkdir(parents=True)
    (have / "2026-07-04.json").write_text(json.dumps({"bars": []}), encoding="utf-8")
    assert _find_missing(tmp_path, events) == [("2330", "2026-07-03")]


def test_find_missing_skips_empty_t1_date(tmp_path: Path) -> None:
    # events.csv 對「尚無次一交易日」的事件會留空 t1_date(實際存在 3 筆)
    events = tmp_path / "events.csv"
    events.write_text(
        "stock_id,t1_date\n1435,\n,2026-07-03\n2330,2026-07-03\n",
        encoding="utf-8",
    )
    assert _find_missing(tmp_path, events) == [("2330", "2026-07-03")]


def test_fetch_stops_when_qry_index_does_not_advance() -> None:
    # TC4 若回傳停滯的 QryIndex,不可無限迴圈
    bar = _raw_bar("10100")
    bar["QryIndex"] = "0"  # 永遠指回同一頁

    class _Stuck(_FakeApi):
        def GetHistory(self, *args: Any) -> dict[str, Any]:  # noqa: N802
            return {"HisData": [bar]}

    bars = _fetch_1k(_Stuck([]), "s", "2330", "2026-07-03")
    assert [b.m for b in bars] == [0]
