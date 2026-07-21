from __future__ import annotations

import json
from pathlib import Path

from copycat.stkfut_map import load_map, parse_taifex_html, write_map

FIXTURE_HTML = """
<table><tbody>
<tr>
 <td align="center">CD</td>
 <td style="text-align: left">台灣積體電路製造股份有限公司</td>
 <td align="center">2330</td>
 <td style="text-align: left">台積電</td>
 <td align="center"><font size="5" aria-hidden="true">●</font> <span class="sr-only">是股票期貨標的</span></td>
 <td align="center"><font size="5" aria-hidden="true">●</font></td>
</tr>
<tr>
 <td align="center">ZZ</td>
 <td style="text-align: left">無期貨股份有限公司</td>
 <td align="center">9999</td>
 <td style="text-align: left">無期貨</td>
 <td align="center"></td>
 <td align="center"></td>
</tr>
<tr>
 <td align="center">NY</td>
 <td style="text-align: left">元大台灣五十</td>
 <td align="center">0050</td>
 <td style="text-align: left">元大台灣50</td>
 <td align="center"><font size="5" aria-hidden="true">●</font> <span class="sr-only">是股票期貨標的</span></td>
 <td align="center"></td>
</tr>
</tbody></table>
"""


class TestParseTaifexHtml:
    def test_flagged_rows_only_prod_is_prefix_plus_f(self) -> None:
        result = parse_taifex_html(FIXTURE_HTML)
        assert result == {
            "2330": {"prod": "CDF", "name": "台積電"},
            "0050": {"prod": "NYF", "name": "元大台灣50"},
        }

    def test_standard_contract_preferred_over_mini(self) -> None:
        # 期交所同頁含標準(2,000 股)與小型(100 股)兩列同股號 — 期現對照要標準檔
        # (2026-07-21 真實頁面實證:2330 被小型 QFF 覆蓋)
        html = """
        <tr><td align="center">CD</td><td>台灣積體電路</td><td align="center">2330</td>
        <td>台積電</td><td><font>●</font><span>是股票期貨標的</span></td><td></td>
        <td style="text-align: right">2,000</td><td>8:45~13:45</td></tr>
        <tr><td align="center">QF</td><td>台灣積體電路</td><td align="center">2330</td>
        <td>小型台積電</td><td><font>●</font><span>是股票期貨標的</span></td><td></td>
        <td style="text-align: right">100</td><td>8:45~13:45</td></tr>
        """
        result = parse_taifex_html(html)
        assert result["2330"] == {"prod": "CDF", "name": "台積電"}

    def test_mini_only_still_included(self) -> None:
        html = """
        <tr><td align="center">QX</td><td>某公司</td><td align="center">8888</td>
        <td>小型某</td><td><font>●</font><span>是股票期貨標的</span></td><td></td>
        <td style="text-align: right">100</td><td>8:45~13:45</td></tr>
        """
        assert parse_taifex_html(html)["8888"]["prod"] == "QXF"


class TestMapIo:
    def test_write_then_load_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        write_map(path, {"2330": {"prod": "CDF", "name": "台積電"}})
        assert load_map(path) == {"2330": {"prod": "CDF", "name": "台積電"}}

    def test_load_default_packaged_map_has_cdf(self) -> None:
        # 內建版控檔隨 PR 提供;至少涵蓋 spike 驗證過的 CDF=2330
        m = load_map()
        assert m["2330"]["prod"] == "CDF"

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert load_map(tmp_path / "nope.json") == {}

    def test_write_map_is_versioned(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        write_map(path, {"2330": {"prod": "CDF", "name": "台積電"}})
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "_cache_version" in payload
