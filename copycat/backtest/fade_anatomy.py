"""§0 前置描述統計(round 4 prereg 2026-07-16;設計輸入,不入判定)— fade-anatomy CLI。

五節:(a) MFE / 讓回、(b) 出量殺解剖、(c) 墊高解剖、(d) 內盤比 UC 分層 gate、
(e) 緩漲觀察。全部以 round 3 舊出場(cfg_legacy:TP 樹 / inner_flip 剝離)模擬,
凍結值回填 round 4 config 後重跑不受汙染(change-spec §5.5;review P2)。
口徑:讓回 / 讓肉一律「毛」(review P1:毛淨混算會系統性偏向放行 tp_hl)。
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path

from copycat.backtest.fade_cells import (
    _R4_TP_OFF,
    _baseline_entry_idx,
    _simulate_r3_trades,
    build_universes,
    find_cell_a_entry,
    find_cell_b_entry,
    find_cell_c_entry,
    is_uc_sample,
)
from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_simulate import FadeSample, _round_trip_cost
from copycat.backtest.quantiles import quantiles_round
from copycat.backtest.report_fmt import fmt_quantiles
from copycat.data.models import Bar1K
from copycat.fileio import atomic_write_text
from copycat.market import limit_up_price

logger = logging.getLogger(__name__)

_Universe = list[tuple[FadeSample, list[Bar1K]]]


def _gap_bucket(gap: float, edges: tuple[float, ...]) -> str:
    for lo, hi in zip(edges, edges[1:]):
        if lo <= gap < hi:
            return f"gap_{lo:g}_{hi:g}"
    return "gap_other"


# ---------- (b) 出量殺解剖 ----------


def flush_anatomy(
    uni: _Universe,
    cfg: FadeBacktestConfig,
    zs: tuple[float, ...] = (2.0, 3.0, 5.0),
    lookback: int = 5,
) -> dict[str, object]:
    """base_arm 進場窗(idx=0)掃 flush 事件:量 > z×前 lookback 均量 且 low ≤ 進場後最低。

    描述掃描非搜索:輸出各 z 的分佈供凍結單值(prereg §0(b))。
    post_move = (flush close − 收盤)/flush close;正 = 殺後續跌(晚收更賺)。
    """
    out: dict[str, object] = {}
    for z in zs:
        firsts_m: list[float] = []
        recoveries: list[float] = []
        post_moves: list[float] = []
        by_gap: dict[str, int] = {}
        found = 0
        for sample, bars in uni:
            if len(bars) < 2:
                continue
            post = bars[1:]
            post_low: float | None = None
            window: list[float] = []
            hit = None
            for b in post:
                post_low = b.low if post_low is None else min(post_low, b.low)
                if len(window) >= lookback:
                    avg = sum(window[-lookback:]) / lookback
                    if avg > 0 and b.volume > avg * z and b.low <= post_low:
                        hit = b
                        break
                window.append(b.volume)
            if hit is not None:
                found += 1
                firsts_m.append(float(hit.m))
                rng = hit.high - hit.low
                if rng > 0:
                    recoveries.append((hit.close - hit.low) / rng)
                if hit.close > 0:
                    post_moves.append((hit.close - bars[-1].close) / hit.close)
                key = _gap_bucket(sample.gap, cfg.base_arm_gap_edges)
                by_gap[key] = by_gap.get(key, 0) + 1
        out[f"z{z:g}"] = {
            "n_days": len(uni),
            "found": found,
            "found_rate": (found / len(uni)) if uni else None,
            "first_m": quantiles_round(firsts_m),
            "recovery": quantiles_round(recoveries),
            "post_move": quantiles_round(post_moves),
            "by_gap": by_gap,
        }
    return out


# ---------- (c) 墊高解剖 ----------


def _entry_idx_for(
    kind: str, sample: FadeSample, bars: list[Bar1K], cfg: FadeBacktestConfig
) -> int | None:
    t1_limit = limit_up_price(sample.limit)
    if kind == "base_arm":
        return 0
    if kind == "m7_arm":
        return _baseline_entry_idx(bars)
    if kind == "cell_a":
        thr = cfg.cell_a_inner_thresholds[0] if cfg.cell_a_inner_thresholds else 0.45
        found = find_cell_a_entry(bars, t1_limit, thr, cfg)
        return found[0] if found else None
    if kind == "cell_b":
        d = cfg.cell_b_approach_dists[0] if cfg.cell_b_approach_dists else 0.03
        found = find_cell_b_entry(bars, t1_limit, d, cfg)
        return found[0] if found else None
    if kind == "cell_c":
        r = cfg.cell_c_rally_pcts[0] if cfg.cell_c_rally_pcts else 0.05
        found = find_cell_c_entry(bars, r, cfg)
        return found[0] if found else None
    raise ValueError(f"未知 arm kind: {kind}")


def hl_anatomy(
    uni: _Universe,
    cfg: FadeBacktestConfig,
    ks: tuple[int, ...] = (2, 3),
    arms: tuple[str, ...] = ("base_arm", "m7_arm"),
) -> dict[str, object]:
    """墊高結構(殺不破前低 + 拉回高點遞增):依各臂進場 idx 起算(引擎同窗)。

    讓肉 = (確認價 − 確認前進場後最低)/ 進場價(價格毛口徑);
    post_move = (確認價 − 收盤)/ 進場價;正 = 確認後仍續跌(提前收工讓掉肉)。
    共用 fade_tp 單一實作(PivotState / check_higher_low_exit,min_profit 鬆綁)。
    """
    from copycat.backtest.fade_tp import PivotState, check_higher_low_exit

    out: dict[str, object] = {}
    for k in ks:
        cfg_k = dataclasses.replace(
            cfg, **_R4_TP_OFF | {"tp_hl_k": k, "tp_hl_min_profit": -1.0}
        )
        arm_blocks: dict[str, object] = {}
        for kind in arms:
            confirms_m: list[float] = []
            givebacks: list[float] = []
            post_moves: list[float] = []
            n_days = 0
            found = 0
            for sample, bars in uni:
                idx = _entry_idx_for(kind, sample, bars, cfg)
                if idx is None or idx >= len(bars) - 1:
                    continue
                n_days += 1
                entry_price = bars[idx].close
                if entry_price <= 0:
                    continue
                t1_limit = limit_up_price(sample.limit)
                state = PivotState()
                pre_min_low: float | None = None
                for b in bars[idx + 1 :]:
                    state.update(b)
                    pre_min_low = b.low if pre_min_low is None else min(pre_min_low, b.low)
                    if b.low >= t1_limit - cfg.limit_eps:
                        continue  # 凍結 bar 只餵不判定(引擎同語意)
                    fill = check_higher_low_exit(state, b, 0.0, cfg_k)
                    if fill is not None:
                        found += 1
                        confirms_m.append(float(b.m))
                        if pre_min_low is not None:
                            givebacks.append((fill - pre_min_low) / entry_price)
                        post_moves.append((fill - bars[-1].close) / entry_price)
                        break
            arm_blocks[kind] = {
                "n_days": n_days,
                "found": found,
                "found_rate": (found / n_days) if n_days else None,
                "confirm_m": quantiles_round(confirms_m),
                "giveback": quantiles_round(givebacks),
                "post_move": quantiles_round(post_moves),
            }
        out[f"k{k}"] = arm_blocks
    return out


def tp_hl_demote(hl_giveback_p50: float | None, hold_giveback_p50: float | None) -> bool:
    """prereg fallback #2 判準:墊高讓肉中位數 > 抱到收盤讓回中位數 → DEMOTE。

    統計不可得(結構樣本不足)一律 DEMOTE(保守向,事先寫死)。
    """
    if hl_giveback_p50 is None:
        return True
    if hold_giveback_p50 is None:
        return False
    return hl_giveback_p50 > hold_giveback_p50


# ---------- (d) 內盤比 UC 分層 gate ----------

_INNER_BUCKETS = ("lt_0.45", "mid", "gt_0.55")


def _inner_bucket(ratio: float) -> str:
    if ratio < 0.45:
        return "lt_0.45"
    if ratio > 0.55:
        return "gt_0.55"
    return "mid"


def inner_gate_anatomy(uni: _Universe, cfg: FadeBacktestConfig) -> dict[str, object]:
    """前 15 分鐘累計內盤比 × gap 桶 → 後續摸板率(摸板 = high ≥ 漲停×(1−0.01),與硬線一致)。

    PASS(寫死):tiger 合併 >0.55 桶摸板率 < <0.45 桶,且有資料的 gap 層方向一致 ≥ 2/3。
    """
    per_cell: dict[str, dict[str, int]] = {}
    combined: dict[str, dict[str, int]] = {b: {"n": 0, "touch": 0} for b in _INNER_BUCKETS}
    for sample, bars in uni:
        head = [b for b in bars if b.m < 15]
        tail = [b for b in bars if b.m >= 15]
        up = sum(b.up_volume for b in head)
        dn = sum(b.down_volume for b in head)
        if up + dn <= 0 or not tail:
            continue
        bucket = _inner_bucket(dn / (up + dn))
        t1_limit = limit_up_price(sample.limit)
        touched = any(b.high >= t1_limit * (1.0 - 0.01) for b in tail)
        gkey = _gap_bucket(sample.gap, cfg.base_arm_gap_edges)
        cell = per_cell.setdefault(f"{bucket}:{gkey}", {"n": 0, "touch": 0})
        cell["n"] += 1
        cell["touch"] += 1 if touched else 0
        combined[bucket]["n"] += 1
        combined[bucket]["touch"] += 1 if touched else 0

    def _rate(d: dict[str, int]) -> float | None:
        return (d["touch"] / d["n"]) if d["n"] else None

    combined_out = {
        b: {"n": v["n"], "touch_rate": _rate(v)} for b, v in combined.items()
    }
    lt_rate = combined_out["lt_0.45"]["touch_rate"]
    gt_rate = combined_out["gt_0.55"]["touch_rate"]
    combined_ok = (
        isinstance(lt_rate, float) and isinstance(gt_rate, float) and gt_rate < lt_rate
    )
    # gap 分層方向一致性(只計兩桶皆有資料的層)
    layers = 0
    consistent = 0
    for lo, hi in zip(cfg.base_arm_gap_edges, cfg.base_arm_gap_edges[1:]):
        gkey = f"gap_{lo:g}_{hi:g}"
        lt = per_cell.get(f"lt_0.45:{gkey}")
        gt = per_cell.get(f"gt_0.55:{gkey}")
        if not lt or not gt or lt["n"] == 0 or gt["n"] == 0:
            continue
        layers += 1
        lt_r = _rate(lt)
        gt_r = _rate(gt)
        if isinstance(lt_r, float) and isinstance(gt_r, float) and gt_r < lt_r:
            consistent += 1
    layered_ok = layers > 0 and (consistent / layers) >= (2.0 / 3.0)
    passed = combined_ok and layered_ok
    # φ 候選建議:0.45 / 0.55 兩錨,主值 = 與 mid 桶分離度較大者(描述性建議)
    mid_rate = combined_out["mid"]["touch_rate"]
    suggested_main = 0.45
    if (
        isinstance(mid_rate, float)
        and isinstance(lt_rate, float)
        and isinstance(gt_rate, float)
        and abs(mid_rate - lt_rate) < abs(mid_rate - gt_rate)
    ):
        # mid 行為接近 lt(危險群)→ 0.55 線分離度較好
        suggested_main = 0.55
    return {
        "cells": {
            key: {"n": v["n"], "touch_rate": _rate(v)} for key, v in sorted(per_cell.items())
        },
        "combined": combined_out,
        "layers": layers,
        "consistent_layers": consistent,
        "pass": passed,
        "suggested_phi_grid": [suggested_main, 0.55 if suggested_main == 0.45 else 0.45],
    }


# ---------- (e) 緩漲觀察 ----------


def slow_rally_anatomy(
    uni: _Universe, min_bars: int = 10, max_bar_gain: float = 0.003, post_n: int = 10
) -> dict[str, object]:
    """緩漲段 = 連續 ≥min_bars 根 close 不減且單根漲幅 ≤max_bar_gain;
    post_move = (段末 close − 之後第 post_n 根 close)/段末 close;正 = 結束後下跌
    (支持「緩漲結束常反向」假設)。僅描述,不入對決(prereg §0(e))。"""
    days_with = 0
    post_moves: list[float] = []
    seg_lens: list[float] = []
    for _sample, bars in uni:
        run = 0
        seg_end: int | None = None
        for i in range(1, len(bars)):
            prev_c = bars[i - 1].close
            cur_c = bars[i].close
            if prev_c > 0 and cur_c >= prev_c and (cur_c / prev_c - 1.0) <= max_bar_gain:
                run += 1
                if run >= min_bars:
                    seg_end = i
            else:
                if seg_end is not None:
                    break  # 只取當日第一段
                run = 0
        if seg_end is None:
            continue
        days_with += 1
        seg_lens.append(float(run))
        end_close = bars[seg_end].close
        post_idx = min(len(bars) - 1, seg_end + post_n)
        if end_close > 0 and post_idx > seg_end:
            post_moves.append((end_close - bars[post_idx].close) / end_close)
    return {
        "n_days": len(uni),
        "days_with_segment": days_with,
        "rate": (days_with / len(uni)) if uni else None,
        "segment_len": quantiles_round(seg_lens),
        "post_move": quantiles_round(post_moves),
    }


# ---------- (a) MFE / 讓回 ----------

_MFE_ARMS: tuple[tuple[str, str], ...] = (
    ("base_arm", "main"),
    ("baseline_m7", "main"),
    ("cell_a", "main"),
    ("cell_b", "cellb"),
    ("cell_c", "low"),
)


def mfe_anatomy(
    universes: dict[str, _Universe],
    cfg: FadeBacktestConfig,
    watchlist_ids: frozenset[str],
) -> dict[str, object]:
    """round 3 陣容各臂(round 3 出場語意)的 MFE 分佈 + 抱到收盤讓回。

    讓回 = mfe − max(gross_pnl, 0),gross_pnl = pnl + 來回成本(全毛口徑;review P1),
    僅計抱到收盤成交的交易(exit_reason=None 且非鎖死)。
    """
    if not cfg.struct_stop_buffers:
        raise ValueError("mfe_anatomy 需要 struct_stop_buffers 提供 b 值")
    cfg_legacy = dataclasses.replace(cfg, **_R4_TP_OFF)
    b = cfg.struct_stop_buffers[0]
    cost = _round_trip_cost(cfg)
    out: dict[str, object] = {}
    for kind, uni_key in _MFE_ARMS:
        uni = universes.get(uni_key) or universes.get("main") or []
        if not uni:
            continue
        param = 0.0
        if kind == "cell_a":
            param = cfg.cell_a_inner_thresholds[0] if cfg.cell_a_inner_thresholds else 0.45
        elif kind == "cell_b":
            param = cfg.cell_b_approach_dists[0] if cfg.cell_b_approach_dists else 0.03
        elif kind == "cell_c":
            param = cfg.cell_c_rally_pcts[0] if cfg.cell_c_rally_pcts else 0.05
        trades, _ = _simulate_r3_trades(
            uni, kind, param, b, cfg_legacy, cfg.slippage_ticks, watchlist_ids
        )
        mfes = [t.mfe for t in trades if t.mfe is not None]
        givebacks = [
            t.mfe - max(t.pnl + cost, 0.0)
            for t in trades
            if t.mfe is not None and t.exit_reason is None and not t.locked_close
        ]
        out[kind] = {
            "n": len(trades),
            "mfe": quantiles_round(mfes),
            "giveback_closeout": quantiles_round(givebacks),
        }
    return out


# ---------- CLI 協調 ----------


def run_anatomy(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    report_date: str,
    watchlist_path: Path,
    report_dir: Path | None = None,
) -> Path:
    """§0 五項統計 → anatomy.json + evidence md(in-window;設計輸入不入判定)。"""
    from copycat.watchlist import load_watchlist

    watchlist = load_watchlist(watchlist_path)
    ids = watchlist.broker_ids
    universes, _counts = build_universes(data_dir, cfg)

    def _uc_in_window(uni: _Universe) -> _Universe:
        return [
            (s, b)
            for s, b in uni
            if is_uc_sample(s, ids) and s.t1_date < cfg.forward_start
        ]

    main_uc = _uc_in_window(universes.get("main", []))
    low_uc = _uc_in_window(universes.get("low", []))
    cellb_uc = _uc_in_window(universes.get("cellb", universes.get("main", [])))
    uni_map = {"main": main_uc, "low": low_uc, "cellb": cellb_uc}

    logger.info("anatomy universes main=%d low=%d cellb=%d", len(main_uc), len(low_uc), len(cellb_uc))
    a = mfe_anatomy(uni_map, cfg, ids)
    logger.info("anatomy (a) MFE done")
    b = flush_anatomy(main_uc, cfg)
    logger.info("anatomy (b) flush done")
    c = hl_anatomy(main_uc, cfg)
    logger.info("anatomy (c) higher-low done")
    d = inner_gate_anatomy(main_uc, cfg)
    logger.info("anatomy (d) inner gate done(pass=%s)", d.get("pass"))
    e = slow_rally_anatomy(main_uc)
    logger.info("anatomy (e) slow rally done")

    base_blk = a.get("base_arm")
    hold_gb = None
    if isinstance(base_blk, dict):
        gb = base_blk.get("giveback_closeout")
        if isinstance(gb, dict):
            hold_gb = gb.get("p50")
    k2 = c.get("k2")
    hl_gb = None
    if isinstance(k2, dict):
        arm = k2.get("base_arm")
        if isinstance(arm, dict):
            gbq = arm.get("giveback")
            if isinstance(gbq, dict):
                hl_gb = gbq.get("p50")
    demote = tp_hl_demote(
        hl_gb if isinstance(hl_gb, float) else None,
        hold_gb if isinstance(hold_gb, float) else None,
    )

    result: dict[str, object] = {
        "report_date": report_date,
        "in_window_lt": cfg.forward_start,
        "n_uc_main": len(main_uc),
        "n_uc_low": len(low_uc),
        "n_uc_cellb": len(cellb_uc),
        "a_mfe": a,
        "b_flush": b,
        "c_higher_low": c,
        "d_inner_gate": d,
        "e_slow_rally": e,
        "verdicts": {
            "inner_flip": "PASS" if d.get("pass") else "DEMOTE",
            "tp_hl": "DEMOTE" if demote else "PASS",
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"anatomy_{report_date}.json"
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1))

    report_path = out_dir / f"fade_round4_anatomy_{report_date}.md"
    _write_report(result, report_path)
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        _write_report(result, report_dir / report_path.name)
    return report_path


def _write_report(result: dict[str, object], path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Round 4 §0 前置描述統計({result.get('report_date')};設計輸入,不入判定)")
    lines.append("")
    lines.append(
        f"- 宇宙:UC 池 in-window(< {result.get('in_window_lt')});"
        f"main n={result.get('n_uc_main')} / low n={result.get('n_uc_low')}"
        f" / cellb n={result.get('n_uc_cellb')};模擬 = round 3 舊出場(不受新機制汙染)。"
    )
    verdicts = result.get("verdicts")
    if isinstance(verdicts, dict):
        lines.append(
            f"- **gate 判準輸出**:inner_flip: **{verdicts.get('inner_flip')}**;"
            f"tp_hl: **{verdicts.get('tp_hl')}**(讓肉 vs 讓回中位數,毛口徑)。"
        )
    lines.append("")

    lines.append("## (a) MFE / 抱到收盤讓回(毛口徑;分位 p25/p50/p75/p90)")
    lines.append("")
    lines.append("| 臂 | n | MFE | 讓回(closeout) |")
    lines.append("|---|---:|---|---|")
    a = result.get("a_mfe")
    if isinstance(a, dict):
        for kind in sorted(a):
            blk = a[kind]
            if isinstance(blk, dict):
                lines.append(
                    f"| {kind} | {blk.get('n')} | {fmt_quantiles(blk.get('mfe'))}"
                    f" | {fmt_quantiles(blk.get('giveback_closeout'))} |"
                )
    lines.append("")

    lines.append("## (b) 出量殺解剖(base_arm 窗;z × lookback=5)")
    lines.append("")
    lines.append("| z | 出現率 | 首次分鐘 | recovery | post_move(正=殺後續跌) |")
    lines.append("|---|---:|---|---|---|")
    b = result.get("b_flush")
    if isinstance(b, dict):
        for zkey in sorted(b):
            blk = b[zkey]
            if isinstance(blk, dict):
                rate = blk.get("found_rate")
                lines.append(
                    f"| {zkey} | {format(rate, '.1%') if isinstance(rate, float) else '—'}"
                    f" | {fmt_quantiles(blk.get('first_m'), '.0f')} | {fmt_quantiles(blk.get('recovery'), '.2f')}"
                    f" | {fmt_quantiles(blk.get('post_move'))} |"
                )
    lines.append(
        "- 凍結值建議:z 取事件率適中之檔位;recovery / min_profit 取分佈自然分位。"
        "**注意:出現率為未套 recovery / min_profit gate 的上界**"
        "(gate 值由本表凍結,引擎實跑觸發率必然更低)。"
    )
    lines.append("")

    lines.append("## (c) 墊高解剖(讓肉 = 確認價 − 確認前最低,毛口徑)")
    lines.append("")
    lines.append("| k | 臂 | 出現率 | 確認分鐘 | 讓肉 | post_move(正=確認後續跌) |")
    lines.append("|---|---|---:|---|---|---|")
    c = result.get("c_higher_low")
    if isinstance(c, dict):
        for kkey in sorted(c):
            arms = c[kkey]
            if not isinstance(arms, dict):
                continue
            for akey in sorted(arms):
                blk = arms[akey]
                if isinstance(blk, dict):
                    rate = blk.get("found_rate")
                    lines.append(
                        f"| {kkey} | {akey}"
                        f" | {format(rate, '.1%') if isinstance(rate, float) else '—'}"
                        f" | {fmt_quantiles(blk.get('confirm_m'), '.0f')} | {fmt_quantiles(blk.get('giveback'))}"
                        f" | {fmt_quantiles(blk.get('post_move'))} |"
                    )
    lines.append("")

    lines.append("## (d) 內盤比 UC 分層 gate(前 15 分鐘累計;摸板 = high ≥ 漲停×0.99)")
    lines.append("")
    d = result.get("d_inner_gate")
    if isinstance(d, dict):
        combined = d.get("combined")
        if isinstance(combined, dict):
            lines.append("| 內盤比桶 | n | 摸板率 |")
            lines.append("|---|---:|---:|")
            for bkey in ("lt_0.45", "mid", "gt_0.55"):
                blk = combined.get(bkey)
                if isinstance(blk, dict):
                    r = blk.get("touch_rate")
                    lines.append(
                        f"| {bkey} | {blk.get('n')}"
                        f" | {format(r, '.1%') if isinstance(r, float) else '—'} |"
                    )
            lines.append("")
        lines.append(
            f"- gap 分層一致:{d.get('consistent_layers')}/{d.get('layers')};"
            f"判定 = {'PASS' if d.get('pass') else 'FAIL(inner_flip DEMOTE)'};"
            f"φ 建議 = {d.get('suggested_phi_grid')}。"
        )
        cells = d.get("cells")
        if isinstance(cells, dict) and cells:
            lines.append("")
            lines.append("| 桶:gap | n | 摸板率 |")
            lines.append("|---|---:|---:|")
            for key in sorted(cells):
                blk = cells[key]
                if isinstance(blk, dict):
                    r = blk.get("touch_rate")
                    lines.append(
                        f"| {key} | {blk.get('n')}"
                        f" | {format(r, '.1%') if isinstance(r, float) else '—'} |"
                    )
    lines.append("")

    lines.append("## (e) 緩漲觀察(≥10 根 close 不減、單根 ≤0.3%;僅描述)")
    lines.append("")
    e = result.get("e_slow_rally")
    if isinstance(e, dict):
        rate = e.get("rate")
        lines.append(
            f"- 出現率 = {format(rate, '.1%') if isinstance(rate, float) else '—'}"
            f"({e.get('days_with_segment')}/{e.get('n_days')});"
            f"段長 = {fmt_quantiles(e.get('segment_len'), '.0f')};"
            f"段末後 10 根 post_move(正=結束後下跌)= {fmt_quantiles(e.get('post_move'))}。"
        )
    lines.append("")

    atomic_write_text(path, "\n".join(lines) + "\n")
