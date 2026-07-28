"""江波圖疊線(CDP / MA)計算與 cache — stock-ui-upgrade SC-4.

「已完成 bar」規則(design R1):輸入先剔除 date >= today 的 bar(盤中 partial bar
不得入計算);CDP 用最後一根已完成 bar 的 H/L/C,MA 用最後 5/20 根已完成 close。
偏離 brainstorm auto-default 的理由見 design v2 R4(data/daily 為凍結研究回補)。
"""

from __future__ import annotations

from copycat.live.stock_source import DailyBar


def compute_cdp(h: int, low: int, c: int) -> dict[str, int]:
    """毫元整數 CDP 五值;cdp 為 round-half-up(impl-spec R1:(x+2)//4,無 float)。"""
    cdp = (h + low + 2 * c + 2) // 4
    spread = h - low
    return {
        "cdp": cdp,
        "ah": cdp + spread,
        "nh": 2 * cdp - low,
        "nl": 2 * cdp - h,
        "al": cdp - spread,
    }


def compute_ma(closes: list[int], n: int) -> int | None:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) // n


def build_overlay(bars: list[DailyBar], today: str) -> dict:
    """bars(升冪)→ overlay response;剔除今日 partial 後空 → 全 null。"""
    done = [b for b in bars if b["date"] < today]
    if not done:
        return {"cdp": None, "ma5": None, "ma20": None, "date": None}
    last = done[-1]
    closes = [b["close"] for b in done]
    return {
        "cdp": compute_cdp(last["high"], last["low"], last["close"]),
        "ma5": compute_ma(closes, 5),
        "ma20": compute_ma(closes, 20),
        "date": last["date"],
    }


class OverlayCache:
    """per (code, today) 記憶;空結果(全 null)不 cache — TC4 失敗與真無資料在上游
    已不可分(design R14),don't-cache-empty 讓斷線恢復後可重試。"""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict] = {}

    def get(self, code: str, today: str) -> dict | None:
        return self._store.get((code, today))

    def put(self, code: str, today: str, value: dict) -> None:
        if value.get("cdp") is None and value.get("ma5") is None and value.get("ma20") is None:
            return
        self._store[(code, today)] = value
