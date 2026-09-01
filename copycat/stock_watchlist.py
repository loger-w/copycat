"""個股自選清單持久化(design v4 §2.5;atomic JSON、無 DB — 專案慣例)。

v3(stock-ui-round5 §🔴-4):`{"codes": [...], "groups": [{"name", "codes"}]}`。
`codes` = 自選全體(有序)= 訂閱池;`groups` 只記成員關係。
**未分組 = codes − ∪groups 衍生不另存** —— 另存一份 ungrouped 會產生「同一檔同時在
未分組與某群組」的可違反不變式,而那個違反在畫面上是「同一檔出現兩次」= 靜默資料錯。

讀時遷移(不就地寫檔):v2(有 groups 無 codes)→ `codes = union(groups)`(畫面零差異);
v1(只有 codes)→ codes 原樣 + 零群組(v1 從來沒有群組概念,包成假的「自選」組是 v2
時代沒有未分組桶的權宜)。名為 `UNGROUPED_NAME` 的群組(舊版 bot 造得出)→ 成員先 union
進 codes 再丟組(discord-watchlist SC-6)。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TypedDict

from copycat.fileio import atomic_write_text

logger = logging.getLogger(__name__)


class Group(TypedDict):
    name: str
    codes: list[str]


class Watchlist(TypedDict):
    codes: list[str]
    groups: list[Group]


WATCHLIST_LIMIT = 150
_CACHE_VERSION = 3
# 4-6 位英數且至少一位數字(涵蓋 00637L 等字母尾碼 ETF;design r1-F6)。
# 存在性不在此驗 — SUBQUOTE 對不存在 symbol 照回 OK,推播健檢才是真閘。
_CODE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9]{4,6}$")

DEFAULT_PATH = Path("data") / "stock_watchlist.json"
# 未分組 = codes − ∪groups 的衍生桶,不是真群組 → 保留名,不得有同名群組
# (前端 WatchlistManagerDialog 的 UNGROUPED_LABEL 同值,跨檔契約)。
UNGROUPED_NAME = "未分組"


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


def with_group_replaced(wl: Watchlist, name: str, codes: list[str]) -> Watchlist:
    """整組覆蓋的純轉換(未 normalize;#173 盤前篩選 nightly 寫入的共用語意)。

    該群組成員 = `codes`(不存在自動建);原成員若不再屬於**任何**群組,同時自
    wl codes 移除 —— 不移的話每晚淘汰的檔會堆積在未分組桶。其他群組成員不受影響。
    呼叫端 = `WatchlistService.replace_group`(server 路徑,同鎖)與 CLI `screen --write`
    (server 未跑時的直接落檔)。
    """
    target = name.strip()
    groups: list[Group] = [{"name": g["name"], "codes": list(g["codes"])} for g in wl["groups"]]
    found = next((g for g in groups if g["name"] == target), None)
    old = set(found["codes"]) if found is not None else set()
    if found is None:
        groups.append({"name": target, "codes": list(codes)})
    else:
        found["codes"] = list(codes)
    still = {c for g in groups for c in g["codes"]}
    kept = [c for c in wl["codes"] if c not in old or c in still]
    return {"codes": kept, "groups": groups}


def fit_group_codes(
    wl: Watchlist, name: str, codes: list[str], limit: int = WATCHLIST_LIMIT
) -> tuple[list[str], int]:
    """`with_group_replaced` 前置的截位:把 `codes` 截到「覆蓋後總檔數 ≤ limit」。

    回 (入列 codes, 截掉數)。留存基底 = 覆蓋成**空組**後的自選(以 `with_group_replaced`
    自身算 —— 截位與轉換語意同源,漂不開;review F5/B3);已在基底裡的候選不吃新額度、
    無條件入列,截掉的是**排序尾段中尚不在自選**的新檔。兩條寫入路徑
    (`WatchlistService.replace_group` 的引擎端、CLI `screen --write`)共用這一份。
    """
    retained = set(with_group_replaced(wl, name, [])["codes"])
    out: list[str] = []
    dropped = 0
    for code in codes:
        if code in retained:
            out.append(code)
        elif len(retained) < limit:
            out.append(code)
            retained.add(code)
        else:
            dropped += 1
    return out, dropped


def load_watchlist(path: Path = DEFAULT_PATH) -> Watchlist:
    if not path.exists():
        return {"codes": [], "groups": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups: list[Group] = [
        {"name": str(g["name"]), "codes": list(g["codes"])} for g in payload.get("groups", [])
    ]
    codes = list(payload["codes"]) if "codes" in payload else union(groups)  # v3 / v1;else v2 遷移
    dropped = [g for g in groups if g["name"].strip() == UNGROUPED_NAME]
    if dropped:
        # 保留名群組是現行 bot 造得出的毒檔:只在寫路拒會讓所有寫入永久 BAD_GROUP。
        # 丟組前先把成員 union 進 codes(手改檔的組可能含 codes 外股號),再落回未分組衍生桶。
        for code in union(dropped):
            if code not in codes:
                codes.append(code)
        logger.warning("watchlist 含保留名群組,讀時丟棄:%s(%s)", path, [g["name"] for g in dropped])
        groups = [g for g in groups if g["name"].strip() != UNGROUPED_NAME]
    return {"codes": codes, "groups": groups}


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
        if not name or name in names or name == UNGROUPED_NAME:
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
