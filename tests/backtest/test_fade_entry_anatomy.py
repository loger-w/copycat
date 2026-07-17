"""Round 5 §0 進場訊號解剖(fade_entry_anatomy):流向反轉 / CDP 位階對決。

判準凍結出處:docs/superpowers/specs/2026-07-17-fade-round5-entry-anatomy-draft.md。
"""

from __future__ import annotations

import csv
from pathlib import Path

from copycat.backtest.fade_entry_anatomy import (
    cdp_levels,
    flow_flip_anatomy,
    flow_flip_go,
    level_anatomy,
    level_stratified_duel,
)
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.daily import DailyIndex
from copycat.data.models import Bar1K

_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    vol: float = 100,
    up: float = 30,
    dn: float = 70,
) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=vol,
        up_volume=up,
        down_volume=dn,
        unch_volume=0,
    )


def _sample(gap: float = 0.04, t1_date: str = "2026-03-03", date: str = "2026-03-02") -> FadeSample:
    return FadeSample(
        stock_id="2330",
        date=date,
        t1_date=t1_date,
        limit=50.0,  # t1_limit = 55.0
        t1_open=50.0 * (1 + gap),
        gap=gap,
        broker_ids="9227",
    )


# ---------- (a) 流向反轉 ----------


def _attack_then_flip(post_closes: list[float], *, new_high: bool = False) -> list[Bar1K]:
    """4 根外盤攻擊(累計 +1.6% ≥ 1%)→ m4 翻內盤 → 之後照 post_closes 走。"""
    bars = [
        _bar(0, 52.0, 52.2, 51.9, 52.2, up=80, dn=20),
        _bar(1, 52.2, 52.5, 52.1, 52.4, up=80, dn=20),
        _bar(2, 52.4, 52.7, 52.3, 52.6, up=80, dn=20),
        _bar(3, 52.6, 52.9, 52.5, 52.85, up=80, dn=20),
        _bar(4, 52.85, 52.9, 52.4, 52.5, up=20, dn=80),  # 翻轉:dn > up×1.5
    ]
    for i, c in enumerate(post_closes):
        h = max(c + 0.1, 53.5) if (new_high and i == 0) else c + 0.1
        bars.append(_bar(5 + i, c, h, c - 0.1, c, up=50, dn=50))
    return bars


class TestFlowFlipAnatomy:
    def test_detects_flip_after_attack(self) -> None:
        bars = _attack_then_flip([52.0, 51.5, 51.0])  # 翻轉後續跌 → post_move 正
        out = flow_flip_anatomy([(_sample(), bars)])
        sig = out["N3_r1_c1"]
        assert isinstance(sig, dict)
        assert sig["n_days"] == 1
        assert sig["found"] == 1
        first_m = sig["first_m"]
        assert isinstance(first_m, dict) and first_m["p50"] == 4
        post = sig["post_move"]
        assert isinstance(post, dict)
        p50 = post["p50"]
        assert isinstance(p50, float) and p50 > 0
        assert sig["false_rate"] == 0.0

    def test_no_attack_no_signal_but_control_fires(self) -> None:
        # 全日內盤佔優、無攻擊段:訊號組不觸發,對照組(無前置)觸發
        bars = [_bar(m, 52.0, 52.1, 51.9, 52.0, up=20, dn=80) for m in range(20)]
        out = flow_flip_anatomy([(_sample(), bars)])
        sig = out["N3_r1_c1"]
        ctrl = out["ctrl_r1_c1"]
        assert isinstance(sig, dict) and isinstance(ctrl, dict)
        assert sig["found"] == 0
        assert ctrl["found"] == 1

    def test_false_signal_when_new_high_after_flip(self) -> None:
        bars = _attack_then_flip([52.0, 52.5, 52.3], new_high=True)  # 翻轉後創當日新高
        out = flow_flip_anatomy([(_sample(), bars)])
        sig = out["N3_r1_c1"]
        assert isinstance(sig, dict)
        assert sig["found"] == 1
        assert sig["false_rate"] == 1.0

    def test_attack_gain_below_threshold_not_armed(self) -> None:
        # 連續外盤但累計漲幅 < 1% → 不算攻擊段
        bars = [
            _bar(0, 52.0, 52.1, 51.9, 52.05, up=80, dn=20),
            _bar(1, 52.05, 52.15, 52.0, 52.1, up=80, dn=20),
            _bar(2, 52.1, 52.2, 52.05, 52.15, up=80, dn=20),
            _bar(3, 52.15, 52.25, 52.1, 52.2, up=80, dn=20),
            _bar(4, 52.2, 52.25, 51.9, 52.0, up=20, dn=80),
        ]
        out = flow_flip_anatomy([(_sample(), bars)])
        sig = out["N3_r1_c1"]
        assert isinstance(sig, dict)
        assert sig["found"] == 0

    def test_confirm_two_bars(self) -> None:
        # c2:翻轉需連續兩根;單根翻轉後回外盤 → 不觸發
        bars = [
            _bar(0, 52.0, 52.2, 51.9, 52.2, up=80, dn=20),
            _bar(1, 52.2, 52.5, 52.1, 52.4, up=80, dn=20),
            _bar(2, 52.4, 52.7, 52.3, 52.6, up=80, dn=20),
            _bar(3, 52.6, 52.9, 52.5, 52.85, up=80, dn=20),
            _bar(4, 52.85, 52.9, 52.4, 52.5, up=20, dn=80),
            _bar(5, 52.5, 52.6, 52.4, 52.55, up=80, dn=20),  # 回外盤,c2 斷
        ]
        out = flow_flip_anatomy([(_sample(), bars)])
        sig = out["N3_r1_c2"]
        assert isinstance(sig, dict)
        assert sig["found"] == 0

    def test_go_criteria(self) -> None:
        # 凍結判準:post_move p50 > 0 且 false_rate < ctrl × 2/3
        assert flow_flip_go(0.01, 0.2, 0.6) is True
        assert flow_flip_go(0.01, 0.5, 0.6) is False  # 0.5 ≥ 0.4
        assert flow_flip_go(-0.01, 0.2, 0.6) is False
        assert flow_flip_go(None, 0.2, 0.6) is False
        assert flow_flip_go(0.01, 0.2, None) is False


