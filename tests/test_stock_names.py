from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.stock_names import (
    ISIN_URLS,
    load_names,
    parse_isin_html,
    parse_isin_html_with_stats,
    refresh,
    write_names,
)

# 段標題列 = 單一 <td>(colspan);資料列 cells[0] = "<code>　<name>"(全形空格)。
# 實測欄位順序:code+name / ISIN / 上市日 / 市場別 / 產業別 / CFICode。
FIXTURE_HTML = """
<table><tbody>
<tr><td colspan="7">股票</td></tr>
<tr><td>2330　台積電</td><td>TW0002330008</td><td>1994/09/05</td><td>上市</td><td>半導體業</td></tr>
<tr><td>6547　高端疫苗</td><td>TW0006547005</td><td>2018/06/25</td><td>上櫃</td><td>生技醫療</td></tr>
<tr><td>2801A　彰銀甲特</td><td>TW0002801A08</td><td>2019/01/01</td><td>上市</td><td>金融業</td></tr>
<tr><td>999　太短</td><td>TWX</td><td>2020/01/01</td><td>上市</td><td>x</td></tr>
<tr><td>ABCD　無數字</td><td>TWY</td><td>2020/01/01</td><td>上市</td><td>x</td></tr>
<tr><td>1234　</td><td>TWZ</td><td>2020/01/01</td><td>上市</td><td>x</td></tr>
<tr><td>5678沒有分隔</td><td>TWW</td><td>2020/01/01</td><td>上市</td><td>x</td></tr>
<tr><td>8888　名稱 含　全形空格</td><td>TWV</td><td>2020/01/01</td><td>上市</td><td>x</td></tr>
<tr><td>欄數不足</td><td>只有兩欄</td></tr>
<tr><td colspan="7">上市認購(售)權證</td></tr>
<tr><td>030001　元大台積購01</td><td>TWW0300010</td><td>2025/01/01</td><td>上市</td><td>x</td></tr>
<tr><td>030002　凱基聯電購02</td><td>TWW0300028</td><td>2025/01/01</td><td>上市</td><td>x</td></tr>
<tr><td colspan="7">ETF</td></tr>
<tr><td>00679B　元大美債20年</td><td>TW00679B004</td><td>2017/01/17</td><td>上市</td><td>x</td></tr>
<tr><td>2330　重複代號</td><td>TW0002330008</td><td>1994/09/05</td><td>上市</td><td>x</td></tr>
</tbody></table>
"""

# 段標題偵測失效的樣態:TWSE 把段標題改成 colspan + 空 td(兩個 cell)→ 段名永遠不更新,
# 「含權證 → 略過」整條失效。守門必須擋住這種「收太多」。
BROKEN_SECTION_HTML = """
<table><tbody>
<tr><td colspan="6">上市認購(售)權證</td><td></td></tr>
<tr><td>030001　元大台積購01</td><td>TWW0300010</td><td>2025/01/01</td><td>上市</td><td>x</td></tr>
</tbody></table>
"""


class TestParseIsinHtml:
    def test_keeps_stock_and_etf_sections(self) -> None:
        result = parse_isin_html(FIXTURE_HTML)
        assert result["2330"] == "台積電"
        assert result["6547"] == "高端疫苗"
        assert result["00679B"] == "元大美債20年"
        # 特別股(5 碼含字母尾)通過 validate_code
        assert result["2801A"] == "彰銀甲特"

    def test_warrant_section_excluded(self) -> None:
        result = parse_isin_html(FIXTURE_HTML)
        assert "030001" not in result
        assert "030002" not in result

    def test_invalid_codes_dropped(self) -> None:
        result = parse_isin_html(FIXTURE_HTML)
        assert "999" not in result  # 太短
        assert "ABCD" not in result  # 無數字
        assert "1234" not in result  # 名稱空
        assert "5678沒有分隔" not in result

    def test_name_may_contain_fullwidth_space(self) -> None:
        """split 必須 maxsplit=1,否則名稱含全形空格的列會被切碎或誤剔。"""
        assert parse_isin_html(FIXTURE_HTML)["8888"] == "名稱 含　全形空格"

    def test_duplicate_code_keeps_first(self) -> None:
        assert parse_isin_html(FIXTURE_HTML)["2330"] == "台積電"

    def test_malformed_rows_do_not_raise(self) -> None:
        assert parse_isin_html("<tr><td>x</td></tr><tr></tr><tr><td>a</td><td>b</td></tr>") == {}

    def test_section_counts_exposed_for_drift_visibility(self) -> None:
        """refresh 要能 log 逐段筆數 + 被剔除的權證列數,漂移才看得見。"""
        result, stats = parse_isin_html_with_stats(FIXTURE_HTML)
        assert result["2330"] == "台積電"
        assert stats.per_section["股票"] == 4  # 2330 / 6547 / 2801A / 8888
        assert stats.per_section["ETF"] == 1  # 00679B(2330 重複不計)
        assert stats.warrant_rows == 2


