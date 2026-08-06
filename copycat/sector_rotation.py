"""類股輪動純函式層(零 IO)—— SC-1。

邏輯自 neigui 搬移(**邏輯全等、實作適配 copycat**),來源:
- `backend/services/industry_chain.py:114-128`:`_rows_to_map`(→ 公開
  `rows_to_chain_map`)
- `backend/services/market_today.py:231-312`:`_dedup_ids` / `_group_stats` /
  `compute_sector_rotation`(含 `_index_to_universe_map`,:30-31)
- `backend/services/market_today.py:425-470`:`compute_sector_members`

**無刻意偏離**:數值口徑(avg 為算術平均、vol_ratio 為 Σ總量/Σ昨量)、排序鍵、
去重語意、None 邊界全部照抄;實作面只有三處適配 —— 私有 `_rows_to_map` 改公開
`rows_to_chain_map`(copycat 的取數/落檔層在別的模組)、加型別別名 `ChainMap`、
docstring 改用專案慣例。等價性由 `tests/test_sector_rotation.py`(neigui
`test_market_today.py:239-360/:407-447` 等價搬移)把關。

`universe_rows` = `market_breadth.assemble_universe` 輸出(需 `stock_id` /
`change_rate` / `total_volume` / `yesterday_volume` / `total_amount`),**不是**
`compute_breadth` 的 rows_out —— 後者的量欄已收成 `volume_ratio`,分子分母不可再
同步剔除。

本模組不做任何 IO;chain 取數在 `copycat/server/breadth_fetch.py`、落檔在
`copycat/server/chain_store.py`,編排在 `copycat/server/breadth_engine.py`。
"""

from __future__ import annotations

#: `{industry: {sub_industry: [stock_id, ...]}}` —— FinMind
#: `TaiwanStockIndustryChain` 的 N-to-M 對映展開形。
ChainMap = dict[str, dict[str, list[str]]]


def rows_to_chain_map(rows: list[dict]) -> ChainMap:
    """chain rows → `ChainMap`(neigui `_rows_to_map` 逐行等價)。

    `stock_id` / `industry` / `sub_industry` **任一 falsy → 整列丟棄**(不進 `""`
    桶):空字串桶會在前端長出一個無名產業,而且 `sub` 空字串桶與「未指定 sub」
    的 drill-down 語意會撞在一起。
    同 `(industry, sub_industry)` 內同 `stock_id` 只留一次(N-to-M 對映本身不該
    重複,防上游髒資料重複列);跨 sub / 跨 industry 的重複是正常對映,不去重。
    """
    out: ChainMap = {}
    for row in rows:
        sid = row.get("stock_id")
        industry = row.get("industry")
        sub = row.get("sub_industry")
        if not sid or not industry or not sub:
            continue
        sub_map = out.setdefault(industry, {})
        members = sub_map.setdefault(sub, [])
        if sid not in members:
            members.append(sid)
    return out


def _index_to_universe_map(universe_rows: list[dict]) -> dict[str, dict]:
    return {r["stock_id"]: r for r in universe_rows if r.get("stock_id")}


def _dedup_ids(stock_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for sid in stock_ids:
        if sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _group_stats(stock_ids: list[str], universe_by_id: dict[str, dict]) -> dict | None:
    """一群 stock_id → `{members, avg_change_rate, vol_ratio}`;成員 0 → None。

    - `members` = `change_rate` 非 None 的成員數(universe 查無的代號同樣剔除)。
    - vol_ratio **分子分母同步剔除**:缺 `total_volume` 或 `yesterday_volume` 的股
      整檔不進 Σ —— 只剔分母會讓量比被高估。
    - 剔除後分母 0 → `vol_ratio` None(members 與 avg 仍成立)。
    """
    member_rows: list[dict] = []
    for sid in _dedup_ids(stock_ids):
        row = universe_by_id.get(sid)
        if row is None or row.get("change_rate") is None:
            continue
        member_rows.append(row)

    if not member_rows:
        return None

    avg_change_rate = sum(r["change_rate"] for r in member_rows) / len(member_rows)

    vol_num = 0.0
    vol_den = 0.0
    for r in member_rows:
        tv = r.get("total_volume")
        yv = r.get("yesterday_volume")
        if tv is None or yv is None:
            continue
        vol_num += tv
        vol_den += yv
    vol_ratio = (vol_num / vol_den) if vol_den else None

    return {
        "members": len(member_rows),
        "avg_change_rate": avg_change_rate,
        "vol_ratio": vol_ratio,
    }


def compute_sector_rotation(
    universe_rows: list[dict],
    chain_map: ChainMap | None,
) -> dict | None:
    """產業主列表 + 展開子產業。`chain_map` None / 空 → None(面板 degraded)。

    industry 層 = 該產業所有 sub 的 stock_id **聯集去重**(同產業內一票);sub 層
    各自獨立(跨產業 / 跨子產業重複允許)。成員 0 的群組略過(幽靈 industry 天然
    不出現)。industries 與 subs 均按 `avg_change_rate` desc 排序。
    """
    if not chain_map:
        return None

    universe_by_id = _index_to_universe_map(universe_rows)
    industries: list[dict] = []

    for industry_name, sub_map in chain_map.items():
        union_ids: list[str] = []
        for sub_ids in sub_map.values():
            union_ids.extend(sub_ids)
        industry_stats = _group_stats(union_ids, universe_by_id)
        if industry_stats is None:
            continue

        subs: list[dict] = []
        for sub_name, sub_ids in sub_map.items():
            sub_stats = _group_stats(sub_ids, universe_by_id)
            if sub_stats is None:
                continue
            subs.append({"name": sub_name, **sub_stats})
        subs.sort(key=lambda s: s["avg_change_rate"], reverse=True)

        industries.append({"name": industry_name, **industry_stats, "subs": subs})

    industries.sort(key=lambda i: i["avg_change_rate"], reverse=True)
    return {"industries": industries}


def compute_sector_members(
    universe_rows: list[dict],
    chain_map: ChainMap | None,
    name_map: dict[str, str],
    industry: str,
    sub_industry: str | None = None,
) -> dict | None:
    """成員股 drill-down;未知 industry / sub_industry → None(呼叫端轉 404)。

    `sub_industry` None → 該產業所有 sub 聯集去重。成員 entry 含 `vol_ratio` /
    `total_amount`,按 `change_rate` desc 排(None 最後)。
    `vol_ratio` 缺欄或分母 0 → None(此處是逐檔比值,非群組 Σ)。
    """
    if not chain_map or industry not in chain_map:
        return None

    sub_map = chain_map[industry]
    if sub_industry is not None:
        if sub_industry not in sub_map:
            return None
        stock_ids = sub_map[sub_industry]
    else:
        stock_ids = []
        for ids in sub_map.values():
            stock_ids.extend(ids)

    universe_by_id = _index_to_universe_map(universe_rows)
    members: list[dict] = []
    for sid in _dedup_ids(stock_ids):
        row = universe_by_id.get(sid)
        if row is None:
            continue
        tv = row.get("total_volume")
        yv = row.get("yesterday_volume")
        vol_ratio = (tv / yv) if (tv is not None and yv) else None
        members.append(
            {
                "stock_id": sid,
                "name": name_map.get(sid) or sid,
                "change_rate": row.get("change_rate"),
                "vol_ratio": vol_ratio,
                "total_amount": row.get("total_amount"),
            }
        )

    members.sort(key=lambda m: (m["change_rate"] is None, -(m["change_rate"] or 0)))
    return {"industry": industry, "sub_industry": sub_industry, "members": members}
