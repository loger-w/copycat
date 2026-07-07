"""兩份 replay run 並排對照(調 config 前後的實驗工具)."""

from __future__ import annotations

from pathlib import Path

from copycat.replay.report import agg_gap_buckets, agg_lock_buckets, load_events


def _pct(x: float | None) -> str:
    return f"{x:+.2%}" if x is not None else "—"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "—"
    return f"{b - a:+.2%}"


def _side_by_side(
    name: str, rows_a: list[dict], rows_b: list[dict], value_keys: list[tuple[str, str]]
) -> list[str]:
    lines = [f"\n## {name}\n"]
    headers = ["bucket", "n(A)", "n(B)"]
    for _, label in value_keys:
        headers += [f"{label}(A)", f"{label}(B)", f"Δ{label}"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    b_map = {r["bucket"]: r for r in rows_b}
    for ra in rows_a:
        rb = b_map.get(ra["bucket"], {})
        cells = [ra["bucket"], str(ra["n"]), str(rb.get("n", "—"))]
        for key, _ in value_keys:
            cells += [_pct(ra.get(key)), _pct(rb.get(key)), _delta(ra.get(key), rb.get(key))]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_compare(run_a: Path, run_b: Path, out: Path) -> Path:
    ev_a, ev_b = load_events(run_a), load_events(run_b)
    lines = [f"# Compare: A={run_a.name} vs B={run_b.name}\n"]
    lines += _side_by_side(
        "鎖板時間 × T+1(tiger)",
        agg_lock_buckets(ev_a, "tiger"),
        agg_lock_buckets(ev_b, "tiger"),
        [("med_gap", "med gap"), ("again_rate", "續鎖")],
    )
    lines += _side_by_side(
        "T+1 gap 分桶(tiger)",
        agg_gap_buckets(ev_a, "tiger"),
        agg_gap_buckets(ev_b, "tiger"),
        [("mean_open_to_close", "E[開→收]"), ("again_rate", "續鎖")],
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
