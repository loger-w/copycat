"""個股自選清單持久化(design v4 §2.5;atomic JSON、無 DB — 專案慣例)。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from copycat.fileio import atomic_write_text

WATCHLIST_LIMIT = 30
_CACHE_VERSION = 1
# 4-6 位英數且至少一位數字(涵蓋 00637L 等字母尾碼 ETF;design r1-F6)。
# 存在性不在此驗 — SUBQUOTE 對不存在 symbol 照回 OK,推播健檢才是真閘。
_CODE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9]{4,6}$")

DEFAULT_PATH = Path("data") / "stock_watchlist.json"


class WatchlistError(ValueError):
    """error code 進 HTTPException detail.error(跨檔契約)。"""


def validate_code(code: str) -> bool:
    return _CODE_RE.match(code) is not None


def load_watchlist(path: Path = DEFAULT_PATH) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("codes", []))


def save_watchlist(path: Path, codes: list[str]) -> list[str]:
    """驗證 + 去重(保序)+ atomic 寫;回傳實際存入清單。"""
    deduped: list[str] = []
    for code in codes:
        if not validate_code(code):
            raise WatchlistError("BAD_CODE")
        if code not in deduped:
            deduped.append(code)
    if len(deduped) > WATCHLIST_LIMIT:
        raise WatchlistError("WATCHLIST_FULL")
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {"_cache_version": _CACHE_VERSION, "codes": deduped},
            ensure_ascii=False,
            indent=1,
        ),
    )
    return deduped
