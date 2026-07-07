from __future__ import annotations

from pathlib import Path

import pytest

from copycat.data.models import Bar1K
from copycat.data.store import bars_path, read_bars, write_bars


def _bar(m: int, px: float = 10.0, v: float = 100.0) -> Bar1K:
    return Bar1K(
        m=m,
        open=px,
        high=px,
        low=px,
        close=px,
        volume=v,
        up_volume=v,
        down_volume=0.0,
        unch_volume=0.0,
    )


def test_roundtrip(tmp_path: Path) -> None:
    bars = [_bar(0), _bar(1, px=10.5)]
    write_bars(tmp_path, "2330", "2026-07-03", bars)
    assert read_bars(tmp_path, "2330", "2026-07-03") == bars


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_bars(tmp_path, "9999", "2026-01-01") is None


def test_write_rejects_unsorted(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_bars(tmp_path, "2330", "2026-07-03", [_bar(5), _bar(3)])


def test_path_layout(tmp_path: Path) -> None:
    assert bars_path(tmp_path, "2330", "2026-07-03") == tmp_path / "1k" / "2330" / "2026-07-03.json"
