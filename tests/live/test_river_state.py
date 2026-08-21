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


class TestCloseClampPush:
    """SC-2:收盤 clamp 第 2 分鐘起不覆寫 end 格(13:46– 的殘留取樣蓋掉真收盤)。

    end+1(13:45:xx 的成交,桶 = 13:46)仍**必須**寫得進來 —— base 腿每秒取樣在
    13:44:xx 就先把 end 格填掉了,收盤價只能從這一分鐘進來。
    """

    def test_close_auction_minute_overwrites_end_slot(self) -> None:
        s = _state()
        s.push("TXF", 825, 40_646_000, DAY)  # 13:44:30 的取樣落 13:45 桶
        s.push("TXF", 826, 40_650_000, DAY)  # 13:45:02 收盤撮合
        assert s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"][300] == 40_650_000

    def test_stale_minute_does_not_overwrite_end_slot(self) -> None:
        s = _state()
        s.push("TXF", 825, 40_646_000, DAY)
        s.push("TXF", 826, 40_650_000, DAY)
        s.push("TXF", 829, 40_700_000, DAY)  # 13:48 殘留取樣 → 丟棄
        assert s.snapshot(LABELS, 2)["legs"]["TXF"]["minutes"][300] == 40_650_000

    def test_first_stale_minute_is_already_blocked(self) -> None:
        # rank >= 2 的**下邊界**:13:46 就已經是「收盤後殘留」。門檻若鬆成 rank >= 3,
        # 上面那條(13:48 = rank 4)照樣綠,只有這一分鐘看得出來。
        s = _state()
        s.push("TXF", 825, 40_646_000, DAY)
        s.push("TXF", 826, 40_650_000, DAY)
        s.push("TXF", 827, 40_700_000, DAY)  # 13:46 = clamp rank 2 → 丟棄
        assert s.snapshot(LABELS, 3)["legs"]["TXF"]["minutes"][300] == 40_650_000

    def test_night_close_clamp_uses_the_expanded_scale(self) -> None:
        # 夜盤 end = 05:00,而 05:0x 的 minute-of-day(300–305)全都 < 窗首 900 →
        # 名次與分桶都得吃 `_expand` 的 +1440。少了展開,收盤那幾分鐘整段落窗外被丟掉。
        s = _state()
        s.push("TXF", 1740, 40_600_000, NIGHT)  # 05:00 bar 本身,offset 840
        s.push("TXF", 301, 40_650_000, NIGHT)  # 05:00:xx 收盤撮合(桶 05:01)= rank 1 → 要進得來
        s.push("TXF", 302, 40_700_000, NIGHT)  # 05:01 殘留 = rank 2 → 丟棄
        assert s.snapshot(LABELS, 3)["legs"]["TXF"]["minutes"] == {840: 40_650_000}

    def test_guard_runs_after_the_session_switch(self) -> None:
        # 守門必須在 `set_session` **之後**:換場後新場的 end 格是空的,rank 2 的第一筆
        # 就是它當下最好的近似。順序顛倒的失效樣態 = 拿上一場的 end 格擋掉新場第一筆,
        # 而新場那一格永遠空著(畫面上是「收盤那一分鐘沒有點」,零錯誤訊號)。
        s = _state()
        s.push("TXF", 825, 40_646_000, DAY)
        s.push("ES", 825, 7_400_000, DAY)
        s.push("TXF", 827, 40_900_000, NEXT_DAY)  # 換日 + clamp rank 2
        legs = s.snapshot(LABELS, 2)["legs"]
        assert legs["TXF"]["minutes"] == {300: 40_900_000}
        assert legs["ES"]["minutes"] == {}  # 舊場的點一併清掉

    def test_discarded_push_does_not_become_a_delta_point(self) -> None:
        s = _state()
        s.push("TXF", 826, 40_650_000, DAY)
        s.push("TXF", 829, 40_700_000, DAY)
        assert s.delta(3)["legs"]["TXF"] == {"m": 300, "p": 40_650_000}

    def test_stale_minute_writes_when_end_slot_empty(self) -> None:
        # 13:45 真收盤可能因 tick 稀疏而沒落 end 格 → 13:46 的取樣仍是最佳近似
        s = _state()
        s.push("TXF", 827, 40_700_000, DAY)
        assert s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"] == {300: 40_700_000}
        # clamp 窗最後一分鐘(13:50 = rank 5)同理:名次再大,end 格空著就照寫
        s2 = _state()
        s2.push("ES", 830, 7_400_000, DAY)
        assert s2.snapshot(LABELS, 1)["legs"]["ES"]["minutes"] == {300: 7_400_000}

    def test_non_clamp_minutes_keep_last_write_wins(self) -> None:
        s = _state()
        s.push("TXF", 824, 40_600_000, DAY)  # 13:44 bar,offset 299
        s.push("TXF", 824, 40_610_000, DAY)
        s.push("TXF", 825, 40_646_000, DAY)  # 13:45 bar,offset 300
        s.push("TXF", 825, 40_648_000, DAY)
        minutes = s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"]
        assert minutes == {299: 40_610_000, 300: 40_648_000}


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

    def test_clamp_approximation_blocks_the_real_close_bar(self) -> None:
        """characterization —— **已知留尾(R5)**:end 格一旦被 clamp 近似值佔住,1K 回補
        的真 end bar 就補不進來。`apply_backfill` 只看「這格有沒有值」,分不出裡面是
        13:46 的殘留近似還是 13:45 的真收盤。

        影響有限(差一個殘留分鐘的價),故本輪不改。日後若替 end 格加上 per-leg
        「這是 clamp 近似」旗標讓回補得以覆寫,**本案就該紅** —— 屆時改的是期望值,
        不是把測試刪掉。
        """
        s = _state()
        s.push("TXF", 827, 40_700_000, DAY)  # 13:46 殘留取樣;end 格還空著 → 進得來
        assert s.apply_backfill("TXF", [(825, 40_646_000)], DAY) == 0
        assert s.snapshot(LABELS, 1)["legs"]["TXF"]["minutes"][300] == 40_700_000


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
