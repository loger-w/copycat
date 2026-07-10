"""FinMind 當沖資格資料回補:TaiwanStockDayTrading(按日)+ DispositionSecuritiesPeriod.

「可當沖」= ex-post proxy:該股當日出現在 TaiwanStockDayTrading(有當沖成交)。
漲停股 T+1 幾乎必有當沖量,除非被禁 → proxy 偏差極小(spec [auto-default])。
處置期間(分盤撮合)一律視為不可當沖。
接入慣例沿 backfill_finmind:Bearer header、重試含 TimeoutError、manifest 續傳。
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date as _date
from datetime import timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_API = "https://api.finmindtrade.com/api/v4/data"

FetchFn = Callable[[str, str, str], list[dict[str, object]]]


def _fetch_dataset(dataset: str, start: str, end: str, token: str) -> list[dict[str, object]]:
    query = urllib.parse.urlencode({"dataset": dataset, "start_date": start, "end_date": end})
    req = urllib.request.Request(f"{_API}?{query}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            raise RuntimeError("FinMind 配額用盡(HTTP 402),停止回補") from exc
        raise
    data = payload.get("data", [])
    assert isinstance(data, list)
    return data


def _fetch_retry(
    fetch: Callable[[], list[dict[str, object]]], label: str, sleep_s: float
) -> list[dict[str, object]]:
    for attempt in range(3):
        try:
            return fetch()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            logger.warning(
                "daytrade %s 失敗(第 %d/3 次): %s", label, attempt + 1, type(exc).__name__
            )
            if attempt == 2:
                raise
            time.sleep(sleep_s)
    raise AssertionError("unreachable")


def _dates(start: str, end: str) -> list[str]:
    d0, d1 = _date.fromisoformat(start), _date.fromisoformat(end)
    out: list[str] = []
    d = d0
    while d <= d1:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def run_backfill_daytrade(
    data_dir: Path,
    start: str,
    end: str,
    token: str,
    fetch: FetchFn | None = None,
    sleep_s: float = 0.35,
) -> dict[str, int]:
    """按日抓 TaiwanStockDayTrading(manifest 續傳)+ range 抓處置期間;冪等合併."""
    out_dir = data_dir / "daytrade"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    done: set[str] = set()
    if manifest_path.exists():
        done = set(json.loads(manifest_path.read_text(encoding="utf-8")).get("done_dates", []))

    dt_path = out_dir / "day_trading.csv"
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if dt_path.exists():
        with dt_path.open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                key = (r["stock_id"], r["date"])
                if key not in seen:
                    seen.add(key)
                    rows.append(r)

    def _fetch(dataset: str, s: str, e: str) -> list[dict[str, object]]:
        if fetch is not None:
            return fetch(dataset, s, e)
        return _fetch_retry(lambda: _fetch_dataset(dataset, s, e, token), f"{dataset} {s}", sleep_s)

    fetched_days = 0
    added = 0
    for day in _dates(start, end):
        if day in done:
            continue
        data = _fetch("TaiwanStockDayTrading", day, day)
        fetched_days += 1
        for raw in data:
            sid = str(raw.get("stock_id", ""))
            d = str(raw.get("date", ""))
            if not sid or not d:
                continue
            key = (sid, d)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {"stock_id": sid, "date": d, "buy_after_sale": str(raw.get("BuyAfterSale", ""))}
            )
            added += 1
        if data:  # 空日(假日/FinMind 未更新)不進 manifest,之後可補
            done.add(day)
        if fetch is None:
            time.sleep(sleep_s)

    _write_csv(dt_path, ["stock_id", "date", "buy_after_sale"], rows)

    dispo = _fetch("TaiwanStockDispositionSecuritiesPeriod", start, end)
    dispo_rows: list[dict[str, str]] = []
    dispo_seen: set[tuple[str, str, str]] = set()
    dispo_path = out_dir / "disposition.csv"
    if dispo_path.exists():
        with dispo_path.open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                key = (r["stock_id"], r["period_start"], r["period_end"])
                if key not in dispo_seen:
                    dispo_seen.add(key)
                    dispo_rows.append(r)
    for raw in dispo:
        sid = str(raw.get("stock_id", ""))
        ps = str(raw.get("period_start", ""))
        pe = str(raw.get("period_end", ""))
        if not sid or not ps or not pe:
            continue
        key = (sid, ps, pe)
        if key in dispo_seen:
            continue
        dispo_seen.add(key)
        dispo_rows.append({"stock_id": sid, "period_start": ps, "period_end": pe})
    _write_csv(dispo_path, ["stock_id", "period_start", "period_end"], dispo_rows)

    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"done_dates": sorted(done)}), encoding="utf-8")
    os.replace(tmp, manifest_path)

    logger.info(
        "backfill-daytrade [%s..%s]: fetched_days=%d added=%d dispo=%d",
        start,
        end,
        fetched_days,
        added,
        len(dispo_rows),
    )
    return {"fetched_days": fetched_days, "added_rows": added, "disposition_rows": len(dispo_rows)}


class DayTradeIndex:
    """當沖資格判定:在當日名單且不在處置期間;該日無任何 rows → None(未覆蓋,R18)."""

    def __init__(
        self,
        by_date: dict[str, set[str]],
        periods: dict[str, list[tuple[str, str]]],
    ) -> None:
        self._by_date = by_date
        self._periods = periods

    @classmethod
    def load(cls, data_dir: Path) -> DayTradeIndex | None:
        dt_path = data_dir / "daytrade" / "day_trading.csv"
        if not dt_path.exists():
            return None
        by_date: dict[str, set[str]] = {}
        with dt_path.open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                by_date.setdefault(r["date"], set()).add(r["stock_id"])
        periods: dict[str, list[tuple[str, str]]] = {}
        dispo_path = data_dir / "daytrade" / "disposition.csv"
        if dispo_path.exists():
            with dispo_path.open("r", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    periods.setdefault(r["stock_id"], []).append(
                        (r["period_start"], r["period_end"])
                    )
        return cls(by_date, periods)

    def eligible(self, stock_id: str, date: str) -> bool | None:
        for ps, pe in self._periods.get(stock_id, []):  # 處置期間優先於覆蓋判定
            if ps <= date <= pe:
                return False
        stocks = self._by_date.get(date)
        if not stocks:
            return None  # 該日未覆蓋(FinMind 未更新)→ caller 不過濾
        return stock_id in stocks
