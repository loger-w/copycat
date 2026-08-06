"""FinMind TXO 月契約 OI 撐壓(futures-allday SC-11;design §2)。

**口徑**:`TaiwanOptionDaily` data_id=TXO,filter `trading_session == "position"`
(OI 只在 position 列;after_market 列的 open_interest 恆 0)且 `contract_date` 與
futures engine 解析出的 TXF 契約月份**精確等值** —— 週選 `202608W1` / `202608F1` 與
他月因此自然排除,不必再寫序列規則。

**不在後端取 max**:回月契約的 per-strike 全表,由前端以現價 ±10% 帶內取 max。
真樣本顯示全域 max 會落在深度價外的垃圾履約價(call max 在 55000),那不是壓力。

**取數**:單次 range 查詢 today−10..today 再取 `max(date)` 那一日(D15:一次往返
涵蓋連假,無序列回退)。stdlib urllib(runtime 不引 httpx)包 `asyncio.to_thread`。

**降級語意**:token 未設 / 契約未解析 / 取數失敗一律 `{"date": null, "contract": null,
"strikes": []}` + HTTP 200 —— OI 線是可有可無的疊圖,4xx/5xx 會被前端 query 的 error
路徑吞成同一種紅色,反而讓「沒 token」與「FinMind 掛了」都變成看不懂的失敗。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
from datetime import date as _date
from datetime import timedelta
from typing import TypedDict
from urllib.request import Request, urlopen

from fastapi import FastAPI
from fastapi import Request as HttpRequest

from copycat.server import finmind_token

logger = logging.getLogger(__name__)

_API = "https://api.finmindtrade.com/api/v4/data"
_DATASET = "TaiwanOptionDaily"
_DATA_ID = "TXO"
_LOOKBACK_DAYS = 10
_TIMEOUT = 30.0
_ATTEMPTS = 2  # 一天一次呼叫的量級,重試一次即可;402 完全不重試(見 _fetch_rows)

#: 失敗/402 的負向快取秒數。不可永久 —— FinMind 恢復(或隔小時配額回補)後要自癒。
NEGATIVE_TTL_SECS = 300.0

#: `latest` 落後今日超過這麼多**日曆日**就升 warning(連假最長約 5 天)。
#: 分頁截斷 / 上游停更會讓 `latest` 悄悄退化成舊日期,而畫面上「舊了三天的 OI 線」與
#: 「今天的 OI 線」長得一模一樣 —— 沒有這道觀測就只能靠猜(review LF-3)。
STALE_WARN_DAYS = 5


class OiStrike(TypedDict):
    strike: int
    call_oi: int
    put_oi: int


class OiLevels(TypedDict):
    date: str | None
    contract: str | None
    strikes: list[OiStrike]


class OiFetchError(RuntimeError):
    """取數失敗(含配額用盡);呼叫端一律降級成空 shape + 負向快取。"""


def _empty() -> OiLevels:
    """每次新建:回傳共用的 module 常數會讓任何一處改動滲進其後每個回應。"""
    return {"date": None, "contract": None, "strikes": []}


def _now() -> float:
    """負向快取的時鐘(monotonic);測試 monkeypatch 這一個名字即可推進時間。"""
    return time.monotonic()


# ---------------------------------------------------------------------------
# 快取(正向永久 / 負向 TTL;跨日與換月自然換鍵)
# ---------------------------------------------------------------------------


class OiLevelsCache:
    """key = (contract_ym, today)。刻意不落盤:一天一次呼叫、重啟頻率低,atomic
    JSON cache 那套樣板對這個量級是純複雜度(design §2)。"""

    def __init__(self) -> None:
        self._pos: dict[tuple[str, str], OiLevels] = {}
        self._neg: dict[tuple[str, str], float] = {}

    def get(self, key: tuple[str, str], *, now: float) -> OiLevels | None:
        """命中正向 → 該值;負向仍在 TTL 內 → 空 shape(呼叫端直接回,零往返);
        皆未命中 → None(要去取)。"""
        hit = self._pos.get(key)
        if hit is not None:
            return hit
        until = self._neg.get(key)
        if until is not None:
            if until > now:
                return _empty()
            del self._neg[key]  # 過期即清,讓下一次真的去問
        return None

    def put(self, key: tuple[str, str], value: OiLevels) -> None:
        self._pos[key] = value
        self._neg.pop(key, None)

    def put_negative(self, key: tuple[str, str], *, now: float) -> None:
        self._neg[key] = now + NEGATIVE_TTL_SECS


_cache = OiLevelsCache()

#: 單飛鎖。**每個 event loop 一把**:asyncio.Lock 首次使用時綁定當下的 loop,之後在
#: 另一個 loop 用會 RuntimeError —— server 只有一條 loop 所以是恆等,但測試每條 async
#: 案例各自起 loop,module 級單一把鎖會在第二條測試炸掉(而且炸在與被測行為無關處)。
_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None


def _get_lock() -> asyncio.Lock:
    global _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop is not loop:
        _lock = asyncio.Lock()
        _lock_loop = loop
    return _lock


# ---------------------------------------------------------------------------
# 取數與 pivot
# ---------------------------------------------------------------------------


def _fetch_rows(start: str, end: str, token: str) -> list[dict]:
    """阻塞取數(呼叫端丟 to_thread)。失敗一律 `OiFetchError`。

    402 = 配額用盡:重打只會燒更多且必然同樣失敗 → 不 retry,直接讓呼叫端進負向快取。
    `TimeoutError` 獨立列在 except:SSL read timeout 不包在 URLError(CLAUDE.md §8)。
    """
    query = urllib.parse.urlencode(
        {
            "dataset": _DATASET,
            "data_id": _DATA_ID,
            "start_date": start,
            "end_date": end,
        }
    )
    req = Request(f"{_API}?{query}", headers={"Authorization": f"Bearer {token}"})
    last: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            with urlopen(req, timeout=_TIMEOUT) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 402:
                raise OiFetchError("FinMind 配額用盡(HTTP 402)") from e
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # 配額燒乾時 FinMind 會回非 JSON 內容 —— 與連線失敗同樣可重試
            last = e
        else:
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                raise OiFetchError(f"FinMind 回應無 data 陣列:{str(payload)[:120]}")
            return data
        logger.warning(
            "oi-levels 取數失敗(第 %d/%d 次):%s", attempt + 1, _ATTEMPTS, type(last).__name__
        )
    raise OiFetchError(f"FinMind 取數失敗:{last!r}")


def _pivot(rows: list[dict], contract_ym: str) -> OiLevels:
    """position + 該月契約 → max(date) 那日的 per-strike 表(升冪,缺對邊填 0)。"""
    picked = [
        r
        for r in rows
        if r.get("trading_session") == "position" and str(r.get("contract_date")) == contract_ym
    ]
    if not picked:
        return _empty()
    latest = max(str(r.get("date")) for r in picked)
    by_strike: dict[int, OiStrike] = {}
    skipped = 0
    for r in picked:
        if str(r.get("date")) != latest:
            continue
        try:
            strike = int(float(r["strike_price"]))
            oi = int(r.get("open_interest") or 0)
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        side = str(r.get("call_put", "")).lower()
        if side not in ("call", "put"):
            skipped += 1
            continue
        entry = by_strike.setdefault(strike, {"strike": strike, "call_oi": 0, "put_oi": 0})
        entry["call_oi" if side == "call" else "put_oi"] = oi
    if skipped:
        logger.warning("oi-levels %s %s:%d 列無法解析(已略過)", contract_ym, latest, skipped)
    if not by_strike:
        return _empty()
    return {
        "date": latest,
        "contract": contract_ym,
        "strikes": [by_strike[k] for k in sorted(by_strike)],
    }


def _log_freshness(rows: list[dict], levels: OiLevels, today: _date) -> None:
    """成功路徑的唯一觀測點(review LF-3)。

    10 日窗 ≈7 萬列走一次分頁,截斷或上游停更會讓 `latest` 靜默退化成舊日期 ——
    回應形狀完全合法、HTTP 200、前端照畫,只有「哪一天的 OI」變了。
    `latest` 落後 > `STALE_WARN_DAYS` 即升 warning,**但照樣回傳**(舊的撐壓仍有用,
    只是要有人知道它舊了)。
    """
    latest = levels["date"] or ""
    try:
        lag: int | None = (today - _date.fromisoformat(latest)).days
    except ValueError:
        lag = None  # 上游日期格式怪 → 一樣要吵(不可靜默當新鮮)
    log = logger.info if lag is not None and lag <= STALE_WARN_DAYS else logger.warning
    log(
        "oi-levels %s:%d rows → latest=%s / %d strikes(落後 %s 日)",
        levels["contract"],
        len(rows),
        latest,
        len(levels["strikes"]),
        "?" if lag is None else lag,
    )


async def fetch_oi_levels(contract_ym: str, *, token: str | None, today: _date) -> OiLevels:
    """月契約 OI 撐壓表;token 未設 / 取數失敗 / 無資料一律空 shape(never-raise)。

    空結果走**負向**快取而非正向永久(design 只寫「正向永久」,此處收斂):盤前該月
    position 列尚未出現、或上游只回了半份,都會 pivot 成空 —— 永久快取會把那個瞬間的
    空凍結一整天(overlay 的 don't-cache-empty 同一個理由)。
    """
    if not contract_ym or token is None:
        return _empty()
    key = (contract_ym, today.isoformat())
    hit = _cache.get(key, now=_now())
    if hit is not None:
        return hit
    async with _get_lock():
        # 等鎖期間可能已被前一位填好(單飛:同鍵只讓一條真的去打 FinMind)
        hit = _cache.get(key, now=_now())
        if hit is not None:
            return hit
        start = (today - timedelta(days=_LOOKBACK_DAYS)).isoformat()
        try:
            rows = await asyncio.to_thread(_fetch_rows, start, today.isoformat(), token)
        except OiFetchError as e:
            logger.warning("oi-levels 降級為空(負向快取 %ds):%s", int(NEGATIVE_TTL_SECS), e)
            _cache.put_negative(key, now=_now())
            return _empty()
        levels = _pivot(rows, contract_ym)
        if not levels["strikes"]:
            logger.info("oi-levels %s 無 position 列(%d rows)→ 負向快取", contract_ym, len(rows))
            _cache.put_negative(key, now=_now())
            return _empty()
        _log_freshness(rows, levels, today)
        _cache.put(key, levels)
        return levels


def register_oi(app: FastAPI) -> None:
    """掛 `GET /api/futures/oi-levels`(與 market_bars 同層,與群益無關)。"""

    @app.get("/api/futures/oi-levels")
    async def oi_levels(request: HttpRequest) -> dict:
        """TXF 當前契約月的 OI 撐壓表;任何一環缺席都是 200 空 shape(SC-11 降級語意)。

        `getattr` 帶 default:`state.futures` 在 lifespan 才被指派,create_app 期(單元
        測試直接打 app)不存在也要答得出來。
        """
        futures = getattr(request.app.state, "futures", None)
        if futures is None:
            return dict(_empty())
        ym = futures.resolved_contract("TXF")
        if not ym:
            return dict(_empty())
        token = finmind_token.resolve_token()  # 經模組屬性:patch finmind_token 即全域生效
        return dict(await fetch_oi_levels(ym, token=token, today=_date.today()))