class TestLoadWrite:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_names(tmp_path / "nope.json") == {}

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "names.json"
        write_names(path, {"2330": "台積電"})
        assert load_names(path) == {"2330": "台積電"}
        assert json.loads(path.read_text(encoding="utf-8"))["_cache_version"] == 1

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        """endpoint 承諾「表不可用 → 空陣列不 500」,韌性必須在這一層。"""
        path = tmp_path / "names.json"
        path.write_text("{oops", encoding="utf-8")
        assert load_names(path) == {}

    def test_missing_names_key_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "names.json"
        path.write_text(json.dumps({"_cache_version": 1}), encoding="utf-8")
        assert load_names(path) == {}


def _fetcher(pages: dict[str, str]):
    def fetch(url: str, _timeout: float) -> bytes:
        return pages[url].encode("cp950", errors="replace")

    return fetch


class TestRefreshGuards:
    """守門必須雙側 + 語意檢查:只防「收太少」的話,段標題偵測失效(收進 4 萬筆權證)
    完全不觸發,靜默覆寫版控檔。"""

    def _existing(self, tmp_path: Path) -> Path:
        path = tmp_path / "names.json"
        write_names(path, {"9999": "舊檔"})
        return path

    def test_too_few_raises_and_keeps_old_file(self, tmp_path: Path) -> None:
        path = self._existing(tmp_path)
        pages = {url: FIXTURE_HTML for url in ISIN_URLS}
        with pytest.raises(ValueError):
            refresh(path, fetcher=_fetcher(pages))
        assert load_names(path) == {"9999": "舊檔"}

    def test_warrant_section_not_detected_raises(self, tmp_path: Path) -> None:
        """段標題偵測失效 → 沒有任何段名含「權證」→ 視為解析失敗。"""
        path = self._existing(tmp_path)
        pages = {url: BROKEN_SECTION_HTML for url in ISIN_URLS}
        with pytest.raises(ValueError):
            refresh(path, fetcher=_fetcher(pages))
        assert load_names(path) == {"9999": "舊檔"}

    def test_too_many_raises(self, tmp_path: Path) -> None:
        """上界:段落偵測失效但仍有權證段名時,筆數會暴增到上萬。"""
        path = self._existing(tmp_path)
        rows = "\n".join(
            f"<tr><td>{3000 + i}　權證{i}</td><td>TW{i}</td><td>d</td><td>上市</td><td>x</td></tr>"
            for i in range(6100)
        )
        big = (
            "<table><tbody><tr><td colspan='7'>上市認購(售)權證</td></tr>"
            + "<tr><td>030001　權證A</td><td>TW</td><td>d</td><td>上市</td><td>x</td></tr>" * 5001
            + "<tr><td colspan='7'>股票</td></tr>"
            + rows
            + "</tbody></table>"
        )
        with pytest.raises(ValueError):
            refresh(path, fetcher=_fetcher({url: big for url in ISIN_URLS}))
        assert load_names(path) == {"9999": "舊檔"}

    def test_healthy_payload_writes(self, tmp_path: Path) -> None:
        path = tmp_path / "names.json"
        rows = "\n".join(
            f"<tr><td>{2000 + i}　股票{i}</td><td>TW{i}</td><td>d</td><td>上市</td><td>x</td></tr>"
            for i in range(1900)
        )
        html = (
            "<table><tbody><tr><td colspan='7'>上市認購(售)權證</td></tr>"
            + "<tr><td>030001　權證A</td><td>TW</td><td>d</td><td>上市</td><td>x</td></tr>" * 5001
            + "<tr><td colspan='7'>股票</td></tr>"
            + rows
            + "</tbody></table>"
        )
        # 兩個 URL 同內容 → 第二份全是重複 code,總數仍為 1900(落在 [1800, 6000])
        names = refresh(path, fetcher=_fetcher({url: html for url in ISIN_URLS}))
        assert len(names) == 1900
        assert load_names(path) == names
