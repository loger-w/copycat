"""corr_config:腿設定與 JSON 覆寫載入(SC-8 商品清單設定檔化)。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from copycat.corr_config import CONFIG_PATH, DEFAULT_CONFIG, load_config


#: 腿的**逐字**契約(key / label / symbol / source),順序 = `configs/correlation.json`。
#: 順序本身是契約:江波圖顏色依腿**序位**指派(`river-colors.ts`),插腿會整組換色。
_EXPECTED_LEGS: tuple[tuple[str, str, str, str], ...] = (
    ("TXF", "台指", "TC.F.TWF.TXF.HOT", "futures_engine"),
    ("TWN", "富台", "TC.F.SGX.TWN.HOT", "tc4"),
    ("YM", "道瓊", "TC.F.CBOT.YM.HOT", "tc4"),
    ("ES", "標普", "TC.F.CME.ES.HOT", "tc4"),
    ("NQ", "納指", "TC.F.CME.NQ.HOT", "tc4"),
    ("SXF", "費半", "TC.F.TWF.SXF.HOT", "tc4"),
    ("NK225M", "小日經", "TC.F.OSE.NK225M.HOT", "tc4"),
    ("VX", "VIX", "TC.F.CFE.VX.HOT", "tc4"),
    ("CL", "原油", "TC.F.CME.CL.HOT", "tc4"),
    ("GC", "黃金", "TC.F.CME.GC.HOT", "tc4"),
    ("TSMC", "台積電", "TC.S.TWS.2330", "tc4"),
)


class TestDefaultConfig:
    def test_has_eleven_legs_matching_the_repo_config(self) -> None:
        """N021:預設腿必須與 `configs/correlation.json` 同一組。

        缺一腿的失效樣態不是「少一條線」而已 —— 設定檔壞掉時 `load_config` 降級回
        DEFAULT_CONFIG,江波圖 / 相關係數會**真的少一腿**,而畫面上沒有任何錯誤訊號。
        """
        assert len(DEFAULT_CONFIG.legs) == 11
        assert [leg.key for leg in DEFAULT_CONFIG.legs] == [key for key, *_rest in _EXPECTED_LEGS]

    def test_only_sxf_is_sparse_and_the_repo_file_agrees(self) -> None:
        """SXF 費半日盤 94.4% 時間沒成交(tc4-market-facts),R2 240 s 對它是假警報。
        DEFAULT_CONFIG 與 configs/correlation.json 的 sparse 集合要一致 —— 設定檔壞掉降級到
        預設腿時,豁免不能悄悄消失或多出來。"""
        assert {leg.key for leg in DEFAULT_CONFIG.legs if leg.sparse} == {"SXF"}
        repo = load_config(CONFIG_PATH)
        assert {leg.key for leg in repo.legs if leg.sparse} == {"SXF"}

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
        assert len(others) == 10

    def test_windows_and_per_window_min_samples(self) -> None:
        assert DEFAULT_CONFIG.windows == (60, 300, 1800)
        assert DEFAULT_CONFIG.min_samples == {60: 30, 300: 100, 1800: 300}

    def test_legs_carry_traditional_chinese_labels(self) -> None:
        labels = {leg.key: leg.label for leg in DEFAULT_CONFIG.legs}
        assert labels["SXF"] == "費半"
        assert labels["TWN"] == "富台"
        # 2026-08-26 F4 四腿:VIX 是專有名詞維持原文,其餘一律繁中
        assert labels["VX"] == "VIX"
        assert labels["CL"] == "原油"
        assert labels["GC"] == "黃金"
        assert labels["TSMC"] == "台積電"

    def test_the_tsmc_leg_is_the_cash_stock_not_a_stock_future(self) -> None:
        """台積電腿走現貨 `TC.S.TWS.2330`(自癒閘 = 個股日盤窗)。

        改成個股期 `TC.F.TWF.` 前綴的失效樣態不是報錯,而是**閘語意悄悄換人**:
        那個前綴會落進台期交日夜盤閘(收 13:45 / 有夜盤),與現貨 13:30 收盤不同尺,
        於是整個夜盤都在對一條收盤了的現貨腿 churn UNSUB+SUB。
        """
        tsmc = next(leg for leg in DEFAULT_CONFIG.legs if leg.key == "TSMC")
        assert tsmc.symbol == "TC.S.TWS.2330"


class TestLoadConfig:
    def test_missing_file_falls_back_to_default(self, tmp_path: Path) -> None:
        assert load_config(tmp_path / "nope.json") == DEFAULT_CONFIG

    def test_seventh_leg_added_without_engine_change(self, tmp_path: Path) -> None:
        """SC-8:日後 TC4 上架 CME SSF 的 TSM 只需改設定檔。"""
        path = tmp_path / "correlation.json"
        legs = [
            {
                "key": leg.key,
                "label": leg.label,
                "symbol": leg.symbol,
                "source": leg.source,
                "sparse": leg.sparse,  # 帶著:fixture 才仍等於 DEFAULT_CONFIG(review Spec 8)
            }
            for leg in DEFAULT_CONFIG.legs
        ]
        legs.append(
            {"key": "TSM", "label": "台積電ADR", "symbol": "TC.F.CME.TSM.HOT", "source": "tc4"}
        )
        path.write_text(json.dumps({"base": "TXF", "legs": legs}), encoding="utf-8")

        cfg = load_config(path)

        # 相對長度(不寫死 7):這條測的是「加一腿不必改引擎」,不是預設有幾腿
        assert len(cfg.legs) == len(DEFAULT_CONFIG.legs) + 1
        assert cfg.legs[-1].key == "TSM"
        assert cfg.legs[-1].symbol == "TC.F.CME.TSM.HOT"

    def test_sparse_flag_is_optional_and_only_literal_true_counts(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`sparse` 選配:缺 = False;只認 JSON 字面 true(字串 "yes" / 1 不算 —— 寧可少豁免一腿
        多幾發 churn,也不要把打錯字的腿悄悄從 R2 拿掉)。但「靜默丟掉旗標」要有訊號(pr-120 F-02):
        設定檔是給人手改的,打成字串 → 該腿修復不生效、退回每 240 s 一發,只能事後 grep log 才知道。"""
        path = tmp_path / "correlation.json"
        legs = [
            {"key": "TXF", "label": "台指", "symbol": "TC.F.TWF.TXF.HOT", "source": "futures_engine"},
            {"key": "SXF", "label": "費半", "symbol": "TC.F.TWF.SXF.HOT", "source": "tc4", "sparse": True},
            {"key": "NQ", "label": "納指", "symbol": "TC.F.CME.NQ.HOT", "source": "tc4", "sparse": "yes"},
            {"key": "ES", "label": "標普", "symbol": "TC.F.CME.ES.HOT", "source": "tc4"},
            # bool 是 int 子類:`1 == True` 但 `1 is True` 為 False —— 這行正是 `is True` 存在的理由
            {"key": "YM", "label": "道瓊", "symbol": "TC.F.CBOT.YM.HOT", "source": "tc4", "sparse": 1},
            # null 與「缺欄」對 `is True` 同義,但有人寫了 null 多半是想關 / 想開 → 也要點名(review S-4)
            {"key": "NK", "label": "日經", "symbol": "TC.F.OSE.NK225M.HOT", "source": "tc4", "sparse": None},
        ]
        path.write_text(json.dumps({"base": "TXF", "legs": legs}), encoding="utf-8")

        with caplog.at_level("WARNING"):
            cfg = load_config(path)

        assert [leg.sparse for leg in cfg.legs] == [False, True, False, False, False, False]
        bad = [r.message for r in caplog.records if "sparse" in r.message]
        assert any("NQ" in m and "('yes')" in m for m in bad), bad  # 字串 → 點名
        assert any("YM" in m and "(1)" in m for m in bad), bad  # 整數 → 點名
        assert any("NK" in m and "(None)" in m for m in bad), bad  # null → 點名
        assert not any("SXF" in m for m in bad), bad  # 合法 true 不吵

    def test_sparse_on_a_non_tc4_leg_warns_but_does_not_degrade(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """base 腿不由 corr source 訂閱 → 標 sparse 沒有 R2 可豁免;app 只對 tc4_legs() 算集合,旗標會被
        丟掉。不降級(腿組仍可用),但要 WARNING 點名 —— 靜默丟掉是零錯誤訊號的漂移。"""
        path = tmp_path / "correlation.json"
        legs = [
            {"key": "TXF", "label": "台指", "symbol": "TC.F.TWF.TXF.HOT", "source": "futures_engine", "sparse": True},
            {"key": "NQ", "label": "納指", "symbol": "TC.F.CME.NQ.HOT", "source": "tc4"},
        ]
        path.write_text(json.dumps({"base": "TXF", "legs": legs}), encoding="utf-8")

        with caplog.at_level("WARNING"):
            cfg = load_config(path)

        assert cfg is not DEFAULT_CONFIG and len(cfg.legs) == 2
        assert any("TXF" in r.message and "sparse" in r.message for r in caplog.records)

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


class TestRepoConfigFile:
    """repo 真檔 `configs/correlation.json`(不是 tmp 假檔)的腿契約。

    2026-08-17 R5:第七腿小日經 `TC.F.OSE.NK225M.HOT`(D13 拍板;OSE 夜盤實測 175 則/60s,
    高於 NK225 102 / SGX NK 78)。**2026-08-25 N021 起 DEFAULT_CONFIG 同步補到七腿** ——
    降級路徑不得比真檔少一腿。

    2026-08-26 F4:第 8–11 腿 VIX / 原油 / 黃金 / 台積電(2026-08-26 01:02 `corr_legs_probe`
    實測:VX 45 s 推 19 則、CL 163、GC 172,1K 首頁各 50 列;台幣匯率全樹無 TWD 標的,不加)。
    """

    def test_repo_config_has_eleven_legs_ending_with_the_f4_four(self) -> None:
        cfg = load_config(CONFIG_PATH)

        assert cfg is not DEFAULT_CONFIG, "真檔應成功載入,不得落回預設腿"
        assert len(cfg.legs) == 11
        assert [(leg.key, leg.label, leg.symbol, leg.source) for leg in cfg.legs] == [
            *_EXPECTED_LEGS
        ]

    def test_repo_config_matches_default_leg_for_leg(self) -> None:
        """白名單 W1:現有腿的 key/label/symbol/source 與順序不動,base 仍 TXF。

        N021 起兩邊**全等**(不再只比前六腿)—— 真檔與降級預設分岔正是那條 bug。
        """
        cfg = load_config(CONFIG_PATH)

        assert cfg.legs == DEFAULT_CONFIG.legs
        assert cfg.base == "TXF"


def test_river_palette_covers_every_leg() -> None:
    """跨檔契約(CLAUDE.md §4 精神):江波圖顏色**依腿序位**指派,腿數 > 調色盤色數時
    `RIVER_STROKES[i % n]` 會靜默撞回 base 近白色(river-colors.ts 自述的失效樣態)。
    後端是腿數的產生點,前端是讀者 → 在這裡以原始碼字面鎖住 色數 >= 腿數。"""
    src = Path(__file__).resolve().parents[1] / "frontend/src/components/corr/river-colors.ts"
    text = src.read_text(encoding="utf-8")
    strokes = re.findall(r'"stroke-river-(\d+)"', text)
    assert strokes == [str(i) for i in range(1, len(strokes) + 1)], strokes
    css = (src.parents[2] / "index.css").read_text(encoding="utf-8")
    tokens = re.findall(r"--color-river-(\d+):", css)
    # 序位包含而不是個數(review F-18):少 8 多 12 個數相等照過,而少的那格 Tailwind 不產 utility
    assert set(tokens) >= set(strokes), (tokens, strokes)
    for cfg in (DEFAULT_CONFIG, load_config()):
        assert len(cfg.legs) <= len(strokes), (len(cfg.legs), len(strokes))
