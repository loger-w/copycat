"""FinMind 全市場取數層(market-overview R2 design §4)— 阻塞,呼叫端丟 to_thread。

三個取數點,錯誤分類與 `oi_levels._fetch_rows` 同款:
- `fetch_snapshot`:全市場即時快照(專屬 endpoint,**無 query 參數**),每輪都打。
- `fetch_stock_info`:代碼 → 名稱 / 市場別 / 產業別對照(24h TTL,一天打幾次)。
- `fetch_disposition`:近 60 日處置股期間表(參數名 **start_date / end_date**)。

**402 不重試**:配額用盡時重打只會燒更多且必然同樣失敗 —— 以 `BreadthFetchError.quota`
標記讓呼叫端改走長退避(config `quota_backoff_secs`),與一般失敗的短退避分開。
`TimeoutError` 獨立列在 except:SSL read timeout 不包在 URLError(CLAUDE.md §8)。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
from datetime import date as _date
from datetime import timedelta
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_BASE = "https://api.finmindtrade.com/api/v4"
_DATA_API = f"{_BASE}/data"
_SNAPSHOT_API = f"{_BASE}/taiwan_stock_tick_snapshot"
_INFO_DATASET = "TaiwanStockInfo"
_DISPOSITION_DATASET = "TaiwanStockDispositionSecuritiesPeriod"
_DISPOSITION_LOOKBACK_DAYS = 60
_TIMEOUT = 30.0
_ATTEMPTS = 2  # 秒級輪詢的量級,重試一次即可;402 完全不重試(見 _get_rows)

#: `TaiwanStockInfo` 少於這麼多列即升 warning。實錄約 4300 列(上市+上櫃+興櫃);
#: 上游分頁截斷會讓對照表悄悄少一截,而缺代碼的表現是「那些股票從家數統計裡消失」——
#: 回應形狀合法、HTTP 200、畫面照畫,沒有這道觀測就只能靠猜。
INFO_MIN_ROWS = 3000


class BreadthFetchError(RuntimeError):
    """取數失敗;`quota=True` 代表 FinMind 配額用盡(HTTP 402),呼叫端改走長退避。"""

    def __init__(self, message: str, *, quota: bool = False) -> None:
        super().__init__(message)
        self.quota = quota


def _get_rows(url: str, token: str, *, label: str) -> list[dict]:
    """單一 GET → `data` 陣列。失敗一律 `BreadthFetchError`(402 帶 quota=True 不重試)。"""
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    last: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            with urlopen(req, timeout=_TIMEOUT) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 402:
                raise BreadthFetchError(f"FinMind 配額用盡(HTTP 402):{label}", quota=True) from e
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # 配額燒乾時 FinMind 會回非 JSON 內容 —— 與連線失敗同樣可重試
            last = e
        else:
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                raise BreadthFetchError(f"FinMind {label} 回應無 data 陣列:{str(payload)[:120]}")
            return data
        logger.warning(
            "breadth %s 取數失敗(第 %d/%d 次):%s",
            label,
            attempt + 1,
            _ATTEMPTS,
            type(last).__name__,
        )
    raise BreadthFetchError(f"FinMind {label} 取數失敗:{last!r}")


def fetch_snapshot(token: str) -> list[dict]:
    """全市場即時快照(全檔一次)。專屬 endpoint,無 query 參數。"""
    return _get_rows(_SNAPSHOT_API, token, label="snapshot")


def fetch_stock_info(token: str) -> list[dict]:
    """代碼對照表;列數過少即升 warning(照樣回傳 —— 少一截仍比沒有好)。"""
    query = urllib.parse.urlencode({"dataset": _INFO_DATASET})
    rows = _get_rows(f"{_DATA_API}?{query}", token, label="stock_info")
    log = logger.info if len(rows) >= INFO_MIN_ROWS else logger.warning
    log("breadth stock_info:%d rows(門檻 %d)", len(rows), INFO_MIN_ROWS)
    return rows


def fetch_disposition(token: str, today: _date) -> list[dict]:
    """近 60 日曆日的處置股期間表(區間查詢涵蓋跨月的處置期)。"""
    start = today - timedelta(days=_DISPOSITION_LOOKBACK_DAYS)
    query = urllib.parse.urlencode(
        {
            "dataset": _DISPOSITION_DATASET,
            "start_date": start.isoformat(),
            "end_date": today.isoformat(),
        }
    )
    return _get_rows(f"{_DATA_API}?{query}", token, label="disposition")
