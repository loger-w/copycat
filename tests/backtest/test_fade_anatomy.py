"""§0 前置統計(fade_anatomy):flush / 墊高 / 內盤比 gate / 緩漲 / MFE(change-spec §5.5)."""

from __future__ import annotations

from copycat.backtest.fade_anatomy import (
    flush_anatomy,
    hl_anatomy,
    inner_gate_anatomy,
    mfe_anatomy,
    slow_rally_anatomy,
    tp_hl_demote,
)
from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K

_CFG = FadeBacktestConfig(struct_stop_buffers=(0.025,))


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


def _sample(gap: float = 0.04, t1_date: str = "2026-03-02") -> FadeSample:
    return FadeSample(
        stock_id="2330",
        date="2026-03-01",
        t1_date=t1_date,
        limit=50.0,  # t1_limit = 55.0
        t1_open=50.0 * (1 + gap),
        gap=gap,
        broker_ids="9227",
    )


class TestFlushAnatomy:
    def test_detects_first_flush(self) -> None:
        bars = [_bar(m, 52.0, 52.1, 51.8, 52.0) for m in range(6)]
        # m6:量爆 5x + 進場後新低 51.0
        bars.append(_bar(6, 52.0, 52.0, 51.0, 51.6, vol=500))
        bars += [_bar(m, 51.6, 51.7, 51.4, 51.5) for m in range(7, 12)]
        out = flush_anatomy([(_sample(), bars)], _CFG)
        z3 = out["z3"]
        assert isinstance(z3, dict)
        assert z3["n_days"] == 1
        assert z3["found"] == 1
        first_m = z3["first_m"]
        assert isinstance(first_m, dict)
        assert first_m["p50"] == 6

    def test_no_flush_flat_day(self) -> None:
        bars = [_bar(m, 52.0, 52.1, 51.8, 52.0) for m in range(20)]
        out = flush_anatomy([(_sample(), bars)], _CFG)
        z3 = out["z3"]
        assert isinstance(z3, dict)
        assert z3["found"] == 0


class TestHlAnatomy:
    def test_giveback_positive_when_confirm_above_low(self) -> None:
        # 結構:L1=50.5 → 反彈 → L2=50.6(墊高)+ 高點遞增 → 確認點 close 高於前低
        bars = [
            _bar(0, 52.0, 52.2, 51.8, 52.0),
            _bar(1, 51.9, 52.6, 51.5, 51.7),
            _bar(2, 51.7, 51.9, 50.8, 51.0),
            _bar(3, 51.0, 51.2, 50.5, 50.9),
            _bar(4, 50.9, 51.1, 50.7, 50.9),
            _bar(5, 50.9, 53.2, 50.8, 53.0),
            _bar(6, 53.0, 53.1, 50.6, 50.8),
            _bar(7, 51.0, 53.4, 50.9, 51.2),
            _bar(8, 52.0, 52.2, 50.4, 51.0),
            _bar(9, 51.0, 51.1, 50.8, 50.9),
        ]
        out = hl_anatomy([(_sample(), bars)], _CFG, ks=(1,))
        k1 = out["k1"]
        assert isinstance(k1, dict)
        blk = k1["base_arm"]
        assert isinstance(blk, dict)
        assert blk["found"] == 1
        giveback = blk["giveback"]
        assert isinstance(giveback, dict)
        p50 = giveback["p50"]
        assert isinstance(p50, float)
        assert p50 > 0  # 確認價必然高於確認前最低(讓肉為正)

    def test_demote_rule(self) -> None:
        assert tp_hl_demote(hl_giveback_p50=0.02, hold_giveback_p50=0.01) is True
        assert tp_hl_demote(hl_giveback_p50=0.005, hold_giveback_p50=0.01) is False
        assert tp_hl_demote(hl_giveback_p50=None, hold_giveback_p50=0.01) is True


