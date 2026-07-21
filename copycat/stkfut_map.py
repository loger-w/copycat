"""股號 ↔ 個股期產品碼對映(design v4.1 §2.6)。

個股期不在 TC4 商品樹(2026-07-21 spike:Type="Fut" 只回指數/商品期 40 碼,但
CDF.HOT 可訂閱)→ 對映靠期交所「股票期貨契約」公開表:契約代號兩碼 + "F" =
TC4 產品碼(CD → CDF,spike 實證)。內建版控檔 `copycat/stkfut_map.json`,
`python -m copycat refresh-stkfut-map` 重抓(失敗保留舊檔)。
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from pathlib import Path

from copycat.fileio import atomic_write_text

logger = logging.getLogger(__name__)

_CACHE_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parent / "stkfut_map.json"
TAIFEX_URL = "https://www.taifex.com.tw/cht/2/stockLists"

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(cell: str) -> str:
    return _TAG_RE.sub("", cell).strip()


def _contract_unit(cells: list[str]) -> int:
    """契約單位(股數):cells 尾段第一個純數字欄;找不到 → 0。"""
    for cell in cells[4:]:
        text = _text(cell).replace(",", "")
        if text.isdigit():
            return int(text)
    return 0


def parse_taifex_html(html: str) -> dict[str, dict]:
    """期交所股票期貨清單頁 → {股號: {prod, name}};只收「是股票期貨標的」列。

    同股號含標準(2,000 股)與小型(100 股)兩列 — 取契約單位較大者(標準檔;
    2026-07-21 真實頁面實證小型列在後,單純 last-write 會拿到 QFF 而非 CDF)。
    """
    result: dict[str, dict] = {}
    units: dict[str, int] = {}
    for row_match in _ROW_RE.finditer(html):
        cells = _TD_RE.findall(row_match.group(1))
        if len(cells) < 5:
            continue
        prefix = _text(cells[0])
        code = _text(cells[2])
        name = _text(cells[3])
        has_future = "●" in cells[4]
        if not has_future or not re.fullmatch(r"[A-Z]{1,2}", prefix):
            continue
        if not re.fullmatch(r"[A-Za-z0-9]{4,6}", code):
            continue
        unit = _contract_unit(cells)
        if code in result and unit <= units.get(code, 0):
            continue
        result[code] = {"prod": f"{prefix}F", "name": name}
        units[code] = unit
    return result


def load_map(path: Path = DEFAULT_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload.get("map", {}))


def write_map(path: Path, mapping: dict[str, dict]) -> None:
    atomic_write_text(
        path,
        json.dumps(
            {"_cache_version": _CACHE_VERSION, "map": mapping},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        ),
    )


def refresh(path: Path = DEFAULT_PATH, url: str = TAIFEX_URL) -> dict[str, dict]:
    """抓期交所頁面重生對映;抓取/解析失敗保留舊檔並原樣拋出。"""
    req = urllib.request.Request(url, headers={"User-Agent": "copycat/stkfut-map"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    mapping = parse_taifex_html(html)
    if not mapping:
        raise ValueError("taifex 頁面解析 0 列 — 格式可能變動,保留舊檔")
    write_map(path, mapping)
    logger.info("stkfut map refreshed: %d entries", len(mapping))
    return mapping
