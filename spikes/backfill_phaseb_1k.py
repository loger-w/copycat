# -*- coding: utf-8 -*-
"""Phase B 前置 TC4 1K 批次回補(next-time 2026-07-07:對照組 T+1 + 7-8% 帶宇宙)。

一次性 job(spikes/ 慣例,不入 CLI):
- worklist A:events.csv source=="control" 缺 T+1 1K(設計參考值 2,068)
- worklist B:prices.csv 掃 7-8% 帶(0.07 ≤ high/ref_prev_close - 1 < 0.08,
  窗 2025-06-30 ~ 2026-06-26)缺 T 日 1K(設計參考值 6,509)
- 「先全鏈 SubHistory 再逐檔收割」波次模式(CLAUDE.md §8),全程進度 log(比例+耗時+ETA)
- 收工 finally Disconnect()(§0a KeepAlive 執行緒教訓)

用法:
    python spikes/backfill_phaseb_1k.py --dry-run     # 只掃 worklist、對照參考值
    python spikes/backfill_phaseb_1k.py               # 長跑回補
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "spikes" / "TCPY"))

from copycat.data.backfill_tc4 import _needs_refetch  # noqa: E402
from copycat.data.daily import DailyIndex  # noqa: E402
from copycat.data.models import Bar1K, parse_raw_bar  # noqa: E402
from copycat.data.store import write_bars  # noqa: E402
from copycat.tc4common import TC4_APPID, TC4_SKEY, iter_qry_pages  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_phaseb")

BAND_START = "2025-06-30"
BAND_END = "2026-06-26"
BAND_LO = 0.07
BAND_HI = 0.08
REF_CTRL_T1 = 2_068
REF_BAND = 6_509


def scan_ctrl_t1(data_dir: Path) -> list[tuple[str, str]]:
    """對照組(source==control)缺 T+1 1K 的 (stock_id, t1_date)。"""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with (data_dir / "events" / "events.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["source"] != "control" or not r["t1_date"]:
                continue
            key = (r["stock_id"], r["t1_date"])
            if key in seen:
                continue
            seen.add(key)
            if _needs_refetch(data_dir / "1k" / key[0] / f"{key[1]}.json"):
                out.append(key)
    return out


def scan_band(data_dir: Path, daily: DailyIndex) -> tuple[int, list[tuple[str, str]]]:
    """7-8% 帶宇宙:回傳 (帶內總 stock-day, 缺 T 日 1K 清單)。"""
    total = 0
    missing: list[tuple[str, str]] = []
    for stock_id, rows in daily._rows.items():  # noqa: SLF001 - 一次性 job 全掃
        for row in rows:
            if not (BAND_START <= row.date <= BAND_END):
                continue
            pc = daily.ref_prev_close(stock_id, row.date)
            if pc is None or pc <= 0:
                continue
            r = row.high / pc - 1.0
            if BAND_LO <= r < BAND_HI:
                total += 1
                if _needs_refetch(data_dir / "1k" / stock_id / f"{row.date}.json"):
                    missing.append((stock_id, row.date))
    return total, missing


def _window(date_str: str) -> tuple[str, str]:
    ymd = date_str.replace("-", "")
    return f"{ymd}00", f"{ymd}06"


def _harvest(api: object, session: str, stock_id: str, date_str: str) -> list[Bar1K]:
    """收割單一 stock-day 1K(已先 SubHistory;等待輪詢比舊逐檔模式短)。"""
    sym = f"TC.S.TWS.{stock_id}"
    start, end = _window(date_str)
    first: dict | None = None
    for attempt in range(8):
        first = api.GetHistory(session, sym, "1K", start, end, "0")  # type: ignore[attr-defined]
        if first and first.get("HisData"):
            break
        if attempt < 7:
            time.sleep(0.3)
    if not first or not first.get("HisData"):
        return []

    def _page(qry_index: str) -> list[dict]:
        his = api.GetHistory(session, sym, "1K", start, end, qry_index)  # type: ignore[attr-defined]
        return his.get("HisData", [])

    bars: list[Bar1K] = []
    for page in iter_qry_pages(_page):
        for raw in page:
            try:
                bar = parse_raw_bar(raw)
            except ValueError:
                continue
            if bar.m < 0:  # 盤前雜訊(時窗涵蓋 08:00 起)
                continue
            bars.append(bar)
    bars.sort(key=lambda b: b.m)
    return bars


def run(data_dir: Path, port: str, worklist: list[tuple[str, str, str]], wave: int) -> dict:
    import zmq
    from tcoreapi_mq import QuoteAPI

    api = QuoteAPI(TC4_APPID, TC4_SKEY)
    # 同 copycat.live.tc4 防護:app 死亡時 recv 可返回,不永久卡死長跑
    api.context.setsockopt(zmq.RCVTIMEO, 30_000)
    api.context.setsockopt(zmq.SNDTIMEO, 30_000)
    api.context.setsockopt(zmq.LINGER, 0)
    q = api.Connect(port)
    if q.get("Success") != "OK":
        raise RuntimeError(f"TC4 login failed: {q}")
    session = q["SessionKey"]
    logger.info("TC4 connected, session=%s", session[:8])

    stats = {"fetched": 0, "no_data": 0, "failed": 0}
    t0 = time.monotonic()
    total = len(worklist)
    try:
        for w0 in range(0, total, wave):
            batch = worklist[w0 : w0 + wave]
            # 先整波 SubHistory 讓 TC4 平行備資料再收割(§8:280 檔 10 分鐘 → 2 分鐘)
            for stock_id, date_str, _kind in batch:
                start, end = _window(date_str)
                api.SubHistory(session, f"TC.S.TWS.{stock_id}", "1K", start, end)
            for j, (stock_id, date_str, kind) in enumerate(batch):
                i = w0 + j
                try:
                    bars = _harvest(api, session, stock_id, date_str)
                    if bars:
                        write_bars(data_dir, stock_id, date_str, bars)
                        stats["fetched"] += 1
                    else:
                        stats["no_data"] += 1
                        logger.warning(
                            "[%d/%d] %s %s (%s): no data", i + 1, total, stock_id, date_str, kind
                        )
                except Exception:
                    stats["failed"] += 1
                    logger.exception(
                        "[%d/%d] %s %s (%s): error", i + 1, total, stock_id, date_str, kind
                    )
                if (i + 1) % 20 == 0 or i + 1 == total:
                    elapsed = time.monotonic() - t0
                    rate = (i + 1) / elapsed
                    eta_min = (total - i - 1) / rate / 60 if rate > 0 else 0
                    logger.info(
                        "progress %d/%d (%.1f%%) elapsed=%.1fmin eta=%.1fmin fetched=%d no_data=%d failed=%d",
                        i + 1,
                        total,
                        (i + 1) * 100.0 / total,
                        elapsed / 60,
                        eta_min,
                        stats["fetched"],
                        stats["no_data"],
                        stats["failed"],
                    )
    finally:
        api.Disconnect()  # §0a:不呼叫則 KeepAlive 執行緒讓 process 不退出
        logger.info("TC4 disconnected")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=REPO / "data")
    ap.add_argument("--port", default="50774")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wave", type=int, default=200)
    args = ap.parse_args()

    daily = DailyIndex.load(args.data_dir)
    ctrl = scan_ctrl_t1(args.data_dir)
    band_total, band_missing = scan_band(args.data_dir, daily)
    logger.info("worklist A ctrl T+1 缺 1K: %d(設計參考 %d)", len(ctrl), REF_CTRL_T1)
    logger.info(
        "worklist B 7-8%% 帶宇宙: 帶內 %d stock-day(設計參考 %d),缺 T 日 1K %d",
        band_total,
        REF_BAND,
        len(band_missing),
    )
    ctrl_set = set(ctrl)
    combined: list[tuple[str, str, str]] = [(s, d, "ctrl_t1") for s, d in ctrl]
    combined += [(s, d, "band") for s, d in band_missing if (s, d) not in ctrl_set]
    logger.info("合併 worklist(去重後): %d stock-day", len(combined))
    if args.dry_run:
        return

    stats = run(args.data_dir, args.port, combined, args.wave)
    logger.info("done: %s", stats)
    # 收工重掃:殘缺數字 = 對照證據
    ctrl_after = scan_ctrl_t1(args.data_dir)
    _, band_after = scan_band(args.data_dir, DailyIndex.load(args.data_dir))
    logger.info(
        "殘缺重掃: ctrl T+1 %d → %d;band %d → %d",
        len(ctrl),
        len(ctrl_after),
        len(band_missing),
        len(band_after),
    )


if __name__ == "__main__":
    main()
