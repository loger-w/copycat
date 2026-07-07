"""events.jsonl → summary.md 彙總表(對照 evidence golden 的表格式)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

_LOCK_BUCKETS = ("<09:05", "09:05-10:00", "10:00-12:00", "12:00-13:00", "13:00+")
_GAP_BUCKETS = ("<0%", "0-1%", "1-3%", "3-7%", "7-9.5%", "漲停開")
_QUEUE_BUCKETS = (">=40%", "15-40%", "<15%")
_AUCTION_BUCKETS = ("<3%", "3-8%", ">=8%")


def load_events(run_dir: Path) -> list[dict]:
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines]


def med(xs: list[float]) -> float | None:
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def _full(events: list[dict], cohort: str) -> list[dict]:
    """lock 與 t1 都齊的事件(golden 表同樣以有 T 日 1K 且鎖住者統計)."""
    return [e for e in events if e["cohort"] == cohort and e.get("lock") and e.get("t1")]


def _rate(sel: list[dict], pred: Callable[[dict], bool]) -> float | None:
    return sum(1 for e in sel if pred(e)) / len(sel) if sel else None


def agg_lock_buckets(events: list[dict], cohort: str) -> list[dict]:
    full = _full(events, cohort)
    rows = []
    for bucket in _LOCK_BUCKETS:
        sel = [e for e in full if e["lock"]["lock_time_bucket"] == bucket]
        rows.append(
            {
                "bucket": bucket,
                "n": len(sel),
                "med_gap": med([e["t1"]["gap"] for e in sel]),
                "again_rate": _rate(sel, lambda e: e["again"]),
            }
        )
    return rows


def agg_violent(events: list[dict], cohort: str) -> dict[str, dict]:
    full = _full(events, cohort)
    violent = [e for e in full if e["lock"]["violent_pull"]]
    natural = [e for e in full if e["lock"]["lock_idx"] < 4 and not e["lock"]["violent_pull"]]

    def stats(sel: list[dict]) -> dict:
        return {
            "n": len(sel),
            "med_gap": med([e["t1"]["gap"] for e in sel]),
            "again_rate": _rate(sel, lambda e: e["again"]),
        }

    return {"violent": stats(violent), "natural_early": stats(natural)}


def agg_queue(events: list[dict], cohort: str) -> list[dict]:
    full = [e for e in _full(events, cohort) if e["lock"]["lock_idx"] < 59]  # 早盤鎖
    rows = []
    for bucket in _QUEUE_BUCKETS:
        sel = [e for e in full if e["lock"]["queue_bucket"] == bucket]
        rows.append(
            {
                "bucket": bucket,
                "n": len(sel),
                "med_gap": med([e["t1"]["gap"] for e in sel]),
                "again_rate": _rate(sel, lambda e: e["again"]),
            }
        )
    return rows


def agg_gap_buckets(events: list[dict], cohort: str) -> list[dict]:
    sel_all = [e for e in events if e["cohort"] == cohort and e.get("t1")]
    rows = []
    for bucket in _GAP_BUCKETS:
        sel = [e for e in sel_all if e["t1"]["gap_bucket"] == bucket]
        oc = [e["t1"]["close_vs_open"] for e in sel]
        rows.append(
            {
                "bucket": bucket,
                "n": len(sel),
                "share": len(sel) / len(sel_all) if sel_all else None,
                "mean_open_to_close": sum(oc) / len(oc) if oc else None,
                "p_win": _rate(sel, lambda e: e["t1"]["close_vs_open"] > 0),
                "again_rate": _rate(sel, lambda e: e["again"]),
                "touched_rate": _rate(sel, lambda e: e["t1"]["touched_limit"]),
            }
        )
    return rows


def agg_auction(events: list[dict], cohort: str, basis: str) -> list[dict]:
    sel_all = [e for e in events if e["cohort"] == cohort and e.get("t1")]
    rows = []
    for bucket in _AUCTION_BUCKETS:
        if basis == "dayvol":

            def in_bucket(e: dict, b: str = bucket) -> bool:
                s = e["t1"]["auction_share_dayvol"]
                return {"<3%": s < 0.03, "3-8%": 0.03 <= s < 0.08, ">=8%": s >= 0.08}[b]

            sel = [e for e in sel_all if in_bucket(e)]
        else:  # adv20(盤中版,用引擎現成標籤)
            sel = [e for e in sel_all if e["t1"]["auction_tell"] == bucket]
        rows.append(
            {"bucket": bucket, "n": len(sel), "med_gap": med([e["t1"]["gap"] for e in sel])}
        )
    return rows


def _pct(x: float | None, signed: bool = True) -> str:
    if x is None:
        return "—"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def write_summary(run_dir: Path) -> Path:
    events = load_events(run_dir)
    parts: list[str] = ["# Replay 彙總\n"]
    n_excluded = sum(1 for e in events if e["cohort"] == "excluded")
    n_skip = sum(1 for e in events if e["skip"])
    parts.append(
        f"- 事件總數 {len(events)};excluded(watchlist 未命中){n_excluded};"
        f"有缺漏(skip 非空){n_skip}\n"
    )
    for cohort in ("tiger", "control"):
        n = sum(1 for e in events if e["cohort"] == cohort)
        parts.append(f"\n## cohort={cohort}(n={n})\n")
        parts.append("\n### 鎖板時間 × T+1\n")
        parts.append(
            _table(
                ["bucket", "n", "med gap", "續鎖率"],
                [
                    [r["bucket"], str(r["n"]), _pct(r["med_gap"]), _pct(r["again_rate"], False)]
                    for r in agg_lock_buckets(events, cohort)
                ],
            )
        )
        v = agg_violent(events, cohort)
        parts.append("\n\n### 暴力拉板 vs 開盤自然鎖\n")
        parts.append(
            _table(
                ["type", "n", "med gap", "續鎖率"],
                [
                    [k, str(s["n"]), _pct(s["med_gap"]), _pct(s["again_rate"], False)]
                    for k, s in v.items()
                ],
            )
        )
        parts.append("\n\n### 早盤鎖 × 鎖後排隊消耗\n")
        parts.append(
            _table(
                ["bucket", "n", "med gap", "續鎖率"],
                [
                    [r["bucket"], str(r["n"]), _pct(r["med_gap"]), _pct(r["again_rate"], False)]
                    for r in agg_queue(events, cohort)
                ],
            )
        )
        parts.append("\n\n### T+1 gap 分桶\n")
        parts.append(
            _table(
                ["bucket", "n", "占比", "E[開→收]", "P(win)", "續鎖率", "觸停率"],
                [
                    [
                        r["bucket"],
                        str(r["n"]),
                        _pct(r["share"], False),
                        _pct(r["mean_open_to_close"]),
                        _pct(r["p_win"], False),
                        _pct(r["again_rate"], False),
                        _pct(r["touched_rate"], False),
                    ]
                    for r in agg_gap_buckets(events, cohort)
                ],
            )
        )
        parts.append("\n\n### 競價量 tell(研究版 ÷全日量)\n")
        parts.append(
            _table(
                ["bucket", "n", "med gap"],
                [
                    [r["bucket"], str(r["n"]), _pct(r["med_gap"])]
                    for r in agg_auction(events, cohort, "dayvol")
                ],
            )
        )
        parts.append("\n\n### 競價量 tell(盤中版 ÷20日均量,無 lookahead)\n")
        parts.append(
            _table(
                ["bucket", "n", "med gap"],
                [
                    [r["bucket"], str(r["n"]), _pct(r["med_gap"])]
                    for r in agg_auction(events, cohort, "adv20")
                ],
            )
        )
        parts.append("\n")
    out = run_dir / "summary.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
