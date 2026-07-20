"""FinMind 分點日報回補:taiwan_stock_trading_daily_report(per stock-day 專用 endpoint).

events.csv 全事件之 T 日 → data/brokers/<stock_id>/<date>.json(broker 層聚合,
完整不截斷——neigui 舊檔只留 top-30 淨買超、賣方大戶已丟失,本管道修正此截斷)。
接入慣例沿 backfill_daytrade:Bearer header、重試含 TimeoutError、manifest 續傳、
空回應不進 manifest、402 → RuntimeError 停止(續傳可重跑)。
rate:sleep_s=0.65 ≈ 5,500 req/hr < Sponsor 6,000 req/hr rolling 配額。
"""

from __future__ import annotations

import csv
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from copycat.fileio import atomic_write_text

logger = logging.getLogger(__name__)

_API = "https://api.finmindtrade.com/api/v4/taiwan_stock_trading_daily_report"

# (stock_id, date) → 原始 rows(分點×價位明細)
FetchFn = Callable[[str, str], list[dict[str, object]]]


def _fetch_report(stock_id: str, date: str, token: str) -> list[dict[str, object]]:
    query = urllib.parse.urlencode({"data_id": stock_id, "date": date})
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
                "brokers %s 失敗(第 %d/3 次): %s", label, attempt + 1, type(exc).__name__
            )
            if attempt == 2:
                raise
            time.sleep(sleep_s)
    raise AssertionError("unreachable")


def aggregate_brokers(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """分點×價位明細 → broker 層聚合(sum buy/sell 股數);broker_id asc 排序(輸出確定性)."""
    acc: dict[str, dict[str, object]] = {}
    for raw in rows:
        bid = str(raw.get("securities_trader_id", ""))
        if not bid:
            continue
        entry = acc.setdefault(
            bid,
            {"broker_id": bid, "name": str(raw.get("securities_trader", "")), "buy": 0, "sell": 0},
        )
        entry["buy"] = int(entry["buy"]) + int(float(str(raw.get("buy", 0) or 0)))  # type: ignore[arg-type]
        entry["sell"] = int(entry["sell"]) + int(float(str(raw.get("sell", 0) or 0)))  # type: ignore[arg-type]
    return [acc[k] for k in sorted(acc)]


def brokers_path(data_dir: Path, stock_id: str, date: str) -> Path:
    return data_dir / "brokers" / stock_id / f"{date}.json"


def read_brokers(data_dir: Path, stock_id: str, date: str) -> list[dict[str, object]] | None:
    """回 None = 該 stock-day 未回補;[] = 已回補但無資料(不會發生於正常交易日)."""
    path = brokers_path(data_dir, stock_id, date)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    brokers = payload.get("brokers", [])
    assert isinstance(brokers, list)
    return brokers


def _event_targets(events_csv: Path) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with events_csv.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (r["stock_id"], r["date"])
            if key not in seen:
                seen.add(key)
                targets.append(key)
    return targets


def run_backfill_brokers(
    data_dir: Path,
    events_csv: Path,
    token: str,
    fetch: FetchFn | None = None,
    sleep_s: float = 0.65,
    limit: int | None = None,
) -> dict[str, int]:
    """events.csv 全事件 T 日分點日報回補(manifest 續傳冪等);limit = 首日樣本驗證用."""
    out_dir = data_dir / "brokers"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    done: set[str] = set()
    if manifest_path.exists():
        done = set(json.loads(manifest_path.read_text(encoding="utf-8")).get("done", []))

    def _fetch(sid: str, day: str) -> list[dict[str, object]]:
        if fetch is not None:
            return fetch(sid, day)
        return _fetch_retry(lambda: _fetch_report(sid, day, token), f"{sid} {day}", sleep_s)

    targets = _event_targets(events_csv)
    fetched = skipped = empty = 0
    total = len(targets) if limit is None else min(limit, len(targets))
    for sid, day in targets:
        if limit is not None and fetched >= limit:
            break
        key = f"{sid}|{day}"
        if key in done or brokers_path(data_dir, sid, day).exists():
            skipped += 1
            continue
        rows = _fetch(sid, day)
        fetched += 1
        if not rows:  # 空回應(FinMind 未更新)不進 manifest,之後可補
            empty += 1
            logger.warning("brokers %s %s 空回應,不進 manifest", sid, day)
            continue
        brokers = aggregate_brokers(rows)
        path = brokers_path(data_dir, sid, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            path, json.dumps({"stock_id": sid, "date": day, "brokers": brokers}, ensure_ascii=False)
        )
        done.add(key)
        if fetch is None:
            time.sleep(sleep_s)
        if fetched % 200 == 0:
            logger.info(
                "backfill-brokers 進度 %d/%d(skipped=%d empty=%d)", fetched, total, skipped, empty
            )

    atomic_write_text(manifest_path, json.dumps({"done": sorted(done)}))

    logger.info(
        "backfill-brokers 完成:fetched=%d skipped=%d empty=%d targets=%d",
        fetched,
        skipped,
        empty,
        len(targets),
    )
    return {"fetched": fetched, "skipped": skipped, "empty": empty, "targets": len(targets)}
