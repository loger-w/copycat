"""自選清單的複合操作(design §6 — SC-8 / SC-11)。

「改自選」不是單一動作,而是**落檔 + 重設訂閱池 + 廣播**三件事的序列;而入口有三個
(前端 `PUT /api/stock/watchlist`、Discord `/watch add`、`/watch remove`)。三個入口各
自 read-modify-write 同一個檔 + 同一個引擎,沒有共用 lock 的話 Discord 加股與前端存檔
撞在一起會靜默丟掉其中一邊(後寫者以自己讀到的舊快照覆蓋)。本模組把序列與 lock 收成
單一定義,route 與 bot 都只呼叫這裡。

**canonical 零寫早退(§6 R18)**:比較「請求正規化後的形」與「現況正規化後的形」,
相同就不落檔、不 `set_watchlist`、不廣播。這是既有 PUT 的行為改動(🔴)—— 舊碼對同
內容 PUT 照樣跑一輪 `set_watchlist`,而那條路會對整份名單做 UNSUB/SUB;前端每次存檔
(即使沒改東西)都讓所有自選股斷訂一次,盤中就是一排「-」。早退分支回傳的是**比較時
算出的那份現況 canonical 形**(R2-10),與落檔路徑同形 —— 呼叫端不必分辨走了哪條。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol

from copycat.stock_watchlist import (
    Group,
    Watchlist,
    WatchlistError,
    load_watchlist,
    normalize,
    save_watchlist,
)

logger = logging.getLogger(__name__)

__all__ = ["WatchlistEngine", "WatchlistService"]


def _copy_groups(groups: list[Group]) -> list[Group]:
    """拷一層再改 —— 同一輪裡的 no-op 分支可能把那份現況原樣回給呼叫端,就地改會讓
    「沒落檔」與「回傳值」對不上(回的是改過的形,檔卻是舊的)。"""
    return [{"name": g["name"], "codes": list(g["codes"])} for g in groups]


class WatchlistEngine(Protocol):
    """StockEngine 結構子集(測試注入 fake)。"""

    async def set_watchlist(self, codes: list[str]) -> None: ...

    def _publish(self, msg: dict) -> None: ...


class WatchlistService:
    def __init__(self, path: Path, engine: WatchlistEngine) -> None:
        self._path = path
        self._engine = engine
        self._lock = asyncio.Lock()

    async def apply(self, wl: Watchlist) -> Watchlist:
        """整份取代(前端 PUT 的語意)。

        REST 契約不變(回 Watchlist):HTTP 沒有「沒變」這個回應形,前端拿到的一律是
        現況;changed flag 只有 Discord 那條路要分文案。
        """
        async with self._lock:
            saved, _ = await self._commit(wl)
            return saved

    async def add(self, code: str, group: str | None = None) -> tuple[Watchlist, bool]:
        """加進自選;帶 group 則同時入該群組(群組不存在自動建)。"""
        async with self._lock:
            current = load_watchlist(self._path)
            codes = list(current["codes"])
            if code not in codes:
                codes.append(code)
            groups: list[Group] = [
                {"name": g["name"], "codes": list(g["codes"])} for g in current["groups"]
            ]
            if group is not None:
                target: Group | None = next((g for g in groups if g["name"] == group), None)
                if target is None:
                    target = Group(name=group, codes=[])
                    groups.append(target)
                if code not in target["codes"]:
                    target["codes"].append(code)
            return await self._commit({"codes": codes, "groups": groups})

    async def remove(self, code: str) -> tuple[Watchlist, bool]:
        """自自選與**所有**群組移除(留在任一群組就會被 normalize 補回 codes)。"""
        async with self._lock:
            current = load_watchlist(self._path)
            groups: list[Group] = [
                {"name": g["name"], "codes": [c for c in g["codes"] if c != code]}
                for g in current["groups"]
            ]
            codes = [c for c in current["codes"] if c != code]
            return await self._commit({"codes": codes, "groups": groups})

    async def create_group(self, name: str) -> tuple[Watchlist, bool]:
        """建立空群組;strip 後同名已存在 → no-op(不報錯 —— 使用者的意圖已經成立)。

        保留名 / 空名不在此判,交 `_commit` 內的 `normalize` 拒(`BAD_GROUP`):
        群組名的合法性只有 `stock_watchlist.normalize` 一份定義。
        """
        async with self._lock:
            current = self._snapshot()
            target = name.strip()
            if any(g["name"] == target for g in current["groups"]):
                return current, False
            groups = _copy_groups(current["groups"])
            groups.append({"name": name, "codes": []})
            return await self._commit({"codes": list(current["codes"]), "groups": groups})

    async def delete_group(self, name: str) -> tuple[Watchlist, bool]:
        """刪群組;codes 不動 —— 成員落回未分組衍生桶(刪群組不等於刪股票)。"""
        async with self._lock:
            current = self._snapshot()
            target = name.strip()
            if not any(g["name"] == target for g in current["groups"]):
                raise WatchlistError("GROUP_NOT_FOUND")
            groups = [g for g in _copy_groups(current["groups"]) if g["name"] != target]
            return await self._commit({"codes": list(current["codes"]), "groups": groups})

    async def rename_group(self, old: str, new: str) -> tuple[Watchlist, bool]:
        """改名;新名撞既有名 / 保留名 / 空名 → `normalize` 拒(`BAD_GROUP`)。"""
        async with self._lock:
            current = self._snapshot()
            src = old.strip()
            dst = new.strip()
            if not any(g["name"] == src for g in current["groups"]):
                raise WatchlistError("GROUP_NOT_FOUND")
            if src == dst:
                return current, False
            groups = _copy_groups(current["groups"])
            for g in groups:
                if g["name"] == src:
                    g["name"] = dst
            return await self._commit({"codes": list(current["codes"]), "groups": groups})

    async def ungroup(self, code: str, group: str) -> tuple[Watchlist, bool]:
        """自該群組移出;wl codes 不動 —— 移出群組不等於移出自選。"""
        async with self._lock:
            current = self._snapshot()
            target = group.strip()
            found = next((g for g in current["groups"] if g["name"] == target), None)
            if found is None:
                raise WatchlistError("GROUP_NOT_FOUND")
            if code not in found["codes"]:
                return current, False
            groups = _copy_groups(current["groups"])
            for g in groups:
                if g["name"] == target:
                    g["codes"] = [c for c in g["codes"] if c != code]
            return await self._commit({"codes": list(current["codes"]), "groups": groups})

    async def current(self) -> Watchlist:
        """現況(canonical 形);壞檔回空清單。Discord `/watch list` 的讀取入口。

        持同一把 lock:讀到寫到一半的中間態雖不可能(落檔是 atomic),但讀跟改共用一把
        鎖才不會出現「list 顯示的是 add 尚未完成前的樣子」這種讓人困惑的交錯。
        """
        async with self._lock:
            return self._snapshot()

    async def _commit(self, wl: Watchlist) -> tuple[Watchlist, bool]:
        """持 lock 呼叫。正規化 → 與現況比對 → 落檔 + 訂閱 + 廣播。

        回傳的 bool = 「這次真的改了嗎」。**唯一事實點就是這裡的比對** —— 呼叫端自己
        比對會多一次讀檔、也就多一個 TOCTOU 窗;而 Discord 的 no-op 文案(「已在自選」
        vs「已加入自選」)必須跟「有沒有落檔」完全一致,否則回報與實況會對不上。
        """
        desired = normalize(wl)  # 非法碼 / 超上限在此拋,尚未落檔
        if desired == self._current_canonical():
            return desired, False
        saved = save_watchlist(self._path, desired)
        await self._engine.set_watchlist(saved["codes"])
        self._engine._publish({"type": "watchlist_changed"})
        return saved, True

    def _snapshot(self) -> Watchlist:
        """現況 canonical 形;不可用(壞檔)視同空 —— 新方法的存在性判定基準。

        壞檔下「群組不存在」是誠實的答案:讀不到的檔裡沒有任何群組可操作,
        `delete/rename/ungroup` 因此拋 `GROUP_NOT_FOUND` 且零寫;`create_group` 則
        以空為底覆蓋回去(與 `apply` 的自癒路徑同語意)。
        """
        return self._current_canonical() or {"codes": [], "groups": []}

    def _current_canonical(self) -> Watchlist | None:
        """現況的 canonical 形;檔**不可用**時回 None(= 一定不相等 → 照常落檔覆蓋)。

        壞檔不該讓一份合法的新名單被拒 —— 請求自己的合法性由 `_commit` 先驗過了。

        「不可用」不只是 `WatchlistError`(MFS-3):半寫入 / 手改壞的檔會在 `load_watchlist`
        就炸 —— 非 JSON 是 `ValueError`、群組缺鍵是 `KeyError`、`codes` 不是 list 是
        `TypeError`、讀不到是 `OSError`。這些穿出去會讓 PUT 變 500,而**自癒的唯一路徑
        正是那個 PUT**:檔壞了就再也修不好,只能手動刪檔。
        """
        try:
            return normalize(load_watchlist(self._path))
        except (WatchlistError, ValueError, KeyError, TypeError, OSError) as e:
            logger.warning("watchlist 現況不可用,視為需覆寫(%s):%s", self._path, e)
            return None
