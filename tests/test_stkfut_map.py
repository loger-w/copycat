from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import copycat.stkfut_map as stkfut_map
from copycat.stkfut_map import load_map, lookup_product, parse_taifex_html, refresh, write_map

FIXTURE_HTML = """
<table><tbody>
<tr>
 <td align="center">CD</td>
 <td style="text-align: left">台灣積體電路製造股份有限公司</td>
 <td align="center">2330</td>
 <td style="text-align: left">台積電</td>
 <td align="center"><font size="5" aria-hidden="true">●</font> <span class="sr-only">是股票期貨標的</span></td>
 <td align="center"><font size="5" aria-hidden="true">●</font></td>
 <td style="text-align: right">2,000</td>
</tr>
<tr>
 <td align="center">ZZ</td>
 <td style="text-align: left">無期貨股份有限公司</td>
 <td align="center">9999</td>
 <td style="text-align: left">無期貨</td>
 <td align="center"></td>
 <td align="center"></td>
 <td style="text-align: right">2,000</td>
</tr>
<tr>
 <td align="center">NY</td>
 <td style="text-align: left">元大台灣五十</td>
 <td align="center">0050</td>
 <td style="text-align: left">元大台灣50</td>
 <td align="center"><font size="5" aria-hidden="true">●</font> <span class="sr-only">是股票期貨標的</span></td>
 <td align="center"></td>
 <td style="text-align: right">10,000</td>
</tr>
</tbody></table>
"""

_PAIR_HTML = """
<tr><td align="center">CD</td><td>台灣積體電路</td><td align="center">2330</td>
<td>台積電</td><td><font>●</font><span>是股票期貨標的</span></td><td></td>
<td style="text-align: right">2,000</td><td>8:45~13:45</td></tr>
<tr><td align="center">QF</td><td>台灣積體電路</td><td align="center">2330</td>
<td>小型台積電</td><td><font>●</font><span>是股票期貨標的</span></td><td></td>
<td style="text-align: right">100</td><td>8:45~13:45</td></tr>
"""


def _v2_map() -> dict[str, dict]:
    return {
        "2330": {
            "prod": "CDF",
            "name": "台積電",
            "unit": 2000,
            "mini": {"prod": "QFF", "unit": 100},
        },
        "0050": {"prod": "NYF", "name": "元大台灣50ETF", "unit": 10000, "mini": None},
    }


class TestParseTaifexHtml:
    def test_flagged_rows_only_prod_is_prefix_plus_f(self) -> None:
        result = parse_taifex_html(FIXTURE_HTML)
        assert result == {
            "2330": {"prod": "CDF", "name": "台積電", "unit": 2000, "mini": None},
            "0050": {"prod": "NYF", "name": "元大台灣50", "unit": 10000, "mini": None},
        }

    def test_standard_and_mini_rows_coexist_in_separate_fields(self) -> None:
        """v2:同股號兩列不再互相覆蓋 —— 契約單位大者入 std 欄、小者入 mini 欄。

        v1 語意是「取單位較大者、丟掉小型」(期現對照只要標準檔);小型個股期要能
        下單選月之後,丟掉的那一列就是使用者要選的合約(2026-08-06 SC-2)。
        """
        result = parse_taifex_html(_PAIR_HTML)
        assert result["2330"] == {
            "prod": "CDF",
            "name": "台積電",
            "unit": 2000,
            "mini": {"prod": "QFF", "unit": 100},
        }

    def test_mini_only_still_included(self) -> None:
        html = """
        <tr><td align="center">QX</td><td>某公司</td><td align="center">8888</td>
        <td>小型某</td><td><font>●</font><span>是股票期貨標的</span></td><td></td>
        <td style="text-align: right">100</td><td>8:45~13:45</td></tr>
        """
        assert parse_taifex_html(html)["8888"]["prod"] == "QXF"

    def test_rows_without_unit_are_skipped(self) -> None:
        """契約單位刮不到的列一律跳過:乘數是安全邊界(名目金額閘),不可猜。"""
        html = """
        <tr><td align="center">CD</td><td>台灣積體電路</td><td align="center">2330</td>
        <td>台積電</td><td><font>●</font><span>是股票期貨標的</span></td><td></td></tr>
        """
        assert parse_taifex_html(html) == {}


