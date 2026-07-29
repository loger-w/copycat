"""corr_config:腿設定與 JSON 覆寫載入(SC-8 商品清單設定檔化)。"""

from __future__ import annotations

import json
from pathlib import Path

from copycat.corr_config import DEFAULT_CONFIG, load_config


class TestDefaultConfig:
    def test_has_six_legs(self) -> None:
        assert len(DEFAULT_CONFIG.legs) == 6

    def test_base_is_txf_and_present_in_legs(self) -> None:
        assert DEFAULT_CONFIG.base == "TXF"
        assert DEFAULT_CONFIG.base in {leg.key for leg in DEFAULT_CONFIG.legs}

    def test_base_leg_reads_from_futures_engine_not_own_subscription(self) -> None:
        """台指腿必須走既有 futures_engine,不可自行訂閱(CLAUDE.md §8 同 symbol 衝突)。"""
        base_leg = next(leg for leg in DEFAULT_CONFIG.legs if leg.key == DEFAULT_CONFIG.base)
        assert base_leg.source == "futures_engine"

    def test_non_base_legs_are_tc4_subscriptions(self) -> None:
        others = [leg for leg in DEFAULT_CONFIG.legs if leg.key != DEFAULT_CONFIG.base]
        assert all(leg.source == "tc4" for leg in others)
        assert len(others) == 5

    def test_windows_and_per_window_min_samples(self) -> None:
        assert DEFAULT_CONFIG.windows == (60, 300, 1800)
        assert DEFAULT_CONFIG.min_samples == {60: 30, 300: 100, 1800: 300}

    def test_legs_carry_traditional_chinese_labels(self) -> None:
        labels = {leg.key: leg.label for leg in DEFAULT_CONFIG.legs}
        assert labels["SXF"] == "費半"
        assert labels["TWN"] == "富台"


class TestLoadConfig:
    def test_missing_file_falls_back_to_default(self, tmp_path: Path) -> None:
        assert load_config(tmp_path / "nope.json") == DEFAULT_CONFIG

    def test_seventh_leg_added_without_engine_change(self, tmp_path: Path) -> None:
        """SC-8:日後 TC4 上架 CME SSF 的 TSM 只需改設定檔。"""
        path = tmp_path / "correlation.json"
        legs = [
            {"key": leg.key, "label": leg.label, "symbol": leg.symbol, "source": leg.source}
            for leg in DEFAULT_CONFIG.legs
        ]
        legs.append(
            {"key": "TSM", "label": "台積電ADR", "symbol": "TC.F.CME.TSM.HOT", "source": "tc4"}
        )
        path.write_text(json.dumps({"base": "TXF", "legs": legs}), encoding="utf-8")

        cfg = load_config(path)

        assert len(cfg.legs) == 7
        assert cfg.legs[-1].key == "TSM"
        assert cfg.legs[-1].symbol == "TC.F.CME.TSM.HOT"

    def test_unknown_fields_are_ignored_not_treated_as_broken(self, tmp_path: Path) -> None:
        """`_comment` 說明欄不得觸發降級(impl review P2)。"""
        path = tmp_path / "correlation.json"
        legs = [
            {"key": "TXF", "label": "台指", "symbol": "TC.F.TWF.TXF.HOT", "source": "futures_engine"},
            {"key": "NQ", "label": "納指", "symbol": "TC.F.CME.NQ.HOT", "source": "tc4"},
        ]
        path.write_text(
            json.dumps({"_comment": "新增腿說明", "base": "TXF", "legs": legs, "_x": 1}),
            encoding="utf-8",
        )

        cfg = load_config(path)

        assert len(cfg.legs) == 2

    def test_malformed_json_falls_back_without_raising(self, tmp_path: Path) -> None:
        path = tmp_path / "correlation.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_config(path) == DEFAULT_CONFIG

    def test_base_absent_from_legs_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / "correlation.json"
        legs = [{"key": "NQ", "label": "納指", "symbol": "TC.F.CME.NQ.HOT", "source": "tc4"}]
        path.write_text(json.dumps({"base": "TXF", "legs": legs}), encoding="utf-8")
        assert load_config(path) == DEFAULT_CONFIG

    def test_leg_missing_required_field_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / "correlation.json"
        path.write_text(json.dumps({"base": "TXF", "legs": [{"key": "TXF"}]}), encoding="utf-8")
        assert load_config(path) == DEFAULT_CONFIG

    def test_empty_legs_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / "correlation.json"
        path.write_text(json.dumps({"base": "TXF", "legs": []}), encoding="utf-8")
        assert load_config(path) == DEFAULT_CONFIG
