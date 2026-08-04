"""個股自選清單持久化(design v4 §2.5;atomic JSON、無 DB — 專案慣例)。

v3(stock-ui-round5 §🔴-4):`{"codes": [...], "groups": [{"name", "codes"}]}`。
`codes` = 自選全體(有序)= 訂閱池;`groups` 只記成員關係。
**未分組 = codes − ∪groups 衍生不另存** —— 另存一份 ungrouped 會產生「同一檔同時在
未分組與某群組」的可違反不變式,而那個違反在畫面上是「同一檔出現兩次」= 靜默資料錯。

讀時遷移(不就地寫檔):v2(有 groups 無 codes)→ `codes = union(groups)`(畫面零差異);
v1(只有 codes)→ codes 原樣 + 零群組(v1 從來沒有群組概念,包成假的「自選」組是 v2
時代沒有未分組桶的權宜)。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

from copycat.fileio import atomic_write_text


class Group(TypedDict):
    name: str
    codes: list[str]


class Watchlist(TypedDict):
    codes: list[str]
    groups: list[Group]


WATCHLIST_LIMIT = 30
_CACHE_VERSION = 3
# 4-6 位英數且至少一位數字(涵蓋 00637L 等字母尾碼 ETF;design r1-F6)。
# 存在性不在此驗 — SUBQUOTE 對不存在 symbol 照回 OK,推播健檢才是真閘。
_CODE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9]{4,6}$")

DEFAULT_PATH = Path("data") / "stock_watchlist.json"


class WatchlistError(ValueError):
    """error code 進 HTTPException detail.error(跨檔契約)。"""


def validate_code(code: str) -> bool:
    return _CODE_RE.match(code) is not None


def union(groups: list[Group]) -> list[str]:
    """跨群組聯集,首見序去重。"""
    seen: list[str] = []
    for g in groups:
        for code in g["codes"]:
            if code not in seen:
                seen.append(code)
    return seen


def load_watchlist(path: Path = DEFAULT_PATH) -> Watchlist:
    if not path.exists():
        return {"codes": [], "groups": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups: list[Group] = [
        {"name": str(g["name"]), "codes": list(g["codes"])} for g in payload.get("groups", [])
    ]
    if "codes" in payload:  # v3 / v1
        return {"codes": list(payload["codes"]), "groups": groups}
    return {"codes": union(groups), "groups": groups}  # v2 遷移


def normalize(wl: Watchlist) -> Watchlist:
    """驗證(群組名 / code)+ 去重保序 + 群組成員補進 codes + 上限 —— 純函數,零 IO。

    抽出來是為了讓「請求的 canonical 形」與「現況的 canonical 形」可比較而不落檔
    (`server/watchlist_service.py` 的零寫早退);正規化規則只有這一份定義,
    `save_watchlist` 內部也走它。冪等:`normalize(normalize(x)) == normalize(x)`。
    """
    cleaned: list[Group] = []
    names: set[str] = set()
    for g in wl["groups"]:
        name = g["name"].strip()
        if not name or name in names:
            raise WatchlistError("BAD_GROUP")
        names.add(name)
        deduped: list[str] = []
        for code in g["codes"]:
            if not validate_code(code):
                raise WatchlistError("BAD_CODE")
            if code not in deduped:
                deduped.append(code)
        cleaned.append({"name": name, "codes": deduped})
    codes: list[str] = []
    for code in wl["codes"]:
        if not validate_code(code):
            raise WatchlistError("BAD_CODE")
        if code not in codes:
            codes.append(code)
    # 「加進群組」蘊含「加進自選」:群組成員缺席 codes 時補進尾端(語意無矛盾,不報錯)
    for code in union(cleaned):
        if code not in codes:
            codes.append(code)
    if len(codes) > WATCHLIST_LIMIT:
        raise WatchlistError("WATCHLIST_FULL")
    return {"codes": codes, "groups": cleaned}


def save_watchlist(path: Path, wl: Watchlist) -> Watchlist:
    """normalize(見上)+ atomic 寫 v3。"""
    canonical = normalize(wl)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {
                "_cache_version": _CACHE_VERSION,
                "codes": canonical["codes"],
                "groups": canonical["groups"],
            },
            ensure_ascii=False,
            indent=1,
        ),
    )
    return canonical
