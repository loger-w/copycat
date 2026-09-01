"""自選清單的複合操作(design §6 — SC-8 / SC-11)。

「改自選」不是單一動作,而是**落檔 + 重設訂閱池 + 廣播**三件事的序列;而入口有三個
(前端 `PUT /api/stock/watchlist`、Discord `/watch add`、`/watch remove`)。三個入口各
自 read-modify-write 同一個檔 + 同一個引擎,沒有共用 lock 的話 Discord 加股與前端存檔
撞在一起會靜默丟掉其中一邊(後寫者以自己讀到的舊快照覆蓋)。本模組把序列與 lock 收成
單一定義,route 與 bot 都只呼叫這裡。

**鎖的範圍到落檔為止(X-3)**:`_commit` 在鎖內做「正規化 → 比對 → 落檔 → 取定序號」,
`_settle` 在**鎖外**做「訂閱 → 廣播」。`engine.set_watchlist` 逐檔走 ZMQ,TC4 故障時
單次最壞是數十檔 × 數十秒 —— 包在鎖內的話期間所有寫入一起堵死,而 Discord 的
interaction token 只有 15 分鐘。並發正確性改由 `seq` 在 engine 端保證(舊名單後到整段
跳過 = last-writer-wins),不再倚賴「訂閱也在鎖內」。

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
    with_group_replaced,
)

logger = logging.getLogger(__name__)

__all__ = ["WatchlistEngine", "WatchlistService"]


def _copy_groups(groups: list[Group]) -> list[Group]:
    """拷一層再改 —— 同一輪裡的 no-op 分支可能把那份現況原樣回給呼叫端,就地改會讓
    「沒落檔」與「回傳值」對不上(回的是改過的形,檔卻是舊的)。"""
    return [{"name": g["name"], "codes": list(g["codes"])} for g in groups]


class WatchlistEngine(Protocol):
    """StockEngine 結構子集(測試注入 fake)。"""

    #: **`seq` 無預設值**(N112):Protocol 這一側是生產契約面 —— 帶預設等於讓未來的
    #: caller 漏帶 keyword 時靜默拿到「不參與定序」的豁免,而那條路的失效樣態是
    #: 「剛加的股票又不見了」,零錯誤訊號。哨兵值見 `stock_engine.WATCHLIST_BOOT_SEQ`。
    async def set_watchlist(self, codes: list[str], *, seq: int) -> None: ...

    def _publish(self, msg: dict) -> None: ...


#: `_commit` 的產出:(現況 / 落檔結果, 這次有沒有改, 定序號)。
#: 沒改 → seq 為 None,`_settle` 直接放行(不訂閱、不廣播)。
_Pending = tuple[Watchlist, bool, int | None]


class WatchlistService:
    def __init__(self, path: Path, engine: WatchlistEngine) -> None:
        self._path = path
        self._engine = engine
        self._lock = asyncio.Lock()
        # 定序號在鎖內取(X-3);訂閱在鎖外送,抵達 engine 的順序不保證 —— engine
        # 靠這個號認出「舊名單後到」並整段跳過(last-writer-wins)。
        self._apply_seq = 0

    async def apply(self, wl: Watchlist) -> Watchlist:
        """整份取代(前端 PUT 的語意)。

        REST 契約不變(回 Watchlist):HTTP 沒有「沒變」這個回應形,前端拿到的一律是
        現況;changed flag 只有 Discord 那條路要分文案。
        """
        async with self._lock:
            pending = self._commit(wl)
        saved, _ = await self._settle(pending)
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
                # strip 後比對(A3):`normalize` 存的是 strip 後名,拿原字串比會讓
                # 「主力 」建出第二個組,兩組 normalize 後同名 → `BAD_GROUP`,
                # 使用者看到「群組名稱不合法」而那個名字明明合法。
                target_name = group.strip()
                target: Group | None = next(
                    (g for g in groups if g["name"].strip() == target_name), None
                )
                if target is None:
                    target = Group(name=target_name, codes=[])
                    groups.append(target)
                if code not in target["codes"]:
                    target["codes"].append(code)
            pending = self._commit({"codes": codes, "groups": groups})
        return await self._settle(pending)

    async def remove(self, code: str) -> tuple[Watchlist, bool]:
        """自自選與**所有**群組移除(留在任一群組就會被 normalize 補回 codes)。"""
        async with self._lock:
            current = load_watchlist(self._path)
            groups: list[Group] = [
                {"name": g["name"], "codes": [c for c in g["codes"] if c != code]}
                for g in current["groups"]
            ]
            codes = [c for c in current["codes"] if c != code]
            pending = self._commit({"codes": codes, "groups": groups})
        return await self._settle(pending)

    async def create_group(self, name: str) -> tuple[Watchlist, bool]:
        """建立空群組;strip 後同名已存在 → no-op(不報錯 —— 使用者的意圖已經成立)。

        保留名 / 空名不在此判,交 `_commit` 內的 `normalize` 拒(`BAD_GROUP`):
        群組名的合法性只有 `stock_watchlist.normalize` 一份定義。
        """
        async with self._lock:
            current = self._require_current()
            target = name.strip()
            if any(g["name"] == target for g in current["groups"]):
                return current, False
            groups = _copy_groups(current["groups"])
            groups.append({"name": target, "codes": []})  # 存 strip 後名(比對基準同一份)
            pending = self._commit({"codes": list(current["codes"]), "groups": groups})
        return await self._settle(pending)

    async def delete_group(self, name: str) -> tuple[Watchlist, bool]:
        """刪群組;codes 不動 —— 成員落回未分組衍生桶(刪群組不等於刪股票)。"""
        async with self._lock:
            current = self._require_current()
            target = name.strip()
            if not any(g["name"] == target for g in current["groups"]):
                raise WatchlistError("GROUP_NOT_FOUND")
            groups = [g for g in _copy_groups(current["groups"]) if g["name"] != target]
            pending = self._commit({"codes": list(current["codes"]), "groups": groups})
        return await self._settle(pending)

    async def rename_group(self, old: str, new: str) -> tuple[Watchlist, bool]:
        """改名;新名撞既有名 / 保留名 / 空名 → `normalize` 拒(`BAD_GROUP`)。"""
        async with self._lock:
            current = self._require_current()
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
            pending = self._commit({"codes": list(current["codes"]), "groups": groups})
        return await self._settle(pending)

    async def replace_group(self, name: str, codes: list[str]) -> tuple[Watchlist, bool]:
        """整組覆蓋(盤前篩選 nightly 寫入,#173):該群組成員 = `codes`(不存在自動建);
        原成員若不再屬於**任何**群組,同時自 wl codes 移除 —— 不移的話每晚淘汰的檔會
        堆積在未分組桶,一週就把上限塞滿。

        邊界刻意接受:使用者手動把某檔留在未分組桶、而它恰好也在本群組 —— 覆蓋時該檔
        自本群組淘汰即一併離開自選(「本群組每日覆蓋、手動增刪會被洗掉」的知情語意,
        #173 Q6 拍板)。轉換語意單一份在 `stock_watchlist.with_group_replaced`
        (CLI `screen --write` 同用);其他群組的成員不受影響(仍在群組 = 不移)。
        """
        async with self._lock:
            current = self._require_current()
            pending = self._commit(with_group_replaced(current, name, codes))
        return await self._settle(pending)

    async def ungroup(self, code: str, group: str) -> tuple[Watchlist, bool]:
        """自該群組移出;wl codes 不動 —— 移出群組不等於移出自選。"""
        async with self._lock:
            current = self._require_current()
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
            pending = self._commit({"codes": list(current["codes"]), "groups": groups})
        return await self._settle(pending)

    async def current(self) -> Watchlist:
        """現況(canonical 形);壞檔回空清單。Discord `/watch list` 的讀取入口。

        持同一把 lock:讀到寫到一半的中間態雖不可能(落檔是 atomic),但讀跟改共用一把
        鎖才不會出現「list 顯示的是 add 尚未完成前的樣子」這種讓人困惑的交錯。
        """
        async with self._lock:
            return self._snapshot()

    def _commit(self, wl: Watchlist) -> _Pending:
        """**持 lock 呼叫**。正規化 → 與現況比對 → 落檔 → 取定序號。

        鎖內到此為止(X-3):訂閱與廣播由呼叫端在**鎖外**交給 `_settle`。
        `engine.set_watchlist` 逐檔走 ZMQ,TC4 故障時單次最壞是數十檔 × 數十秒;
        留在鎖內的話期間所有 `/watch` 與前端 PUT 全部堆積,而 Discord 的 interaction
        token 只有 15 分鐘 —— 使用者看到的是「應用程式沒有回應」。

        回傳的 bool = 「這次真的改了嗎」。**唯一事實點就是這裡的比對** —— 呼叫端自己
        比對會多一次讀檔、也就多一個 TOCTOU 窗;而 Discord 的 no-op 文案(「已在自選」
        vs「已加入自選」)必須跟「有沒有落檔」完全一致,否則回報與實況會對不上。
        """
        desired = normalize(wl)  # 非法碼 / 超上限在此拋,尚未落檔
        if desired == self._current_canonical():
            return desired, False, None
        saved = save_watchlist(self._path, desired)
        self._apply_seq += 1  # 落檔順序 = 定序順序(同在鎖內,不會交錯)
        return saved, True, self._apply_seq

    async def _settle(self, pending: _Pending) -> tuple[Watchlist, bool]:
        """**鎖外**的副作用:訂閱 + 廣播。六個公開方法共用這一份。

        呼叫端仍 `await` —— 收斂的是**鎖凸出**,不是自己這一次的等待:改成
        fire-and-forget 的話 route 回應時訂閱可能還沒掛上,前端拿到的第一份 snapshot
        會缺。並發安全由 `seq` 在 engine 端負責(舊名單後到整段跳過)。

        收斂範圍要誠實:X-3 解掉的是 **service 這把鎖**的堆積(`current()` 讀路、
        群組操作的驗證與落檔不再排在訂閱迴圈後面);N111 再把 engine 端 `_pool_lock`
        從「整段迴圈一鎖」改成**逐檔取鎖**,第二個寫入者的等待上界從「整段迴圈」
        (150 檔 × 10 s,上限)降到「當下這一檔」(≤ 10 s)。**仍不是零等待**:ZMQ IO 還在
        鎖內,要完全移出得引進 per-code in-flight 狀態(新的不變式),見 next-time。
        """
        saved, changed, seq = pending
        if not changed:
            return saved, False
        if seq is None:
            # `_commit` 的不變式:changed=True 必帶號。走到這裡代表**檔已經改了**而
            # 訂閱池與畫面不會跟上 —— 靜默丟棄使用者的變更是最壞的失效樣態,所以這條
            # 「不該發生」的路要有訊號(review ST3)。行為維持不訂閱不廣播:帶著 None
            # 往下送只會在 engine 端變成另一種靜默。
            logger.error("watchlist 已落檔卻沒有定序號(_commit 不變式被打破),本次不訂閱不廣播")
            return saved, False
        await self._engine.set_watchlist(saved["codes"], seq=seq)
        self._engine._publish({"type": "watchlist_changed"})
        return saved, True

    def _require_current(self) -> Watchlist:
        """群組方法的現況基準;檔不可用 → 大聲拒絕、零寫(v3 A1/B1)。

        群組操作全是 **read-modify-write**:它們只帶「差異」(建一個組 / 刪一個組),
        現況必須是真的現況。壞檔視同空快照的話,`create_group` 會拿一份空名單當底
        寫回去 = **靜默清空整份自選**,而使用者只看到「已建立群組」;
        `delete/rename/ungroup` 則回 `GROUP_NOT_FOUND`,把「檔壞了」講成「你打錯名字」。

        整份取代的 `apply`(前端存檔)不走這裡 —— 它自帶完整名單,正是壞檔的自癒路徑。
        """
        current = self._current_canonical()
        if current is None:
            raise WatchlistError("WATCHLIST_UNAVAILABLE")
        return current

    def _snapshot(self) -> Watchlist:
        """現況 canonical 形;不可用(壞檔)視同空 —— **唯讀路徑專用**(`current()`)。

        讀路可以降級成空:`/watch list` 顯示「自選清單目前是空的」雖然不精確,但不會
        毀掉任何資料。寫路不行,見 `_require_current`。
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
