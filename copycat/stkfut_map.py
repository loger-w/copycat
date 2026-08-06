"""股號 ↔ 個股期產品碼對映(design v4.1 §2.6;v2 = stkfut-contracts SC-2)。

個股期不在 TC4 商品樹(2026-07-21 spike:Type="Fut" 只回指數/商品期 40 碼,但
CDF.HOT 可訂閱)→ 對映靠期交所「股票期貨契約」公開表:契約代號兩碼 + "F" =
TC4 產品碼(CD → CDF,spike 實證)。內建版控檔 `copycat/stkfut_map.json`,
`python -m copycat refresh-stkfut-map` 重抓(失敗保留舊檔)。

**v2 形**(2026-08-06):每檔加 `unit`(標準型契約股數)與 `mini: {prod, unit} | None`
(小型契約)。unit 是下單名目金額閘的乘數 —— 屬安全邊界,所以走版控檔可稽核,
而不是每次跟期交所現抓。**版本不符 → 空表 + warning,不 raise**:唯一 runtime
呼叫點是 `StockEngine.__init__`,拋例外會讓整個個股 tab 因一份對映檔而掛掉。
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from pathlib import Path

from copycat.fileio import atomic_write_text

logger = logging.getLogger(__name__)

_CACHE_VERSION = 2
DEFAULT_PATH = Path(__file__).resolve().parent / "stkfut_map.json"
TAIFEX_URL = "https://www.taifex.com.tw/cht/2/stockLists"

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

#: prod → {unit, kind, code} 的反向索引(process 級 lazy cache,per path)。
#: 送單熱路徑上每筆都重讀 270 檔 JSON 是無謂 IO;`write_map` 會作廢對應路徑。
_INDEX_CACHE: dict[Path, dict[str, dict]] = {}


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
    """期交所股票期貨清單頁 → `{股號: {prod, name, unit, mini}}`;只收「是股票期貨標的」列。

    同股號含標準(2,000 股 / ETF 10,000 受益權單位)與小型(100 / 1,000)兩列 ——
    **v2 起兩列並存**:契約單位大者為標準檔(`prod`/`unit`),小者入 `mini`
    (v1 語意是丟掉小型,期現對照只要標準檔;小型個股期要能選月下單之後,
    被丟掉的那一列正是使用者要選的合約)。

    契約單位刮不到的列一律跳過並計入 warning(乘數是名目金額閘的分母,不可猜)。
    """
    mapping, _skipped = _parse_rows(html)
    return mapping


def _parse_rows(html: str) -> tuple[dict[str, dict], int]:
    """解析主體;回傳 (對映, 壞列數)。壞列 = 掛著「是股票期貨標的」卻解不出欄位的列。"""
    rows: dict[str, list[tuple[int, str, str]]] = {}
    skipped = 0
    for row_match in _ROW_RE.finditer(html):
        cells = _TD_RE.findall(row_match.group(1))
        if len(cells) < 5:
            continue
        if "●" not in cells[4]:
            continue  # 非股票期貨標的:正常資料,不是壞列
        prefix = _text(cells[0])
        code = _text(cells[2])
        name = _text(cells[3])
        unit = _contract_unit(cells)
        if not re.fullmatch(r"[A-Z]{1,2}", prefix) or not re.fullmatch(r"[A-Za-z0-9]{4,6}", code):
            skipped += 1
            continue
        if unit <= 0:
            skipped += 1
            continue
        rows.setdefault(code, []).append((unit, f"{prefix}F", name))
    result: dict[str, dict] = {}
    for code, legs in rows.items():
        legs.sort(key=lambda leg: -leg[0])  # 契約單位大者 = 標準檔
        unit, prod, name = legs[0]
        entry: dict = {"prod": prod, "name": name, "unit": unit, "mini": None}
        if len(legs) > 1:
            mini_unit, mini_prod, _ = legs[1]
            entry["mini"] = {"prod": mini_prod, "unit": mini_unit}
        result[code] = entry
    return result, skipped


def load_map(path: Path = DEFAULT_PATH) -> dict[str, dict]:
    """版控對映檔 → 對映;檔不存在或版本不符 → 空表(降級不 raise,見檔頭)。"""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("_cache_version")
    if version != _CACHE_VERSION:
        logger.warning(
            "stkfut 對映檔版本不符(%s ≠ %s):降級為空表,個股期乘數一律拒單 — "
            "跑 `python -m copycat refresh-stkfut-map` 重生",
            version,
            _CACHE_VERSION,
        )
        return {}
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
    _INDEX_CACHE.pop(path, None)  # refresh 之後同 process 必須看得到新表


def _product_index(path: Path) -> dict[str, dict]:
    cached = _INDEX_CACHE.get(path)
    if cached is not None:
        return cached
    index: dict[str, dict] = {}
    for code, entry in load_map(path).items():
        prod = entry.get("prod")
        if isinstance(prod, str):
            index[prod] = {"unit": entry.get("unit", 0), "kind": "std", "code": code}
        mini = entry.get("mini")
        if isinstance(mini, dict) and isinstance(mini.get("prod"), str):
            index[mini["prod"]] = {"unit": mini.get("unit", 0), "kind": "mini", "code": code}
    _INDEX_CACHE[path] = index
    return index


def lookup_product(prod: str, *, path: Path | None = None) -> dict | None:
    """個股期產品碼 → `{unit, kind: "std"|"mini", code}`;查無 → None。

    乘數(`capital/mapping.multiplier_of`)與下單閘(`server/capital_api`)共用的
    **單一入口** —— 兩邊各自走 `load_map` + 自己那份反查邏輯的話,「什麼算標準檔」
    就有兩個定義,而它們分岔時的失效樣態是「金額閘用一個單位、產品閘用另一個」。

    `path=None` → 呼叫期讀 `DEFAULT_PATH`(**不綁預設參數**:測試要能以
    monkeypatch 換掉模組層路徑來隔離版控真檔)。
    """
    return _product_index(path if path is not None else DEFAULT_PATH).get(prod)


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "copycat/stkfut-map"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def refresh(path: Path = DEFAULT_PATH, url: str = TAIFEX_URL) -> dict[str, dict]:
    """抓期交所頁面重生對映;抓取/解析失敗保留舊檔並原樣拋出。

    壞列**跳過 + 彙總 warn**(全滅才 raise):期交所改一欄就整份拒收,會讓
    「今天沒更新」變成常態;但靜默跳過又會讓改版表現成「這幾檔突然沒有期貨」。
    """
    html = _fetch_html(url)
    mapping, skipped = _parse_rows(html)
    if not mapping:
        raise ValueError("taifex 頁面解析 0 列 — 格式可能變動,保留舊檔")
    if skipped:
        logger.warning("stkfut map:略過 %d 列無法解析的標的列(期交所頁面格式可能變動)", skipped)
    write_map(path, mapping)
    logger.info("stkfut map refreshed: %d entries", len(mapping))
    return mapping