class TestMapIo:
    def test_write_then_load_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        write_map(path, _v2_map())
        assert load_map(path) == _v2_map()

    def test_load_default_packaged_map_has_cdf(self) -> None:
        # 內建版控檔隨 PR 提供;至少涵蓋 spike 驗證過的 CDF=2330 與其小型 QFF
        m = load_map()
        assert m["2330"]["prod"] == "CDF"
        assert m["2330"]["unit"] == 2000
        assert m["2330"]["mini"] == {"prod": "QFF", "unit": 100}

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert load_map(tmp_path / "nope.json") == {}

    def test_write_map_is_versioned(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        write_map(path, _v2_map())
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["_cache_version"] == 2

    def test_load_stale_version_degrades_to_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """舊版檔 → 空表 + warning,**不 raise**:唯一 runtime 呼叫點是
        `StockEngine.__init__`,拋例外會讓整個個股 tab 因為一份對映檔而掛掉(R2-6)。
        """
        path = tmp_path / "map.json"
        path.write_text(
            json.dumps({"_cache_version": 1, "map": {"2330": {"prod": "CDF", "name": "台積電"}}}),
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING):
            assert load_map(path) == {}
        assert "版本" in caplog.text or "version" in caplog.text.lower()


class TestLookupProduct:
    def test_std_and_mini_products_resolve(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        write_map(path, _v2_map())
        assert lookup_product("CDF", path=path) == {"unit": 2000, "kind": "std", "code": "2330"}
        assert lookup_product("QFF", path=path) == {"unit": 100, "kind": "mini", "code": "2330"}

    def test_unknown_product_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        write_map(path, _v2_map())
        assert lookup_product("ZZF", path=path) is None

    def test_index_is_cached_but_invalidated_by_write(self, tmp_path: Path) -> None:
        """process 級 lazy cache:每次送單都重讀 268 檔 JSON 是熱路徑上的無謂 IO;
        但 refresh 之後必須看得到新表(write_map 作廢該路徑的索引)。"""
        path = tmp_path / "map.json"
        write_map(path, _v2_map())
        assert lookup_product("CDF", path=path) is not None
        write_map(path, {"9999": {"prod": "ZZF", "name": "新", "unit": 2000, "mini": None}})
        assert lookup_product("CDF", path=path) is None
        assert lookup_product("ZZF", path=path) == {"unit": 2000, "kind": "std", "code": "9999"}


class TestRefresh:
    def test_bad_rows_skipped_with_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """混壞列:好列照落,壞列彙總 warn —— 靜默跳過會讓「期交所改版」表現成
        「這幾檔突然沒有期貨」,而畫面上只是下拉少了幾個選項。"""
        bad_row = """
        <tr><td align="center">CD</td><td>台灣積體電路</td><td align="center">2330</td>
        <td>台積電</td><td><font>●</font><span>是股票期貨標的</span></td><td></td></tr>
        """
        monkeypatch.setattr(stkfut_map, "_fetch_html", lambda url: FIXTURE_HTML + bad_row)
        path = tmp_path / "map.json"
        with caplog.at_level(logging.WARNING):
            mapping = refresh(path=path)
        assert set(mapping) == {"2330", "0050"}
        assert mapping["2330"]["unit"] == 2000  # 壞列不得蓋掉同股號的好列
        assert "略過" in caplog.text

    def test_all_rows_bad_raises_and_keeps_old_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "map.json"
        write_map(path, _v2_map())
        before = path.read_text(encoding="utf-8")
        monkeypatch.setattr(stkfut_map, "_fetch_html", lambda url: "<table></table>")
        with pytest.raises(ValueError):
            refresh(path=path)
        assert path.read_text(encoding="utf-8") == before
