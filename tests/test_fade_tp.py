"""Phase B TP 機制測試(config + 模擬器)."""

from __future__ import annotations

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    FadeTakeProfitCombo,
    enumerate_tp_combos,
)


class TestTpConfig:
    def test_enumerate_tp_combos_count(self) -> None:
        cfg = FadeBacktestConfig.default()
        combos = enumerate_tp_combos(cfg)
        expected = (
            1  # None
            + 9  # S5
            + 6 * 6 * 5 * 5  # TP1 = 900
            + 4 * 3 * 4 * 5 * 3  # TP2 = 720
            + 5 * 5 * 4  # TP3 = 100
            + 9 * 5  # TP4 = 45
            + 8  # TP5
            + 8  # TP6
            + 6  # TP7
            + 5 * 6 * 3  # TP8 = 90
            + 4  # TP9
            + 4 * 4  # TP10 = 16
            + 5 * 4  # TP11 = 20
        )
        assert len(combos) == expected

    def test_tp_combo_id_unique(self) -> None:
        cfg = FadeBacktestConfig.default()
        combos = enumerate_tp_combos(cfg)
        ids = [c.tp_id for c in combos]
        assert len(ids) == len(set(ids))

    def test_tp_combo_none(self) -> None:
        combo = FadeTakeProfitCombo(None, ())
        assert combo.tp_id == "tp=None"
        assert combo.tp_type is None

    def test_tp_combo_get(self) -> None:
        combo = FadeTakeProfitCombo("tp1", (("min_profit", 0.005), ("z", 2.0)))
        assert combo.get("z") == 2.0
        assert combo.get("min_profit") == 0.005
