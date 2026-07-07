from __future__ import annotations

import pytest

from copycat.data.models import Bar1K, fmt_min, parse_raw_bar, taipei_min


def test_taipei_min_first_bar() -> None:
    # UTC 01:01 = 台北 09:01 = 索引 0
    assert taipei_min("10100") == 0


def test_taipei_min_last_bar() -> None:
    # UTC 05:30 = 台北 13:30 收盤競價根 = 索引 269
    assert taipei_min("53000") == 269


def test_taipei_min_mid() -> None:
    # UTC 02:00 = 台北 10:00 = 索引 59
    assert taipei_min("20000") == 59


def test_fmt_min_roundtrip() -> None:
    assert fmt_min(0) == "09:01"
    assert fmt_min(59) == "10:00"
    assert fmt_min(269) == "13:30"


def test_parse_raw_bar() -> None:
    raw = {
        "Time": "10100",
        "Open": "30.05",
        "High": "30.7",
        "Low": "30",
        "Close": "30.6",
        "Volume": "1936",
        "UpTick": "101",
        "UpVolume": "1792",
        "DownTick": "49",
        "DownVolume": "144",
        "UnchVolume": "0",
    }
    bar = parse_raw_bar(raw)
    assert bar == Bar1K(
        m=0,
        open=30.05,
        high=30.7,
        low=30.0,
        close=30.6,
        volume=1936.0,
        up_volume=1792.0,
        down_volume=144.0,
        unch_volume=0.0,
    )


def test_parse_raw_bar_empty_volume_is_zero() -> None:
    raw = {
        "Time": "10100",
        "Open": "30",
        "High": "30",
        "Low": "30",
        "Close": "30",
        "Volume": "",
        "UpTick": "0",
        "UpVolume": "",
        "DownTick": "0",
        "DownVolume": "",
        "UnchVolume": "",
    }
    bar = parse_raw_bar(raw)
    assert bar.volume == 0.0 and bar.up_volume == 0.0


def test_parse_raw_bar_missing_field_raises() -> None:
    with pytest.raises(ValueError):
        parse_raw_bar({"Time": "10100"})