class TestInnerGate:
    def _day(self, dn_ratio: float, touch: bool) -> list[Bar1K]:
        dn = 100.0 * dn_ratio
        up = 100.0 - dn
        bars = [_bar(m, 52.0, 52.1, 51.8, 52.0, up=up, dn=dn) for m in range(15)]
        if touch:
            bars.append(_bar(15, 52.0, 54.6, 51.9, 54.5))  # ≥ 55×0.99=54.45
        bars += [_bar(m, 52.0, 52.1, 51.9, 52.0) for m in range(16, 30)]
        return bars

    def test_pass_when_high_inner_low_touch(self) -> None:
        uni = []
        # 高內盤(賣壓在)不摸板 ×4;低內盤摸板 ×4 → 方向 = 全池證據一致 → PASS
        for i in range(4):
            uni.append((_sample(t1_date=f"2026-03-0{i + 2}"), self._day(0.70, touch=False)))
            uni.append((_sample(t1_date=f"2026-03-0{i + 2}"), self._day(0.30, touch=True)))
        out = inner_gate_anatomy(uni, _CFG)
        assert out["pass"] is True
        combined = out["combined"]
        assert isinstance(combined, dict)
        gt = combined["gt_0.55"]
        lt = combined["lt_0.45"]
        assert isinstance(gt, dict) and isinstance(lt, dict)
        gt_rate = gt["touch_rate"]
        lt_rate = lt["touch_rate"]
        assert isinstance(gt_rate, float) and isinstance(lt_rate, float)
        assert gt_rate < lt_rate

    def test_fail_when_direction_reversed(self) -> None:
        uni = []
        for i in range(4):
            uni.append((_sample(t1_date=f"2026-03-0{i + 2}"), self._day(0.70, touch=True)))
            uni.append((_sample(t1_date=f"2026-03-0{i + 2}"), self._day(0.30, touch=False)))
        out = inner_gate_anatomy(uni, _CFG)
        assert out["pass"] is False


class TestSlowRally:
    def test_detects_slow_segment(self) -> None:
        bars = []
        price = 50.0
        for m in range(12):  # 12 根緩漲(每根 +0.1% ≤ 0.3%)
            new_price = round(price * 1.001, 3)
            bars.append(_bar(m, price, new_price, price, new_price))
            price = new_price
        bars += [_bar(m, price, price, price * 0.97, price * 0.98) for m in range(12, 24)]
        out = slow_rally_anatomy([(_sample(), bars)])
        assert out["days_with_segment"] == 1

    def test_sharp_rally_not_slow(self) -> None:
        bars = []
        price = 50.0
        for m in range(12):  # 每根 +1% > 0.3% → 不算緩漲
            new_price = round(price * 1.01, 3)
            bars.append(_bar(m, price, new_price, price, new_price))
            price = new_price
        out = slow_rally_anatomy([(_sample(), bars)])
        assert out["days_with_segment"] == 0


class TestMfeAnatomy:
    def test_closeout_mfe_and_giveback(self) -> None:
        bars = [_bar(0, 52.0, 52.1, 51.8, 52.0)]
        bars += [_bar(m, 52.0, 52.1, 51.8, 52.0) for m in range(1, 7)]
        bars.append(_bar(7, 52.0, 52.1, 50.0, 51.0))  # 盤中最低 50.0
        bars.append(_bar(8, 51.0, 51.6, 50.9, 51.5))  # 收盤 51.5(讓回)
        out = mfe_anatomy({"main": [(_sample(), bars)]}, _CFG, frozenset({"9227"}))
        blk = out["base_arm"]
        assert isinstance(blk, dict)
        assert blk["n"] == 1
        mfe = blk["mfe"]
        giveback = blk["giveback_closeout"]
        assert isinstance(mfe, dict) and isinstance(giveback, dict)
        mfe_p50 = mfe["p50"]
        gb_p50 = giveback["p50"]
        assert isinstance(mfe_p50, float) and mfe_p50 > 0
        assert isinstance(gb_p50, float) and gb_p50 > 0
