"""江波圖的分鐘序列狀態機(零 IO;design v2 §4;SC-1)。

per-leg `{offset: 收盤毫點}`,offset = 當場盤別窗內的分鐘位移(`river_models.offset_of`)。

三條規則決定了它為什麼長這樣:

1. **同分鐘 last-write-wins**:一分鐘內多筆成交,圖上那一點的語意是「該分鐘收盤」。
   唯一例外是收盤補正窗(`river_models.close_clamp_rank`):`end+2` 起(13:46– / 05:01–)
   的取樣不覆寫已有值的 end 格,否則收盤後的殘留成交會蓋掉真收盤價。
2. **換場清空**:盤別或 UTC 日期一變,舊場的點與新場的 x 軸無關(窗也不同)。
   `set_session` 讓「還沒有任何報價」的情形也能換窗 —— TC4 掛掉時 `push` 永不被呼叫,
   窗若只靠 push 更新,畫面會停在上一場的軸上。
3. **回補只補空缺**:1K 回補資料延遲數十秒,覆蓋 live 值會讓當前分鐘的價格倒退。

`snapshot.last` 取**最大 offset** 的值(不是最後寫入的值):回補完成後,「現價」應該是
時間軸上最後那一分鐘,而回補的寫入順序與時間序無關。`delta` 反過來只帶**最後寫入**的那
一分鐘 —— 它是給每秒推播用的增量,不是狀態查詢。

**執行緒**:所有方法僅由 event loop thread 呼叫(推播 handler、tick task、回補結果 apply
都已經回到 loop)。若日後把 apply 移進 worker thread,dict 寫入就需要鎖。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from copycat.live.river_models import close_clamp_rank, offset_of, window_bounds

__all__ = ["RiverState", "SessionKey"]

SessionKey = tuple[str, str]  # (ymd_utc, "day" | "night");copycat.live.session 同型


class RiverState:
    def __init__(self, leg_keys: Sequence[str], *, base: str) -> None:
        self._base = base
        self._keys = list(leg_keys)
        self._minutes: dict[str, dict[int, int]] = {k: {} for k in self._keys}
        self._last_write: dict[str, tuple[int, int] | None] = {k: None for k in self._keys}
        self._session: SessionKey | None = None

    # ---- 寫入 ----

    def set_session(self, session: SessionKey) -> None:
        """盤別(含 UTC 日)變更 → 全腿清空並換窗;相同則無作用。"""
        if self._session == session:
            return
        if self._session is not None:
            for minutes in self._minutes.values():
                minutes.clear()
            for key in self._last_write:
                self._last_write[key] = None
        self._session = session

    def push(self, key: str, minute_end: int, price_milli: int, session: SessionKey) -> None:
        """live 取樣:換場先清空,再依 offset 分桶(窗外丟棄;未知腿忽略)。"""
        self.set_session(session)
        minutes = self._minutes.get(key)
        if minutes is None:
            return
        offset = offset_of(minute_end, session[1])
        if offset is None:
            return
        # 收盤 clamp 第 2 分鐘起(13:46– / 05:01–)不覆寫已有值的 end 格:那些是收盤後
        # 的殘留取樣。end+1 = 收盤撮合那一分鐘,必須寫得進來(base 腿每秒取樣在 13:44:xx
        # 就先填了 end 格)。end 格還空著時照寫 —— tick 稀疏沒落 end 格時它就是最佳近似。
        # 守門刻意排在 `set_session` **之後**:換場後 end 格是空的,新場第一筆(哪怕名次
        # 大)就是它當下最好的近似;順序顛倒會拿上一場的 end 格擋掉新場第一筆。
        # `rank is not None` 是防禦性冗餘 —— 兩者共用 `_expand` 與同一個 clamp 寬度,
        # rank 為 None 的分鐘 `offset_of` 也回 None,上面早就 return 了。留著是因為
        # 「兩函式恆同時失效」是耦合假設而非型別保證,拆尺時這裡不該變成 TypeError。
        rank = close_clamp_rank(minute_end, session[1])
        if rank is not None and rank >= 2 and offset in minutes:
            return
        minutes[offset] = price_milli
        self._last_write[key] = (offset, price_milli)

    def apply_backfill(self, key: str, rows: list[tuple[int, int]], session: SessionKey) -> int:
        """1K 回補:**只填尚無值的 offset**;session 與當前不符 → 全數丟棄回 0。

        回傳實際填入筆數(供 log 與測試斷言;0 = 該腿無回補可用)。
        """
        if self._session is not None and session != self._session:
            return 0
        self.set_session(session)
        minutes = self._minutes.get(key)
        if minutes is None:
            return 0
        filled = 0
        for minute_end, price_milli in rows:
            offset = offset_of(minute_end, session[1])
            if offset is None or offset in minutes:
                continue
            minutes[offset] = price_milli
            filled += 1
        return filled

    # ---- 讀出 ----

    def _kind(self) -> str:
        return self._session[1] if self._session is not None else "day"

    def _window(self) -> dict[str, int]:
        start, end = window_bounds(self._kind())
        return {"start_min": start, "end_min": end}

    def snapshot(self, labels: Mapping[str, str], seq: int) -> dict:
        """全量(REST / WS 首則):`last` = 最大 offset 的值。"""
        legs: dict[str, dict] = {}
        for key in self._keys:
            minutes = self._minutes[key]
            last_minute = max(minutes) if minutes else None
            legs[key] = {
                "label": labels.get(key, key),
                "minutes": dict(minutes),
                "last": minutes[last_minute] if last_minute is not None else None,
                "last_minute": last_minute,
            }
        return {
            "type": "river",
            "seq": seq,
            "session": self._kind(),
            "base": self._base,
            "window": self._window(),
            "legs": legs,
        }

    def delta(self, seq: int) -> dict:
        """每秒增量:各腿最後**寫入**的那一分鐘;該腿本場尚無 live 點 → None。

        `[phase-3 補註]` 不吃 `labels`(design/PLAN 原寫 `delta(labels, seq)` 以求與 snapshot
        同簽名)—— delta 只帶點不帶名,留著會是永不使用的參數;腿名由 snapshot 提供,
        前端本來就先收 snapshot 才收 delta。
        """
        return {
            "type": "river_delta",
            "seq": seq,
            "session": self._kind(),
            "window": self._window(),
            "legs": {
                key: ({"m": write[0], "p": write[1]} if write is not None else None)
                for key, write in self._last_write.items()
            },
        }
