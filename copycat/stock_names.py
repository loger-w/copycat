"""全市場股票代號 ↔ 名稱表(個股搜尋提示列用;change-spec stock-ui-round4 🟢-6)。

資料源 = 證交所 ISIN 公開查詢頁(`strMode=2` 上市 / `strMode=4` 上櫃)。內建**版控**檔
`copycat/stock_names.json`,`python -m copycat refresh-stock-names` 重抓(失敗保留舊檔)——
形狀完全比照 `copycat/stkfut_map.py`。落版控而非 `data/` 是刻意的:名稱表要在 clone
之後、還沒跑任何 CLI 之前就可用。

**解碼一定用 `cp950` 不是 `big5`**:2026-07-30 實測同一份上市頁,`big5` +
`errors="replace"` 解出 **447 個 U+FFFD**,`cp950`(Big5 超集)解出 **0 個**。名稱表的
唯一用途是給人看/搜,靜默毀字不可接受。

分類過濾用**排除法**(段名含「權證」者剔除),不用允許清單 —— 權證是唯一巨量段
(2026-07-30 實測上市 30,561 + 上櫃 9,438 = 39,999 列),而允許清單會在 TWSE 改段名時
靜默漏掉「股票」段。實測收錄 2,401 檔(上市 1,378 / 上櫃 1,023)。

守門是**雙側 + 語意檢查**而不只是下界:段標題偵測靠「單一 `<td>` 的列」,一旦 TWSE 改成
`colspan` + 空 `<td>`,段名就永遠不更新 → 「含權證 → 略過」整條失效 → 39,999 筆權證全部
收進表,總數約 42,000 **遠大於**任何下界,單側門檻完全不觸發而靜默覆寫版控檔。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from copycat.fileio import atomic_write_text
from copycat.stock_watchlist import validate_code

logger = logging.getLogger(__name__)

_CACHE_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parent / "stock_names.json"

ISIN_URLS = (
    "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",  # 上市
    "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",  # 上櫃
)
_TIMEOUT = 60.0  # 實測 7.5 MB + 2.5 MB

# 守門門檻(實測基準:總 2,401;權證段 30,561 / 9,438;股票段 1,054 / 890)
_MIN_TOTAL = 1_800
_MAX_TOTAL = 6_000
_MIN_WARRANT_ROWS = 5_000
_MIN_STOCK_ROWS = 500

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_FULLWIDTH_SPACE = "　"
_REPLACEMENT = "�"


@dataclass
class ParseStats:
    """逐段筆數與剔除計數 —— refresh 要 log 出來,格式漂移才看得見(禁止靜默截斷)。"""

    per_section: dict[str, int] = field(default_factory=dict)
    warrant_rows: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    duplicates: list[str] = field(default_factory=list)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1


def _text(cell: str) -> str:
    return _TAG_RE.sub("", cell).replace("&nbsp;", " ").strip()


def parse_isin_html_with_stats(html: str) -> tuple[dict[str, str], ParseStats]:
    """ISIN 頁 → ({股號: 名稱}, 逐段筆數與剔除計數)。

    段名含「權證」的整段剔除;重複代號保留先出現者。統計是 `refresh` 的守門與 log 依據。
    """
    names: dict[str, str] = {}
    stats = ParseStats()
    section = ""
    for row_match in _ROW_RE.finditer(html):
        cells = [_text(c) for c in _TD_RE.findall(row_match.group(1))]
        if len(cells) == 1:
            section = cells[0]
            continue
        if "權證" in section:
            stats.warrant_rows += 1
            continue
        if len(cells) < 4:
            stats.drop("cells")
            continue
        # maxsplit=1:名稱本身可能含全形空格(實測上市段目前 0 筆,但不能靠這個)
        parts = cells[0].split(_FULLWIDTH_SPACE, 1)
        if len(parts) < 2:
            stats.drop("no_separator")
            continue
        code = parts[0].strip()
        name = parts[1].strip()
        # 只收「加得進自選」的代碼 —— 提示列點了才被後端 400 打回是最差體驗
        if not validate_code(code):
            stats.drop("bad_code")
            continue
        if not name:
            stats.drop("empty_name")
            continue
        if code in names:
            stats.duplicates.append(code)
            continue
        names[code] = name
        stats.per_section[section] = stats.per_section.get(section, 0) + 1
    return names, stats


def load_names(path: Path = DEFAULT_PATH) -> dict[str, str]:
    """讀名稱表。**任何讀取/格式問題都回 `{}`**(`/api/stock/names` 承諾不 500)。"""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload["names"]
        return {str(k): str(v) for k, v in raw.items()}
    except (json.JSONDecodeError, OSError, KeyError, TypeError, AttributeError) as e:
        logger.warning("股票名稱表讀取失敗(視為空表):%s", e)
        return {}


def write_names(path: Path, names: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {"_cache_version": _CACHE_VERSION, "names": names},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        ),
    )


def _default_fetcher(url: str, timeout: float) -> bytes:
    req = Request(url, headers={"User-Agent": "copycat/stock-names"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 固定的證交所 https URL
        return bytes(resp.read())


def refresh(
    path: Path = DEFAULT_PATH,
    urls: tuple[str, ...] = ISIN_URLS,
    fetcher: Callable[[str, float], bytes] = _default_fetcher,
) -> dict[str, str]:
    """抓 ISIN 頁重生名稱表;守門任一條不成立 → 拋 `ValueError` 保留舊檔。"""
    merged: dict[str, str] = {}
    warrant_rows = 0
    stock_section_rows = 0
    for url in urls:
        html = fetcher(url, _TIMEOUT).decode("cp950", errors="replace")
        names, stats = parse_isin_html_with_stats(html)
        warrant_rows += stats.warrant_rows
        # substring 比對 + 跨 URL 合計:精確段名比對會在 TWSE 把「股票」改成「上市股票」
        # 這種無害微調後讓 CLI 整條死掉,而 auto-default 選排除法的理由正是要避開段名耦合
        stock_section_rows += sum(n for sec, n in stats.per_section.items() if "股票" in sec)
        logger.info(
            "ISIN %s:收 %d 筆,逐段 %s,權證剔除 %d 列,其他剔除 %s",
            url,
            len(names),
            stats.per_section,
            stats.warrant_rows,
            stats.dropped or "{}",
        )
        if stats.duplicates:
            logger.warning("ISIN %s 段內重複代號 %s", url, sorted(set(stats.duplicates)))
        cross = [code for code in names if code in merged]
        if cross:
            logger.warning("跨市場重複代號(保留先出現者)%s", sorted(cross))
        for code, name in names.items():
            merged.setdefault(code, name)

    # 語意檢查先於數量:段標題偵測活著,才輪得到討論筆數合不合理
    if warrant_rows < _MIN_WARRANT_ROWS:
        raise ValueError(
            f"權證段只剔除 {warrant_rows} 列(< {_MIN_WARRANT_ROWS})—— "
            "段標題偵測可能失效,保留舊檔"
        )
    if stock_section_rows < _MIN_STOCK_ROWS:
        raise ValueError(
            f"「股票」段只收到 {stock_section_rows} 筆(< {_MIN_STOCK_ROWS})—— "
            "段名或欄位格式可能變動,保留舊檔"
        )
    if not _MIN_TOTAL <= len(merged) <= _MAX_TOTAL:
        raise ValueError(
            f"名稱表 {len(merged)} 筆不在 [{_MIN_TOTAL}, {_MAX_TOTAL}] —— "
            "格式可能變動(過多常代表段標題偵測失效把權證收進來),保留舊檔"
        )
    mangled = [code for code, name in merged.items() if _REPLACEMENT in name]
    if mangled:
        logger.warning("名稱含無法解碼字元的 %d 筆:%s", len(mangled), sorted(mangled)[:20])
    write_names(path, merged)
    logger.info("股票名稱表更新完成:%d 檔(權證剔除 %d 列)", len(merged), warrant_rows)
    return merged




