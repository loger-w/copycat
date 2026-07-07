"""FinMind TaiwanStockPrice 日線回補(SC-1)— 按日期抓、(stock_id, date) 冪等合併.

token 走 Authorization Bearer header;錯誤 log 不含 token / URL query。
續傳判準 = data/daily/backfill_manifest.json 的成功日集合(marker),
每日成功即 atomic 落盤,中斷不丟進度。
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
_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]

FetchFn = Callable[[str, str], list[dict[str, object]]]


def _map_row(raw: dict[str, object]) -> dict[str, str] | None:
    """FinMind 欄位 → prices.csv schema;Trading_Volume(股)÷1000 → volume_lots(張)."""
    try:
        return {
            "stock_id": str(raw["stock_id"]),
            "date": str(raw["date"]),
            "open": str(float(raw["open"])),  # type: ignore[arg-type]
            "high": str(float(raw["max"])),  # type: ignore[arg-type]
            "low": str(float(raw["min"])),  # type: ignore[arg-type]
            "close": str(float(raw["close"])),  # type: ignore[arg-type]
            "spread": str(float(raw["spread"])),  # type: ignore[arg-type]
            "volume_lots": str(float(raw["Trading_Volume"]) / 1000.0),  # type: ignore[arg-type]
        }
    except (KeyError, ValueError, TypeError):
        return None


def fetch_day(date: str, token: str) -> list[dict[str, object]]:
    """抓單日全市場日線;402(配額)→ RuntimeError,其餘 HTTP/URL 錯誤由 caller 重試."""
    query = urllib.parse.urlencode(
        {"dataset": "TaiwanStockPrice", "start_date": date, "end_date": date}
    )
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


def _fetch_retry(fetch: FetchFn, date: str, token: str, sleep_s: float) -> list[dict[str, object]]:
    for attempt in range(3):
        try:
            return fetch(date, token)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            # 訊息只含日期與次數,不含 URL / token
            logger.warning(
                "backfill %s 失敗(第 %d/3 次): %s", date, attempt + 1, type(exc).__name__
            )
            if attempt == 2:
                raise
            time.sleep(sleep_s)
    raise AssertionError("unreachable")


def _read_existing(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows[(r["stock_id"], r["date"])] = {f: r.get(f, "") for f in _FIELDS}
    return rows


def _write_atomic(path: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        for key in sorted(rows):
            w.writerow(rows[key])
    os.replace(tmp, path)


def _dates(start: str, end: str) -> list[str]:
    d0, d1 = _date.fromisoformat(start), _date.fromisoformat(end)
    out: list[str] = []
    d = d0
    while d <= d1:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def run_backfill(
    data_dir: Path,
    start: str,
    end: str,
    token: str,
    *,
    fetch: FetchFn = fetch_day,
    sleep_s: float = 0.7,
) -> dict[str, int]:
    prices_path = data_dir / "daily" / "prices.csv"
    manifest_path = data_dir / "daily" / "backfill_manifest.json"
    rows = _read_existing(prices_path)
    done: set[str] = set()
    if manifest_path.exists():
        done = set(json.loads(manifest_path.read_text(encoding="utf-8"))["done_dates"])

    fetched = skipped = added = 0
    for day in _dates(start, end):
        if day in done:
            skipped += 1
            continue
        raw_rows = _fetch_retry(fetch, day, token, sleep_s)
        fetched += 1
        for raw in raw_rows:
            mapped = _map_row(raw)
            if mapped is None:
                continue
            key = (mapped["stock_id"], mapped["date"])
            if key not in rows:  # 既有鍵不覆寫
                rows[key] = mapped
                added += 1
        done.add(day)
        _write_atomic(prices_path, rows)
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"done_dates": sorted(done)}, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, manifest_path)
        if sleep_s:
            time.sleep(sleep_s)
    logger.info("backfill 完成: fetched=%d skipped=%d added=%d", fetched, skipped, added)
    return {"fetched_days": fetched, "skipped_days": skipped, "added_rows": added}