# ---------- (c) CDP / 位階 ----------


class TestCdpLevels:
    def test_arithmetic(self) -> None:
        lv = cdp_levels(105.0, 95.0, 100.0)
        assert lv["cdp"] == 100.0
        assert lv["ah"] == 110.0
        assert lv["nh"] == 105.0
        assert lv["nl"] == 95.0
        assert lv["al"] == 90.0


def _write_daily(tmp_path: Path, rows: list[dict[str, str]]) -> DailyIndex:
    daily = tmp_path / "daily"
    events = tmp_path / "events"
    daily.mkdir(exist_ok=True)
    events.mkdir(exist_ok=True)
    with (daily / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with (events / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
    return DailyIndex.load(tmp_path)


def _drow(
    date: str, o: float, h: float, lo: float, c: float, stock_id: str = "2330"
) -> dict[str, str]:
    return {
        "stock_id": stock_id,
        "date": date,
        "open": str(o),
        "high": str(h),
        "low": str(lo),
        "close": str(c),
        "spread": "0.0",
        "volume_lots": "100.0",
    }


class TestLevelAnatomy:
    def test_one_price_day_width_zero_drops_cdp(self, tmp_path: Path) -> None:
        # T 日一價到底(H=L)→ CDP 五線全擠 → 線距中位 0 < 2% → CDP 出局
        daily = _write_daily(tmp_path, [_drow("2026-03-02", 50.0, 50.0, 50.0, 50.0)])
        bars = [_bar(m, 52.0, 52.5, 51.8, 52.0) for m in range(30)]
        out = level_anatomy([(_sample(), bars)], daily)
        width = out["cdp_width"]
        assert isinstance(width, dict)
        assert width["median"] == 0.0
        assert out["cdp_drop"] is True

    def test_wide_day_keeps_cdp(self, tmp_path: Path) -> None:
        # T 日 H−L = 4/50 = 8% → 線距 (AH−AL)/前收 = 2×8% = 16% ≥ 2% → 不出局
        daily = _write_daily(tmp_path, [_drow("2026-03-02", 46.5, 50.0, 46.0, 50.0)])
        bars = [_bar(m, 52.0, 52.5, 51.8, 52.0) for m in range(30)]
        out = level_anatomy([(_sample(), bars)], daily)
        assert out["cdp_drop"] is False

    def test_line_trigger_and_applicability(self, tmp_path: Path) -> None:
        # T 日:H=50, L=46, C=50 → CDP=49, NH=52, AH=53(NL=48/AL=45 低於開盤 52 不適用)
        daily = _write_daily(tmp_path, [_drow("2026-03-02", 46.5, 50.0, 46.0, 50.0)])
        # 當日高 52.1 貼 NH=52(|52.1−52|/52 ≈ 0.19% ≤ 0.5%)後回落
        bars = [_bar(0, 52.0, 52.1, 51.9, 52.0)]
        bars += [_bar(m, 52.0, 52.0, 51.0, 51.2) for m in range(1, 30)]
        out = level_anatomy([(_sample(), bars)], daily)
        lines = out["lines"]
        assert isinstance(lines, dict)
        nh = lines["nh"]
        nl = lines["nl"]
        assert isinstance(nh, dict) and isinstance(nl, dict)
        assert nh["applicable"] == 1
        assert nh["trigger"] == 1
        assert nl["applicable"] == 0  # NL=48 < 開盤 52 → 非壓力位
        ma5 = lines["ma5"]
        assert isinstance(ma5, dict)
        assert ma5["applicable"] == 0  # 只有一天日線 → MA5 不可得

    def test_stratified_duel_pass_when_near_falls_harder(self, tmp_path: Path) -> None:
        # 兩個拉幅層,層內「貼線局」回落一致深於「不貼局」→ 方向 2/2 + z 過門檻
        # T 日:H=50,L=46,C=50 → NH=52、AH=53
        rows = [_drow("2026-03-02", 46.5, 50.0, 46.0, 50.0)]
        daily = _write_daily(tmp_path, rows)
        uni = []
        day = 3

        def _day(open_: float, high: float, close: float) -> None:
            nonlocal day
            s = FadeSample(
                stock_id="2330",
                date="2026-03-02",
                t1_date=f"2026-03-{day:02d}",
                limit=50.0,
                t1_open=open_,
                gap=open_ / 50.0 - 1.0,
                broker_ids="9227",
            )
            bars = [_bar(0, open_, high, open_ - 0.1, open_)]
            bars += [_bar(m, close, close + 0.05, close - 0.05, close) for m in range(1, 10)]
            uni.append((s, bars))
            day += 1

        # 層 2~4%(open 50.5):貼 NH=52 的局重摔、不貼的小回
        for _ in range(3):
            _day(50.5, 52.0, 48.5)  # pull 2.97%,|高−NH|=0 貼線,回落 6.7%
            _day(50.5, 51.6, 51.3)  # pull 2.18%,距 NH 0.77% 不貼,回落 0.6%
        # 層 4~6%(open 49.8)
        for _ in range(3):
            _day(49.8, 52.0, 48.6)  # pull 4.4%,貼 NH,回落 6.5%
            _day(49.8, 52.6, 52.2)  # pull 5.6%,距 NH 1.15%/AH 0.75% 不貼,回落 0.8%

        out = level_stratified_duel(uni, daily)
        assert isinstance(out["z"], float)
        cl = out["consistent_layers"]
        assert isinstance(cl, int) and cl >= 2
        assert out["pass"] is True

    def test_stratified_duel_fail_when_reversed(self, tmp_path: Path) -> None:
        rows = [_drow("2026-03-02", 46.5, 50.0, 46.0, 50.0)]
        daily = _write_daily(tmp_path, rows)
        uni = []
        day = 3

        def _day(open_: float, high: float, close: float) -> None:
            nonlocal day
            s = FadeSample(
                stock_id="2330",
                date="2026-03-02",
                t1_date=f"2026-03-{day:02d}",
                limit=50.0,
                t1_open=open_,
                gap=open_ / 50.0 - 1.0,
                broker_ids="9227",
            )
            bars = [_bar(0, open_, high, open_ - 0.1, open_)]
            bars += [_bar(m, close, close + 0.05, close - 0.05, close) for m in range(1, 10)]
            uni.append((s, bars))
            day += 1

        # 方向反轉:貼線的局反而不跌
        for _ in range(3):
            _day(50.5, 52.0, 51.9)  # 貼 NH,幾乎不回
            _day(49.8, 52.6, 49.0)  # 不貼,重摔
        out = level_stratified_duel(uni, daily)
        assert out["pass"] is False

    def test_duel_groups_present(self, tmp_path: Path) -> None:
        daily = _write_daily(tmp_path, [_drow("2026-03-02", 46.5, 50.0, 46.0, 50.0)])
        bars = [_bar(0, 52.0, 52.1, 51.9, 52.0)]
        bars += [_bar(m, 52.0, 52.0, 51.0, 51.2) for m in range(1, 30)]
        out = level_anatomy([(_sample(), bars)], daily)
        duel = out["duel"]
        assert isinstance(duel, dict)
        assert "near_level_only" in duel
        assert "neither" in duel
        assert "z" in duel
        assert "go" in duel
