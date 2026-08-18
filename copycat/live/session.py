"""台股期權交易時段窗(零 IO、不碰 ZMQ;tc4 選窗與 engine 跨盤偵測共用)。

時區事實(change-spec 5.1):日盤 台北 08:45–13:45 = UTC 00:45–05:45;夜盤 台北
15:00–次日 05:00 = UTC **同日** 07:00–21:00 — 兩時段各自完整落在單一 UTC 日,
窗字串不需跨日處理。TC4 REALTIME 的 TradeVolume 每時段重新起算(2026-07-20 夜盤
實測),回補窗與 REALTIME 同時段即可讓 stale-drop 基準自然對齊。
"""

from __future__ import annotations

import datetime as _dt
import time

SessionKey = tuple[str, str]  # (ymd_utc, "day" | "night")

#: 台北牆鐘的實際交易時段(日盤 / 夜盤;夜盤跨午夜)。`session_key` 的 UTC 分界是
#: 「顯示最近一場」語意(收盤後仍歸該場),這裡要的是「**現在真的在盤中嗎**」。
_TXO_DAY = (_dt.time(8, 45), _dt.time(13, 45))
_TXO_NIGHT = (_dt.time(15, 0), _dt.time(5, 0))

# 夜盤窗帶裕度 06–22:UTC 06–07 = 台北 14–15、21–22 = 台北 05–06 皆無成交,
# 不依賴 TC4 窗邊界含斥語意(未實測);日盤窗維持既有 00–06(SC-4 日盤不變)。
_WINDOWS = {"day": ("00", "06"), "night": ("06", "22")}


def session_key(now: time.struct_time | None = None) -> SessionKey:
    """當下(UTC)所屬時段:hour < 7 → 日盤,≥ 7 → 夜盤(含收盤後顯示「最近一場」)。"""
    t = time.gmtime() if now is None else now
    return (time.strftime("%Y%m%d", t), "day" if t.tm_hour < 7 else "night")


def in_txo_session(now: _dt.time | None = None) -> bool:
    """現在是否在台指期權盤中(TXO session 的 `heal_active` 閘)。

    盤外零推播是正常的,重掛只會 churn TC4 上游 —— 自癒必須有時段閘。
    夜盤跨午夜,故以「≥ 15:00 或 ≤ 05:00」判(不能寫成單一區間比較)。
    """
    t = _dt.datetime.now().time() if now is None else now
    if _TXO_DAY[0] <= t <= _TXO_DAY[1]:
        return True
    return t >= _TXO_NIGHT[0] or t <= _TXO_NIGHT[1]


def session_window(key: SessionKey) -> tuple[str, str]:
    """時段 key → TC4 歷史/訂閱窗(StartTime, EndTime;UTC 小時字串)。"""
    ymd, kind = key
    start_h, end_h = _WINDOWS[kind]
    return (f"{ymd}{start_h}", f"{ymd}{end_h}")
