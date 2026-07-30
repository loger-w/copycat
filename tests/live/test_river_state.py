"""RiverState 狀態機測試(SC-1:分桶 / 換場清空 / 回補只補空缺 / snapshot & delta 形狀)。"""

from __future__ import annotations

from copycat.live.river_state import RiverState

DAY = ("20260730", "day")
NIGHT = ("20260730", "night")
NEXT_DAY = ("20260731", "day")
LABELS = {"TXF": "台指", "ES": "標普"}


def _state() -> RiverState:
    return RiverState(["TXF", "ES"], base="TXF")


class TestPush:
    def test_same_minute_keeps_last_write(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.push("TXF", 600, 40_650_000, DAY)
        assert s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"] == {75: 40_650_000}

    def test_out_of_window_minute_dropped(self) -> None:
        s = _state()
        s.push("TXF", 525, 40_646_000, DAY)  # 08:45 bar = 開盤前
        s.push("TXF", 900, 40_646_000, DAY)  # 15:00,日盤窗外
        assert s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"] == {}

    def test_unknown_leg_ignored(self) -> None:
        s = _state()
        s.push("NOPE", 600, 1_000, DAY)
        assert "NOPE" not in s.snapshot(LABELS, 1)["legs"]

    def test_session_change_clears_all_legs(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.push("ES", 600, 7_388_000, DAY)
        s.push("TXF", 901, 40_700_000, NIGHT)  # 15:01
        legs = s.snapshot(LABELS, 2)["legs"]
        assert legs["TXF"]["minutes"] == {1: 40_700_000}
        assert legs["ES"]["minutes"] == {}

    def test_utc_date_change_clears(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.push("TXF", 600, 40_800_000, NEXT_DAY)
        assert s.snapshot(LABELS, 2)["legs"]["TXF"]["minutes"] == {75: 40_800_000}


class TestSetSession:
    def test_window_follows_session_without_any_price(self) -> None:
        s = _state()
        s.set_session(NIGHT)
        assert s.snapshot(LABELS, 0)["window"] == {"start_min": 900, "end_min": 1740}

    def test_set_session_clears_previous_session_data(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.set_session(NIGHT)
        assert s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"] == {}


class TestApplyBackfill:
    def test_fills_only_missing_offsets(self) -> None:
        s = _state()
        s.push("ES", 600, 7_400_000, DAY)  # live 值,offset 75
        filled = s.apply_backfill("ES", [(599, 7_380_000), (600, 7_390_000)], DAY)
        minutes = s.snapshot(LABELS, 1)["legs"]["ES"]["minutes"]
        assert filled == 1
        assert minutes[74] == 7_380_000
        assert minutes[75] == 7_400_000  # live 優先,不被回補覆蓋

    def test_out_of_window_rows_skipped(self) -> None:
        s = _state()
        assert s.apply_backfill("ES", [(100, 1_000), (600, 7_390_000)], DAY) == 1

    def test_stale_session_discarded(self) -> None:
        s = _state()
        s.set_session(NIGHT)
        assert s.apply_backfill("ES", [(600, 7_390_000)], DAY) == 0
        assert s.snapshot(LABELS, 1)["legs"]["ES"]["minutes"] == {}

    def test_unknown_leg_returns_zero(self) -> None:
        s = _state()
        assert s.apply_backfill("NOPE", [(600, 1_000)], DAY) == 0


class TestSnapshot:
    def test_shape_and_last_from_largest_offset(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.apply_backfill("TXF", [(700, 40_700_000)], DAY)
        snap = s.snapshot(LABELS, 7)
        assert snap["type"] == "river"
        assert snap["seq"] == 7
        assert snap["session"] == "day"
        assert snap["base"] == "TXF"
        assert snap["window"] == {"start_min": 525, "end_min": 825}
        leg = snap["legs"]["TXF"]
        assert leg["label"] == "台指"
        assert leg["last"] == 40_700_000  # 最大 offset 的值(不是最後寫入的)
        assert leg["last_minute"] == 175

    def test_empty_leg_has_null_last(self) -> None:
        snap = _state().snapshot(LABELS, 0)
        assert snap["legs"]["ES"] == {
            "label": "標普",
            "minutes": {},
            "last": None,
            "last_minute": None,
        }

    def test_label_falls_back_to_key(self) -> None:
        snap = _state().snapshot({}, 0)
        assert snap["legs"]["ES"]["label"] == "ES"


class TestDelta:
    def test_carries_only_most_recent_write_per_leg(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.push("TXF", 601, 40_650_000, DAY)
        d = s.delta(3)
        assert d["type"] == "river_delta"
        assert d["seq"] == 3
        assert d["session"] == "day"
        assert d["window"] == {"start_min": 525, "end_min": 825}
        assert d["legs"]["TXF"] == {"m": 76, "p": 40_650_000}
        assert d["legs"]["ES"] is None

    def test_backfill_does_not_become_a_delta_point(self) -> None:
        s = _state()
        s.apply_backfill("ES", [(600, 7_390_000)], DAY)
        assert s.delta(1)["legs"]["ES"] is None

    def test_all_null_after_session_change(self) -> None:
        s = _state()
        s.push("TXF", 600, 40_646_000, DAY)
        s.set_session(NIGHT)
        assert s.delta(2)["legs"] == {"TXF": None, "ES": None}
