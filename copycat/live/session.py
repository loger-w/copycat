"""台股期權交易時段窗(零 IO、不碰 ZMQ;tc4 選窗與 engine 跨盤偵測共用)。

時區事實(change-spec 5.1):日盤 台北 08:45–13:45 = UTC 00:45–05:45;夜盤 台北
15:00–次日 05:00 = UTC **同日** 07:00–21:00 — 兩時段各自完整落在單一 UTC 日,
窗字串不需跨日處理。TC4 REALTIME 的 TradeVolume 每時段重新起算(2026-07-20 夜盤
實測),回補窗與 REALTIME 同時段即可讓 stale-drop 基準自然對齊。
"""

from __future__ import annotations

import time

SessionKey = tuple[str, str]  # (ymd_utc, "day" | "night")

# 夜盤窗帶裕度 06–22:UTC 06–07 = 台北 14–15、21–22 = 台北 05–06 皆無成交,
# 不依賴 TC4 窗邊界含斥語意(未實測);日盤窗維持既有 00–06(SC-4 日盤不變)。
_WINDOWS = {"day": ("00", "06"), "night": ("06", "22")}


def session_key(now: time.struct_time | None = None) -> SessionKey:
    """當下(UTC)所屬時段:hour < 7 → 日盤,≥ 7 → 夜盤(含收盤後顯示「最近一場」)。"""
    t = time.gmtime() if now is None else now
    return (time.strftime("%Y%m%d", t), "day" if t.tm_hour < 7 else "night")


def session_window(key: SessionKey) -> tuple[str, str]:
    """時段 key → TC4 歷史/訂閱窗(StartTime, EndTime;UTC 小時字串)。"""
    ymd, kind = key
    start_h, end_h = _WINDOWS[kind]
    return (f"{ymd}{start_h}", f"{ymd}{end_h}")
