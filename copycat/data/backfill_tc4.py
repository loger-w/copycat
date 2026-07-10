"""TC4 歷史 1K 回補:讀 events.csv 找缺 T+1 1K 的 stock-day,逐筆向 TC4 拉取."""

from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path

from copycat.data.models import Bar1K, parse_raw_bar

logger = logging.getLogger(__name__)

# Touchance 官方範例公開的 app 憑證(GitBook / TCPY sample 原樣),非帳號 secret
TC4_APPID = "ZMQ"
TC4_SKEY = "8076c9867a372d2a9a814ae710c256e2"


def _needs_refetch(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return True
        if not isinstance(payload, dict) or "bars" not in payload:
            return True
    except (json.JSONDecodeError, UnicodeDecodeError):
        return True
    return False


def _find_missing(data_dir: Path, events_path: Path) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    with events_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            stock_id = row["stock_id"]
            t1_date = row["t1_date"]
            if not stock_id or not t1_date:  # 尚無次一交易日的事件 t1_date 為空
                continue
            path = data_dir / "1k" / stock_id / f"{t1_date}.json"
            if _needs_refetch(path):
                missing.append((stock_id, t1_date))
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _date_to_utc_window(date_str: str) -> tuple[str, str]:
    ymd = date_str.replace("-", "")
    return f"{ymd}00", f"{ymd}06"


def _tc4_symbol(stock_id: str) -> str:
    return f"TC.S.TWS.{stock_id}"


def _fetch_1k(api: object, session: str, stock_id: str, date_str: str) -> list[Bar1K]:
    """回傳與種子匯入同格式的 Bar1K list(parse_raw_bar 同源,含零量試撮根)."""
    sym = _tc4_symbol(stock_id)
    start, end = _date_to_utc_window(date_str)
    api.SubHistory(session, sym, "1K", start, end)  # type: ignore[attr-defined]
    for _ in range(10):
        time.sleep(1)
        his = api.GetHistory(session, sym, "1K", start, end, "0")  # type: ignore[attr-defined]
        if his and his.get("HisData") and len(his["HisData"]) > 0:
            break
    else:
        return []

    bars: list[Bar1K] = []
    qry_index = "0"
    while True:
        his = api.GetHistory(session, sym, "1K", start, end, qry_index)  # type: ignore[attr-defined]
        page = his.get("HisData", [])
        if not page:
            break
        for raw in page:
            try:
                bar = parse_raw_bar(raw)
            except ValueError:
                continue
            if bar.m < 0:  # 盤前雜訊(TC4 時窗涵蓋 08:00 起)
                continue
            bars.append(bar)
        next_index = page[-1].get("QryIndex", "")
        if not next_index or next_index == qry_index:  # 空 = 結束;停滯 = 防無限迴圈
            break
        qry_index = next_index
    bars.sort(key=lambda b: b.m)
    return bars


def _save_bars(data_dir: Path, stock_id: str, date_str: str, bars: list[Bar1K]) -> None:
    from copycat.data.store import write_bars

    write_bars(data_dir, stock_id, date_str, bars)


def run_backfill_tc4(
    data_dir: Path,
    events_path: Path,
    port: str,
    batch_size: int = 0,
) -> dict[str, int]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY"))
    from tcoreapi_mq import QuoteAPI  # type: ignore[import-untyped]

    missing = _find_missing(data_dir, events_path)
    logger.info("missing 1K stock-days: %d", len(missing))
    if not missing:
        return {"total_missing": 0, "fetched": 0, "failed": 0}

    if batch_size > 0:
        missing = missing[:batch_size]
        logger.info("batch limited to %d", batch_size)

    api = QuoteAPI(TC4_APPID, TC4_SKEY)
    q_data = api.Connect(port)
    if q_data.get("Success") != "OK":
        raise RuntimeError(f"TC4 login failed: {q_data}")
    session = q_data["SessionKey"]
    logger.info("TC4 connected, session=%s", session[:8])

    fetched = 0
    failed = 0
    try:
        for i, (stock_id, date_str) in enumerate(missing):
            try:
                bars = _fetch_1k(api, session, stock_id, date_str)
                if bars:
                    _save_bars(data_dir, stock_id, date_str, bars)
                    fetched += 1
                    logger.info(
                        "[%d/%d] %s %s: %d bars",
                        i + 1,
                        len(missing),
                        stock_id,
                        date_str,
                        len(bars),
                    )
                else:
                    failed += 1
                    logger.warning(
                        "[%d/%d] %s %s: no data",
                        i + 1,
                        len(missing),
                        stock_id,
                        date_str,
                    )
            except Exception:
                failed += 1
                logger.exception(
                    "[%d/%d] %s %s: error",
                    i + 1,
                    len(missing),
                    stock_id,
                    date_str,
                )
            time.sleep(0.5)
    finally:
        api.Disconnect()

    return {"total_missing": len(missing), "fetched": fetched, "failed": failed}
