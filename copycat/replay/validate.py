"""Characterization gate:replay 彙總 vs docs/evidence golden(spec §6 SC-2~SC-6)."""

from __future__ import annotations

from pathlib import Path

from copycat.replay.report import (
    agg_auction,
    agg_gap_buckets,
    agg_lock_buckets,
    agg_queue,
    agg_violent,
    load_events,
)

# golden 出處:intraday_playbook §2d / open_gap_definition §2-3 / strategy.md §5
_G_LOCK = [
    ("<09:05", 175, 0.074, 0.183),
    ("09:05-10:00", 322, 0.035, 0.056),
    ("10:00-12:00", 311, 0.024, 0.068),
    ("12:00-13:00", 125, 0.015, 0.112),
    ("13:00+", 90, 0.006, 0.044),
]
_G_GAP = [
    ("<0%", 92, 0.0072, 0.022),
    ("0-1%", 63, 0.0026, 0.048),
    ("1-3%", 96, -0.0160, 0.000),
    ("3-7%", 170, -0.0164, 0.094),
    ("7-9.5%", 45, -0.0347, 0.067),
    ("漲停開", 76, -0.0126, 0.263),
]
_G_AUCTION = [("<3%", 0.018), ("3-8%", 0.027), (">=8%", 0.090)]

_TOL_N = 0.05  # n 相對差
_TOL_GAP = 0.005  # med gap / E 差(0.5pp)
_TOL_AGAIN = 0.01  # 續鎖率差(1pp)
_TOL_SC3 = 0.03  # SC-3 續鎖率差(3pp,violent_pull 為 1K 近似)


def _within_rel(actual: float | None, golden: float, tol: float) -> bool:
    return actual is not None and golden > 0 and abs(actual - golden) / golden <= tol


def _within_pp(actual: float | None, golden: float, tol: float) -> bool:
    return actual is not None and abs(actual - golden) <= tol


def _pct(x: float | None) -> str:
    return f"{x:+.2%}" if x is not None else "—"


def _check(sc: str, name: str, golden_s: str, actual_s: str, tol_s: str, ok: bool) -> dict:
    return {"sc": sc, "name": name, "golden": golden_s, "actual": actual_s, "tol": tol_s, "ok": ok}


def run_validate(run_five: Path, run_four: Path) -> list[dict]:
    ev5 = load_events(run_five)
    ev4 = load_events(run_four)
    checks: list[dict] = []

    lock = {r["bucket"]: r for r in agg_lock_buckets(ev5, "tiger")}
    for bucket, g_n, g_gap, g_again in _G_LOCK:
        r = lock[bucket]
        checks.append(
            _check(
                "SC-2",
                f"鎖板 {bucket} n",
                str(g_n),
                str(r["n"]),
                "±5%",
                _within_rel(r["n"], g_n, _TOL_N),
            )
        )
        checks.append(
            _check(
                "SC-2",
                f"鎖板 {bucket} med gap",
                _pct(g_gap),
                _pct(r["med_gap"]),
                "±0.5pp",
                _within_pp(r["med_gap"], g_gap, _TOL_GAP),
            )
        )
        checks.append(
            _check(
                "SC-2",
                f"鎖板 {bucket} 續鎖",
                _pct(g_again),
                _pct(r["again_rate"]),
                "±1pp",
                _within_pp(r["again_rate"], g_again, _TOL_AGAIN),
            )
        )

    v = agg_violent(ev5, "tiger")
    vio, nat = v["violent"], v["natural_early"]
    direction = (nat["again_rate"] or 0) > (vio["again_rate"] or 1)
    checks.append(
        _check(
            "SC-3",
            "violent med gap",
            "+6.20%",
            _pct(vio["med_gap"]),
            "±3pp",
            _within_pp(vio["med_gap"], 0.062, _TOL_SC3),
        )
    )
    checks.append(
        _check(
            "SC-3",
            "violent 續鎖",
            "+3.30%",
            _pct(vio["again_rate"]),
            "±3pp",
            _within_pp(vio["again_rate"], 0.033, _TOL_SC3),
        )
    )
    checks.append(
        _check(
            "SC-3",
            "natural_early 續鎖",
            "+18.30%",
            _pct(nat["again_rate"]),
            "±3pp,且 natural≫violent",
            _within_pp(nat["again_rate"], 0.183, _TOL_SC3) and direction,
        )
    )

    # SC-4 golden cell 出自四虎 core 事件集(與 SC-5 同,2026-07-07 定義掃描確認:
    # 四虎 lock<10:00 × share≥0.40 → med gap +6.00% / 續鎖 13.2% 與 golden 完全一致)
    queue = {r["bucket"]: r for r in agg_queue(ev4, "tiger")}
    checks.append(
        _check(
            "SC-4",
            "早盤鎖 >=40% med gap",
            "+6.00%",
            _pct(queue[">=40%"]["med_gap"]),
            "±0.5pp",
            _within_pp(queue[">=40%"]["med_gap"], 0.060, _TOL_GAP),
        )
    )
    checks.append(
        _check(
            "SC-4",
            "早盤鎖 >=40% 續鎖",
            "+13.20%",
            _pct(queue[">=40%"]["again_rate"]),
            "±1pp",
            _within_pp(queue[">=40%"]["again_rate"], 0.132, _TOL_AGAIN),
        )
    )
    checks.append(
        _check(
            "SC-4",
            "早盤鎖 <15% 續鎖",
            "+0.00%",
            _pct(queue["<15%"]["again_rate"]),
            "±1pp",
            _within_pp(queue["<15%"]["again_rate"], 0.0, _TOL_AGAIN),
        )
    )

    gap = {r["bucket"]: r for r in agg_gap_buckets(ev4, "tiger")}
    for bucket, g_n, g_e, g_again in _G_GAP:
        r = gap[bucket]
        checks.append(
            _check(
                "SC-5",
                f"gap {bucket} n",
                str(g_n),
                str(r["n"]),
                "±5%",
                _within_rel(r["n"], g_n, _TOL_N),
            )
        )
        checks.append(
            _check(
                "SC-5",
                f"gap {bucket} E[開→收]",
                _pct(g_e),
                _pct(r["mean_open_to_close"]),
                "±0.5pp",
                _within_pp(r["mean_open_to_close"], g_e, _TOL_GAP),
            )
        )
        checks.append(
            _check(
                "SC-5",
                f"gap {bucket} 續鎖",
                _pct(g_again),
                _pct(r["again_rate"]),
                "±1pp",
                _within_pp(r["again_rate"], g_again, _TOL_AGAIN),
            )
        )

    auction = {r["bucket"]: r for r in agg_auction(ev5, "tiger", "dayvol")}
    for bucket, g_gap in _G_AUCTION:
        checks.append(
            _check(
                "SC-6",
                f"競價 {bucket} med gap",
                _pct(g_gap),
                _pct(auction[bucket]["med_gap"]),
                "±0.5pp",
                _within_pp(auction[bucket]["med_gap"], g_gap, _TOL_GAP),
            )
        )
    return checks


def format_validate(checks: list[dict]) -> str:
    lines = ["| SC | 項目 | golden | actual | 容忍 | 結果 |", "|---|---|---|---|---|---|"]
    for c in checks:
        lines.append(
            f"| {c['sc']} | {c['name']} | {c['golden']} | {c['actual']} "
            f"| {c['tol']} | {'PASS' if c['ok'] else '**FAIL**'} |"
        )
    n_fail = sum(1 for c in checks if not c["ok"])
    lines.append(f"\n{len(checks) - n_fail}/{len(checks)} PASS")
    return "\n".join(lines)
