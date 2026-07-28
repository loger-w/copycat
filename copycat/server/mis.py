"""TPEx 櫃買指數 MIS 快照(index-board SC-4).

MIS 為非契約公開端點(design Known Risk 1):失敗一律 None 降級,poller 層保留前值。
5 秒 poll 間隔尊重端點 userDelay=5000。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, TypedDict
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=otc_o00.tw&json=1&delay=0"
_TIMEOUT = 5.0


class OtcSnap(TypedDict):
    """價格欄毫點 int;time 為 HHMMSS 字串(台北時刻)。"""

    p: int
    ref: int
    open: int
    high: int
    low: int
    time: str


def _millipt(raw: str) -> int:
    return round(float(raw) * 1000)


def fetch_otc_snapshot(fetcher: Callable[..., Any] = urlopen) -> OtcSnap | None:
    """單次快照;任何失敗(網路/格式/暫停計算)→ None(caller 保留前值)。"""
    req = Request(_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with_resp = fetcher(req, timeout=_TIMEOUT)
        body = with_resp.read() if hasattr(with_resp, "read") else with_resp
        payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        if payload.get("rtcode") != "0000":
            logger.warning("MIS rtcode 異常:%s", payload.get("rtcode"))
            return None
        msg = payload["msgArray"][0]
        if msg.get("z") in (None, "", "-"):
            return None
        return OtcSnap(
            p=_millipt(msg["z"]),
            ref=_millipt(msg["y"]),
            open=_millipt(msg["o"]),
            high=_millipt(msg["h"]),
            low=_millipt(msg["l"]),
            time=str(msg["t"]).replace(":", ""),
        )
    # TimeoutError 獨立列(SSL read timeout 不包在 URLError,CLAUDE.md §8);
    # ValueError 涵蓋 o/h/l/y 欄 "-"(design R8)
    except (
        URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        ValueError,
    ) as e:
        logger.warning("MIS 快照失敗:%s", e)
        return None
