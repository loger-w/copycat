"""FinMind 全市場取數層(market-overview R2 design §4)— 阻塞,呼叫端丟 to_thread。

四個取數點,錯誤分類與 `oi_levels._fetch_rows` 同款:
- `fetch_snapshot`:全市場即時快照(專屬 endpoint,**無 query 參數**),每輪都打。
- `fetch_stock_info`:代碼 → 名稱 / 市場別 / 產業別對照(24h TTL,一天打幾次)。
- `fetch_disposition`:近 60 日處置股期間表(參數名 **start_date / end_date**)。
- `fetch_industry_chain`:代碼 → 產業 / 次產業對照(R4 類股強弱用,**無 query 參數**)。
  7 天 TTL,一天最多打幾次。
- `fetch_daily_prices`:單日全市場 EOD(連板數回看用)。一天只武裝一輪,掃描窗上限
  25 個日曆日,而**已成功取得的日跨重試由引擎的 memo 重用** → 成功取數 ≤ 25 次;
  每次失敗的嘗試最多多打 1 次(嘗試上限 10)→ 一天上界 ≈ 35 次。

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
_PRICE_DATASET = "TaiwanStockPrice"
_CHAIN_DATASET = "TaiwanStockIndustryChain"
_DISPOSITION_LOOKBACK_DAYS = 60
_TIMEOUT = 30.0
#: 單日全市場 EOD 專用:回應是 MB 級(~3 萬列含權證),秒級輪詢用的 30s 會在正常日
#: 就逾時 —— 失效樣態是 streak 整輪失敗、連板欄整天 null(`backfill_finmind` 同量級)
_DAILY_TIMEOUT = 60.0
_ATTEMPTS = 2  # 秒級輪詢的量級,重試一次即可;402 完全不重試(見 _get_rows)

#: `TaiwanStockInfo` 少於這麼多列即升 warning。實錄約 4300 列(上市+上櫃+興櫃);
#: 上游分頁截斷會讓對照表悄悄少一截,而缺代碼的表現是「那些股票從家數統計裡消失」——
#: 回應形狀合法、HTTP 200、畫面照畫,沒有這道觀測就只能靠猜。
INFO_MIN_ROWS = 3000

#: `TaiwanStockIndustryChain` 少於這麼多列即升 warning。實測約 6861 列,腰斬即異常;
#: 少一截的表現是「那些股票的產業歸類消失、類股強弱少幾個業別」—— 回應形狀合法、
#: HTTP 200、rotation 照算,沒有這道觀測就只能靠猜(`INFO_MIN_ROWS` 同理)。
CHAIN_MIN_ROWS = 1000


class BreadthFetchError(RuntimeError):
    """取數失敗;`quota=True` 代表 FinMind 配額用盡(HTTP 402),呼叫端改走長退避。"""

    def __init__(self, message: str, *, quota: bool = False) -> None:
        super().__init__(message)
        self.quota = quota


def _get_rows(url: str, token: str, *, label: str, timeout: float = _TIMEOUT) -> list[dict]:
    """單一 GET → `data` 陣列。失敗一律 `BreadthFetchError`(402 帶 quota=True 不重試)。

    `timeout` keyword-only:秒級輪詢的三支沿用 30s,單日 EOD 那支帶 60s(回應量級
    差兩個數量級,共用一個常數只能二選一地錯)。
    """
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    last: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            with urlopen(req, timeout=timeout) as resp:
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


def fetch_industry_chain(token: str) -> list[dict]:
    """產業鏈對照表(全檔一次,**無其他 query 參數**);列數過少即升 warning。"""
    query = urllib.parse.urlencode({"dataset": _CHAIN_DATASET})
    rows = _get_rows(f"{_DATA_API}?{query}", token, label="industry_chain")
    log = logger.info if len(rows) >= CHAIN_MIN_ROWS else logger.warning
    log("breadth industry_chain:%d rows(門檻 %d)", len(rows), CHAIN_MIN_ROWS)
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


def fetch_daily_prices(token: str, day: _date) -> list[dict]:
    """單日全市場 EOD(`TaiwanStockPrice`,start == end == `day`,**無 data_id**)。

    非交易日回**空 `data` 陣列**(合法回應,不是錯誤)—— 「空 = 假日候選」的判定
    在引擎那層,本函式只如實回傳。

    不重用 `backfill_finmind.fetch_day`:那條的錯誤契約是 RuntimeError / HTTPError,
    而引擎的退避分類吃 `BreadthFetchError.quota`(402 走長退避)。
    """
    query = urllib.parse.urlencode(
        {
            "dataset": _PRICE_DATASET,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        }
    )
    return _get_rows(
        f"{_DATA_API}?{query}",
        token,
        label=f"daily_prices {day.isoformat()}",
        timeout=_DAILY_TIMEOUT,
    )
