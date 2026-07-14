"""label-events:top-30 淨買超標籤(邊界/tie-break/只補空/verify;change-spec SC-2)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from copycat.data.label_events import label_events, top_netbuy_hits

_EVENT_FIELDS = [
    "stock_id",
    "date",
    "stock_name",
    "limitup_close",
    "t1_date",
    "source",
    "broker_ids",
]


def _write_events(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_EVENT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _event(sid: str, date: str, source: str = "scan", broker_ids: str = "") -> dict[str, str]:
    return {
        "stock_id": sid,
        "date": date,
        "stock_name": "",
        "limitup_close": "10.0",
        "t1_date": "2026-01-02",
        "source": source,
        "broker_ids": broker_ids,
    }


def _write_brokers(data_dir: Path, sid: str, date: str, brokers: list[dict[str, object]]) -> None:
    path = data_dir / "brokers" / sid / f"{date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"stock_id": sid, "date": date, "brokers": brokers}), encoding="utf-8"
    )


def _write_watchlist(path: Path, ids: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "test",
                "members": [{"broker_id": i, "name": i, "role": "leader"} for i in ids],
            }
        ),
        encoding="utf-8",
    )


def _brokers_ranked(n: int, watch_id: str, watch_rank: int) -> list[dict[str, object]]:
    """n 個分點,net 遞減(rank 1 = net n×10);watchlist 成員插在 watch_rank."""
    out: list[dict[str, object]] = []
    for i in range(1, n + 1):
        bid = watch_id if i == watch_rank else f"B{i:03d}"
        out.append({"broker_id": bid, "name": bid, "buy": (n - i + 1) * 10, "sell": 0})
    return out


def test_top5_boundary_rank5_hits_rank6_does_not() -> None:
    # 語意 = top-5 淨買超(2026-07-15 實證修正:top-30 是 neigui 儲存截斷非標籤準則)
    watch = frozenset({"9227"})
    assert top_netbuy_hits(_brokers_ranked(10, "9227", 5), watch) == ["9227"]
    assert top_netbuy_hits(_brokers_ranked(10, "9227", 6), watch) == []


def test_top5_tiebreak_broker_id_asc() -> None:
    # 6 個分點 net 全相等 → tie-break broker_id asc,前 5 名入列
    brokers: list[dict[str, object]] = [
        {"broker_id": f"B{i:03d}", "name": "", "buy": 100, "sell": 0} for i in range(1, 6)
    ]
    brokers.append({"broker_id": "Z999", "name": "", "buy": 100, "sell": 0})  # asc 排最後 → 出局
    assert top_netbuy_hits(brokers, frozenset({"Z999"})) == []
    assert top_netbuy_hits(brokers, frozenset({"B005"})) == ["B005"]


def test_label_fills_empty_only(tmp_path: Path) -> None:
    events = tmp_path / "events" / "events.csv"
    _write_events(
        events,
        [
            _event("2330", "2026-01-01"),  # 空 → 應補
            _event("1101", "2026-01-01", source="tiger_csv", broker_ids="9600"),  # 既有 → 不動
        ],
    )
    _write_brokers(tmp_path, "2330", "2026-01-01", _brokers_ranked(5, "9227", 1))
    _write_brokers(tmp_path, "1101", "2026-01-01", _brokers_ranked(5, "9227", 1))  # 重算會是 9227
    wl = tmp_path / "wl.json"
    _write_watchlist(wl, ["9227", "9600"])

    stats = label_events(tmp_path, events, wl)
    assert stats["labeled_hit"] == 1
    assert stats["already_labeled"] == 1
    with events.open(encoding="utf-8") as fh:
        rows = {r["stock_id"]: r for r in csv.DictReader(fh)}
    assert rows["2330"]["broker_ids"] == "9227"
    assert rows["1101"]["broker_ids"] == "9600"  # 既有值原封不動


def test_label_no_hit_stays_empty_and_uncovered_counted(tmp_path: Path) -> None:
    events = tmp_path / "events" / "events.csv"
    _write_events(events, [_event("2330", "2026-01-01"), _event("1101", "2026-01-01")])
    _write_brokers(tmp_path, "2330", "2026-01-01", _brokers_ranked(5, "B999", 1))  # 無 watchlist
    # 1101 無 brokers 檔 → uncovered
    wl = tmp_path / "wl.json"
    _write_watchlist(wl, ["9227"])

    stats = label_events(tmp_path, events, wl)
    assert stats["labeled_no_hit"] == 1
    assert stats["uncovered"] == 1
    with events.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert all(r["broker_ids"] == "" for r in rows)


def test_verify_existing_reports_consistency(tmp_path: Path) -> None:
    events = tmp_path / "events" / "events.csv"
    _write_events(
        events,
        [
            _event("2330", "2026-01-01", source="tiger_csv", broker_ids="9227"),  # 一致
            _event("1101", "2026-01-01", source="tiger_csv", broker_ids="9600"),  # 不一致
            _event("2317", "2026-01-01", source="tiger_csv", broker_ids="9227"),  # 無檔
        ],
    )
    _write_brokers(tmp_path, "2330", "2026-01-01", _brokers_ranked(5, "9227", 1))
    _write_brokers(tmp_path, "1101", "2026-01-01", _brokers_ranked(5, "9227", 1))
    wl = tmp_path / "wl.json"
    _write_watchlist(wl, ["9227", "9600"])

    stats = label_events(tmp_path, events, wl, verify_existing=True)
    assert stats["verified_matched"] == 1
    assert stats["verified_mismatched"] == 1
    assert stats["verified_uncovered"] == 1
    with events.open(encoding="utf-8") as fh:
        rows = {r["stock_id"]: r for r in csv.DictReader(fh)}
    assert rows["1101"]["broker_ids"] == "9600"  # verify 模式不寫檔


def test_different_watchlist_relabels_differently(tmp_path: Path) -> None:
    events = tmp_path / "events" / "events.csv"
    _write_events(events, [_event("2330", "2026-01-01")])
    _write_brokers(
        tmp_path,
        "2330",
        "2026-01-01",
        [
            {"broker_id": "9227", "name": "", "buy": 100, "sell": 0},
            {"broker_id": "5854", "name": "", "buy": 90, "sell": 0},
        ],
    )
    wl_a = tmp_path / "a.json"
    _write_watchlist(wl_a, ["5854"])
    label_events(tmp_path, events, wl_a)
    with events.open(encoding="utf-8") as fh:
        assert next(csv.DictReader(fh))["broker_ids"] == "5854"
