from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.stock_names import (
    ISIN_URLS,
    load_names,
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
        result, _ = parse_isin_html_with_stats(FIXTURE_HTML)
        assert result["2330"] == "台積電"
        assert result["6547"] == "高端疫苗"
        assert result["00679B"] == "元大美債20年"
        # 特別股(5 碼含字母尾)通過 validate_code
        assert result["2801A"] == "彰銀甲特"

    def test_warrant_section_excluded(self) -> None:
        result, _ = parse_isin_html_with_stats(FIXTURE_HTML)
        assert "030001" not in result
        assert "030002" not in result

    def test_invalid_codes_dropped(self) -> None:
        result, _ = parse_isin_html_with_stats(FIXTURE_HTML)
        assert "999" not in result  # 太短
        assert "ABCD" not in result  # 無數字
        assert "1234" not in result  # 名稱空
        assert "5678沒有分隔" not in result

    def test_name_may_contain_fullwidth_space(self) -> None:
        """split 必須 maxsplit=1,否則名稱含全形空格的列會被切碎或誤剔。"""
        assert parse_isin_html_with_stats(FIXTURE_HTML)[0]["8888"] == "名稱 含　全形空格"

    def test_duplicate_code_keeps_first(self) -> None:
        assert parse_isin_html_with_stats(FIXTURE_HTML)[0]["2330"] == "台積電"

    def test_malformed_rows_do_not_raise(self) -> None:
        html = "<tr><td>x</td></tr><tr></tr><tr><td>a</td><td>b</td></tr>"
        assert parse_isin_html_with_stats(html)[0] == {}

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


def _build_html(*, warrant_rows: int, stock_rows: int, base: int = 2000) -> str:
    """權證段 N 列 + 股票段 M 列。三條守門要能被**分別**觸發,fixture 就得能獨立調參 ——
    否則測試名稱寫「下界」卻其實撞在權證那條(self-review FG-3 實際踩過)。"""
    warrants = "".join(
        f"<tr><td>03{i:04d}　權證{i}</td><td>TW{i}</td><td>d</td><td>上市</td><td>x</td></tr>"
        for i in range(warrant_rows)
    )
    stocks = "".join(
        f"<tr><td>{base + i}　股票{i}</td><td>TWS{i}</td><td>d</td><td>上市</td><td>x</td></tr>"
        for i in range(stock_rows)
    )
    return (
        "<table><tbody>"
        f"<tr><td colspan='7'>上市認購(售)權證</td></tr>{warrants}"
        f"<tr><td colspan='7'>股票</td></tr>{stocks}"
        "</tbody></table>"
    )


class TestRefreshGuards:
    """守門必須雙側 + 語意檢查:只防「收太少」的話,段標題偵測失效(收進 4 萬筆權證)
    完全不觸發,靜默覆寫版控檔。

    **每支測試都斷言錯誤訊息**,確保它釘的是自己那條守門 —— 只驗 `pytest.raises(ValueError)`
    的話,三支可以全部撞在同一條上而測試名稱看起來都對(FG-3)。"""

    def _existing(self, tmp_path: Path) -> Path:
        path = tmp_path / "names.json"
        write_names(path, {"9999": "舊檔"})
        return path

    def test_too_few_raises_and_keeps_old_file(self, tmp_path: Path) -> None:
        """下界:權證段與股票段都健康,只有總筆數不足 → 必須是**總數**那條守門攔下。"""
        path = self._existing(tmp_path)
        # 權證 5001(> 5000 過關)、股票 600(> 500 過關)、總數 600(< 1800 不過)
        html = _build_html(warrant_rows=5001, stock_rows=600)
        with pytest.raises(ValueError, match=r"\[1800, 6000\]"):
            refresh(path, fetcher=_fetcher({url: html for url in ISIN_URLS}))
        assert load_names(path) == {"9999": "舊檔"}

    def test_warrant_section_not_detected_raises(self, tmp_path: Path) -> None:
        """段標題偵測失效 → 沒有任何段名含「權證」→ 視為解析失敗。"""
        path = self._existing(tmp_path)
        pages = {url: BROKEN_SECTION_HTML for url in ISIN_URLS}
        with pytest.raises(ValueError, match="權證段"):
            refresh(path, fetcher=_fetcher(pages))
        assert load_names(path) == {"9999": "舊檔"}

    def test_stock_section_missing_raises(self, tmp_path: Path) -> None:
        """段名改動導致「股票」段收不到 → 保留舊檔(而不是寫一份只有 ETF 的表)。"""
        path = self._existing(tmp_path)
        html = _build_html(warrant_rows=5001, stock_rows=10)
        with pytest.raises(ValueError, match="「股票」段"):
            refresh(path, fetcher=_fetcher({url: html for url in ISIN_URLS}))
        assert load_names(path) == {"9999": "舊檔"}

    def test_too_many_raises(self, tmp_path: Path) -> None:
        """上界:段落偵測失效但仍有權證段名時,筆數會暴增到上萬。"""
        path = self._existing(tmp_path)
        html = _build_html(warrant_rows=5001, stock_rows=6100)
        with pytest.raises(ValueError, match=r"\[1800, 6000\]"):
            refresh(path, fetcher=_fetcher({url: html for url in ISIN_URLS}))
        assert load_names(path) == {"9999": "舊檔"}

    def test_healthy_payload_writes(self, tmp_path: Path) -> None:
        path = tmp_path / "names.json"
        html = _build_html(warrant_rows=5001, stock_rows=1900)
        # 兩個 URL 同內容 → 第二份全是重複 code,總數仍為 1900(落在 [1800, 6000])
        names = refresh(path, fetcher=_fetcher({url: html for url in ISIN_URLS}))
        assert len(names) == 1900
        assert load_names(path) == names

    def test_cross_market_duplicate_keeps_first_url(self, tmp_path: Path) -> None:
        """跨市場同號 → 保留先出現者(上市優先,因 URL 順序)。原本三支 refresh 測試都餵
        同一份 HTML 給兩個 URL,這條 setdefault 語意只存在註解裡(FG-3 同批 MC-9)。"""
        path = tmp_path / "names.json"
        listed = _build_html(warrant_rows=5001, stock_rows=1900, base=2000)
        otc = _build_html(warrant_rows=5001, stock_rows=1900, base=2000).replace(
            "股票0</td>", "上櫃同號</td>"
        )
        names = refresh(path, fetcher=_fetcher({ISIN_URLS[0]: listed, ISIN_URLS[1]: otc}))
        assert names["2000"] == "股票0"  # 上市那份贏
