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
        """整份取代(前端 PUT 的語意)。"""
        async with self._lock:
            return await self._commit(wl)

    async def add(self, code: str, group: str | None = None) -> Watchlist:
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

    async def remove(self, code: str) -> Watchlist:
        """自自選與**所有**群組移除(留在任一群組就會被 normalize 補回 codes)。"""
        async with self._lock:
            current = load_watchlist(self._path)
            groups: list[Group] = [
                {"name": g["name"], "codes": [c for c in g["codes"] if c != code]}
                for g in current["groups"]
            ]
            codes = [c for c in current["codes"] if c != code]
            return await self._commit({"codes": codes, "groups": groups})

    async def _commit(self, wl: Watchlist) -> Watchlist:
        """持 lock 呼叫。正規化 → 與現況比對 → 落檔 + 訂閱 + 廣播。"""
        desired = normalize(wl)  # 非法碼 / 超上限在此拋,尚未落檔
        if desired == self._current_canonical():
            return desired
        saved = save_watchlist(self._path, desired)
        await self._engine.set_watchlist(saved["codes"])
        self._engine._publish({"type": "watchlist_changed"})
        return saved

    def _current_canonical(self) -> Watchlist | None:
        """現況的 canonical 形;檔內容不合法時回 None(= 一定不相等 → 照常落檔覆蓋)。

        壞檔不該讓一份合法的新名單被拒 —— 請求自己的合法性由 `_commit` 先驗過了。
        """
        try:
            return normalize(load_watchlist(self._path))
        except WatchlistError:
            logger.warning("watchlist 現況不符正規化規則,視為需覆寫:%s", self._path)
            return None
