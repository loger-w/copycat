"""個股自選清單持久化(design v4 §2.5;atomic JSON、無 DB — 專案慣例)。

v2(stock-ui-upgrade SC-6):群組 schema `{"groups": [{"name", "codes"}]}`;
v1(`{"codes": [...]}`)讀時遷移為單一「自選」群組。上限以跨群組聯集計。
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


WATCHLIST_LIMIT = 30
_CACHE_VERSION = 2
# 4-6 位英數且至少一位數字(涵蓋 00637L 等字母尾碼 ETF;design r1-F6)。
# 存在性不在此驗 — SUBQUOTE 對不存在 symbol 照回 OK,推播健檢才是真閘。
_CODE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9]{4,6}$")

DEFAULT_PATH = Path("data") / "stock_watchlist.json"


class WatchlistError(ValueError):
    """error code 進 HTTPException detail.error(跨檔契約)。"""


def validate_code(code: str) -> bool:
    return _CODE_RE.match(code) is not None


def load_watchlist_groups(path: Path = DEFAULT_PATH) -> list[Group]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "groups" in payload:
        return [
            {"name": str(g["name"]), "codes": list(g["codes"])} for g in payload["groups"]
        ]
    codes = list(payload.get("codes", []))
    # v1 讀時遷移(不就地寫檔,下次 save 落 v2)
    return [{"name": "自選", "codes": codes}] if codes else []


def union(groups: list[Group]) -> list[str]:
    """跨群組聯集,首見序去重。"""
    seen: list[str] = []
    for g in groups:
        for code in g["codes"]:
            if code not in seen:
                seen.append(code)
    return seen


def save_watchlist_groups(path: Path, groups: list[Group]) -> list[Group]:
    """驗證(code / 群組名)+ 群組內去重(保序)+ 聯集上限 + atomic 寫 v2。"""
    cleaned: list[Group] = []
    names: set[str] = set()
    for g in groups:
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
    if len(union(cleaned)) > WATCHLIST_LIMIT:
        raise WatchlistError("WATCHLIST_FULL")
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {"_cache_version": _CACHE_VERSION, "groups": cleaned},
            ensure_ascii=False,
            indent=1,
        ),
    )
    return cleaned
