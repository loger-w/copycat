"""neigui five-tigers 種子資料 → copycat 標準格式(一次性匯入).

來源唯讀;TC4 原始格式陷阱(UTC 時刻、無前導零、字串數值)全在這層清洗,
引擎只看標準化資料(spec §3)。
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from copycat.data.daily import DailyIndex
from copycat.data.models import parse_raw_bar
from copycat.data.store import read_bars, write_bars

logger = logging.getLogger(__name__)


def _import_k1(src_file: Path, data_dir: Path) -> tuple[int, int]:
    """回傳 (匯入 stock-day 數, 略過的壞 bar 數)。壞 bar = 欄位缺漏/非數字."""
    days = 0
    skipped = 0
    with src_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            bars = []
            for raw in rec["bars"]:
                try:
                    bars.append(parse_raw_bar(raw))
                except ValueError:
                    skipped += 1
            bars.sort(key=lambda b: b.m)
            write_bars(data_dir, rec["stock_id"], rec["date"], bars)
            days += 1
    return days, skipped


def _import_daily(src: Path, data_dir: Path) -> None:
    out = data_dir / "daily" / "prices.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with (
        (src / "prices.csv").open("r", encoding="utf-8") as fin,
        out.open("w", encoding="utf-8", newline="") as fout,
    ):
        w = csv.DictWriter(
            fout, fieldnames=["stock_id", "date", "open", "high", "low", "close", "volume_lots"]
        )
        w.writeheader()
        for r in csv.DictReader(fin):
            w.writerow(
                {
                    "stock_id": r["stock_id"],
                    "date": r["date"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume_lots": str(float(r["volume"]) / 1000.0),
                }
            )


def _import_limitup(src: Path, data_dir: Path) -> list[dict[str, str]]:
    out = data_dir / "events" / "limitup_all.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with (src / "all_limitup_events.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({"stock_id": r["stock_id"], "date": r["date"], "close": r["close"]})
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
        w.writerows(rows)
    return rows


def _build_events(
    events_csv: Path, limitup: list[dict[str, str]], daily: DailyIndex, data_dir: Path
) -> tuple[int, int]:
    tiger: dict[tuple[str, str], dict[str, object]] = {}
    with events_csv.open("r", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            key = (r["stock_id"], r["date"])
            ev = tiger.setdefault(
                key,
                {
                    "stock_name": r["stock_name"],
                    "limitup_close": r["limitup_close"],
                    "brokers": set(),
                },
            )
            brokers = ev["brokers"]
            assert isinstance(brokers, set)
            brokers.add(r["broker_id"])
            t1 = daily.next_date(r["stock_id"], r["date"])
            if r.get("t1_date") and t1 and r["t1_date"] != t1:
                logger.warning(
                    "t1_date 不一致 %s %s: csv=%s 推導=%s(以推導為準)",
                    r["stock_id"],
                    r["date"],
                    r["t1_date"],
                    t1,
                )

    out_rows: list[dict[str, str]] = []
    for (sid, dt), ev in sorted(tiger.items()):
        brokers = ev["brokers"]
        assert isinstance(brokers, set)
        out_rows.append(
            {
                "stock_id": sid,
                "date": dt,
                "stock_name": str(ev["stock_name"]),
                "limitup_close": str(ev["limitup_close"]),
                "t1_date": daily.next_date(sid, dt) or "",
                "source": "tiger_csv",
                "broker_ids": "|".join(sorted(brokers)),
            }
        )
    n_tiger = len(out_rows)
    tiger_keys = set(tiger)
    for r in limitup:
        key = (r["stock_id"], r["date"])
        if key in tiger_keys:
            continue
        out_rows.append(
            {
                "stock_id": r["stock_id"],
                "date": r["date"],
                "stock_name": "",
                "limitup_close": r["close"],
                "t1_date": daily.next_date(r["stock_id"], r["date"]) or "",
                "source": "control",
                "broker_ids": "",
            }
        )
    out = data_dir / "events" / "events.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "stock_id",
                "date",
                "stock_name",
                "limitup_close",
                "t1_date",
                "source",
                "broker_ids",
            ],
        )
        w.writeheader()
        w.writerows(out_rows)
    return n_tiger, len(out_rows) - n_tiger


def run_import(src: Path, events_csv: Path, data_dir: Path) -> dict[str, object]:
    for required in ("k1_bars.jsonl", "prices.csv", "all_limitup_events.csv"):
        if not (src / required).exists():
            raise FileNotFoundError(src / required)
    if not events_csv.exists():
        raise FileNotFoundError(events_csv)

    days, skipped = _import_k1(src / "k1_bars.jsonl", data_dir)
    ctrl_file = src / "k1_control.jsonl"
    if ctrl_file.exists():
        d2, s2 = _import_k1(ctrl_file, data_dir)
        days, skipped = days + d2, skipped + s2
    _import_daily(src, data_dir)
    limitup = _import_limitup(src, data_dir)
    daily = DailyIndex.load(data_dir)
    n_tiger, n_ctrl = _build_events(events_csv, limitup, daily, data_dir)

    missing_t: list[str] = []
    missing_t1: list[str] = []
    with (data_dir / "events" / "events.csv").open("r", encoding="utf-8") as fh:
        for ev in csv.DictReader(fh):
            if read_bars(data_dir, ev["stock_id"], ev["date"]) is None:
                missing_t.append(f"{ev['stock_id']},{ev['date']}")
            if ev["t1_date"] and read_bars(data_dir, ev["stock_id"], ev["t1_date"]) is None:
                missing_t1.append(f"{ev['stock_id']},{ev['t1_date']}")

    manifest: dict[str, object] = {
        "k1_days": days,
        "skipped_bars": skipped,
        "tiger_events": n_tiger,
        "control_events": n_ctrl,
        "missing_t_1k": missing_t,
        "missing_t1_1k": missing_t1,
    }
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("import 完成: %s", {k: v for k, v in manifest.items() if not isinstance(v, list)})
    return manifest
