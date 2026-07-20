"""Round 5 §0 進場訊號解剖(spec 2026-07-17,已凍結)— fade-entry-anatomy CLI。

兩節:(a) 流向反轉(分鐘級近似;攻擊段前置 vs 無前置對照)、
(c) CDP / 均線位階對決(線距 gate 2% / 觸發率 gate 10% / 固定拉幅對決)。
設計輸入不入判定;(b) tick 級增量待 (a) GO 後另跑(tick 回補依賴達錢 4 常駐)。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_diagnose import cluster_se
from copycat.backtest.fade_simulate import FadeSample
from copycat.backtest.fade_vote import iter_flow_flip
from copycat.backtest.quantiles import quantiles_round
from copycat.backtest.report_fmt import fmt_quantiles
from copycat.data.daily import DailyIndex
from copycat.data.models import Bar1K
from copycat.fileio import atomic_write_text

logger = logging.getLogger(__name__)

_Universe = list[tuple[FadeSample, list[Bar1K]]]

# 凍結值(spec §a / §c;2026-07-17 拍板)
_MIN_SEG_GAIN = 0.01
_FALSE_RATE_FRACTION = 2.0 / 3.0
_WIDTH_DROP_MEDIAN = 0.02
_TRIGGER_DROP_RATE = 0.10
_NEAR_EPS = 0.005
_FIXED_PULL_BAND = (0.033, 0.041)
_DUEL_Z_ONE_SIDED = 1.645


# ---------- (a) 流向反轉 ----------


def _first_flip(
    bars: list[Bar1K], rho: float, confirm: int, *, require_attack: bool, n: int
) -> int | None:
    """回傳翻轉 bar 的 list index;require_attack=False 為無前置對照(自 index 1 起掃)。

    狀態機 = fade_vote.iter_flow_flip 單一實作(攻擊段 armed / 翻轉判定同定義,
    seg_gain 用本模組凍結值 _MIN_SEG_GAIN)。
    """
    for i, _b, _armed, flipped in iter_flow_flip(
        bars, n=n, rho=rho, confirm=confirm, seg_gain=_MIN_SEG_GAIN,
        require_attack=require_attack,
    ):
        if flipped:
            return i
    return None


def flow_flip_anatomy(
    uni: _Universe,
    ns: tuple[int, ...] = (3, 5),
    rhos: tuple[float, ...] = (1.0, 1.5),
    confirms: tuple[int, ...] = (1, 2),
) -> dict[str, object]:
    """流向反轉解剖:N×ρ×確認根數 8 組 + 無前置對照(ρ×確認 4 組)。

    post_move = (翻轉 close − 收盤 close)/翻轉 close;正 = 翻轉後續跌(訊號有肉)。
    false = 翻轉後任一 bar high > 翻轉當下的當日最高(被洗)。
    對照組 = round 4 已證偽的「無前置條件反轉」,驗攻擊段前置是否洗掉噪音。
    """

    def _scan(rho: float, confirm: int, *, require_attack: bool, n: int) -> dict[str, object]:
        firsts: list[float] = []
        post_moves: list[float] = []
        false_cnt = 0
        found = 0
        for _sample, bars in uni:
            if len(bars) < 2:
                continue
            idx = _first_flip(bars, rho, confirm, require_attack=require_attack, n=n)
            if idx is None:
                continue
            found += 1
            hit = bars[idx]
            firsts.append(float(hit.m))
            if hit.close > 0:
                post_moves.append((hit.close - bars[-1].close) / hit.close)
            high_at_flip = max(b.high for b in bars[: idx + 1])
            if any(b.high > high_at_flip for b in bars[idx + 1 :]):
                false_cnt += 1
        return {
            "n_days": len(uni),
            "found": found,
            "found_rate": (found / len(uni)) if uni else None,
            "first_m": quantiles_round(firsts),
            "post_move": quantiles_round(post_moves),
            "false_rate": (false_cnt / found) if found else None,
        }

    out: dict[str, object] = {}
    for rho in rhos:
        for c in confirms:
            out[f"ctrl_r{rho:g}_c{c}"] = _scan(rho, c, require_attack=False, n=0)
            for n in ns:
                out[f"N{n}_r{rho:g}_c{c}"] = _scan(rho, c, require_attack=True, n=n)
    return out


def flow_flip_go(
    post_move_p50: float | None, false_rate: float | None, ctrl_false_rate: float | None
) -> bool:
    """凍結判準(spec §a):post_move p50 > 0 且 false_rate < 對照 × 2/3;
    統計不可得一律 DROP(保守向)。"""
    if post_move_p50 is None or false_rate is None or ctrl_false_rate is None:
        return False
    return post_move_p50 > 0 and false_rate < ctrl_false_rate * _FALSE_RATE_FRACTION


# ---------- (c) CDP / 位階對決 ----------

_CDP_LINES = ("cdp", "ah", "nh", "nl", "al")
_MA_LINES = ("ma5", "ma10", "ma20")


@dataclass(frozen=True, slots=True)
class _DayRec:
    t1_date: str
    t1_open: float
    high: float
    close: float
    levels: dict[str, float | None]


def cdp_levels(h: float, low: float, c: float) -> dict[str, float]:
    """CDP 五值(前日 H/L/C):CDP=(H+L+2C)/4、AH=CDP+(H−L)、NH=2CDP−L、
    NL=2CDP−H、AL=CDP−(H−L)。"""
    cdp = (h + low + 2 * c) / 4
    rng = h - low
    return {"cdp": cdp, "ah": cdp + rng, "nh": 2 * cdp - low, "nl": 2 * cdp - h, "al": cdp - rng}


def _build_day_recs(uni: _Universe, daily: DailyIndex) -> tuple[list[_DayRec], list[float]]:
    """共用:UC 池 T+1 日紀錄(位階線值 + 當日高/收)與 CDP 線距分佈。"""
    day_recs: list[_DayRec] = []
    widths: list[float] = []
    for sample, bars in uni:
        if not bars:
            continue
        ohlc_t = daily.ohlc(sample.stock_id, sample.date)
        if ohlc_t is None:
            continue
        _o, h, low, c = ohlc_t
        if c <= 0:
            continue
        levels: dict[str, float | None] = dict(cdp_levels(h, low, c))
        ah, al = levels["ah"], levels["al"]
        widths.append((ah - al) / c if ah is not None and al is not None else 0.0)
        for name, n in zip(_MA_LINES, (5, 10, 20)):
            levels[name] = daily.ma(sample.stock_id, sample.date, n)
        day_recs.append(
            _DayRec(
                t1_date=sample.t1_date,
                t1_open=sample.t1_open,
                high=max(b.high for b in bars),
                close=bars[-1].close,
                levels=levels,
            )
        )
    return day_recs, widths


def _two_sample_cluster(
    a: list[tuple[float, str]], b: list[tuple[float, str]]
) -> tuple[float, float]:
    """兩組 (value, day) 的 two-sample cluster-z 素材:(均值差, 變異數和 se_a²+se_b²)
    (level_stratified_duel 加權版 / level_anatomy duel 直接版共用)。呼叫端保證兩組非空。"""
    mean_a = sum(v for v, _ in a) / len(a)
    mean_b = sum(v for v, _ in b) / len(b)
    se_a = cluster_se([v for v, _ in a], [d for _, d in a])
    se_b = cluster_se([v for v, _ in b], [d for _, d in b])
    return mean_a - mean_b, se_a**2 + se_b**2


def _near_line(rec: _DayRec, names: tuple[str, ...]) -> bool:
    for name in names:
        v = rec.levels.get(name)
        if v is not None and v > 0 and v >= rec.t1_open and abs(rec.high - v) / v <= _NEAR_EPS:
            return True
    return False


def level_stratified_duel(
    uni: _Universe,
    daily: DailyIndex,
    lines: tuple[str, ...] = ("ah", "nh"),
    strata_edges: tuple[float, ...] = (0.02, 0.04, 0.06),
    day_recs: list[_DayRec] | None = None,
) -> dict[str, object]:
    """0′(1) 拉幅混淆補驗(round 5 prereg §0′,判準凍結):同拉幅層內
    貼 AH/NH vs 不貼的 post_move 對照。

    PASS(寫死)= 有資料的層 ≥2/3 方向一致(貼線更差)且分層合併
    z ≥ 1.645(逆變異數加權,cluster_se 日聚類);FAIL → 位階票降級觀察。
    層需兩組各 ≥2 筆才入計。
    """
    if day_recs is None:
        day_recs, _ = _build_day_recs(uni, daily)
    edges = (*strata_edges, float("inf"))
    strata: dict[str, object] = {}
    layers = 0
    consistent = 0
    num = 0.0
    wsum = 0.0
    for lo, hi in zip(edges, edges[1:]):
        key = f"pull_{lo:g}_{hi:g}"
        near: list[tuple[float, str]] = []
        far: list[tuple[float, str]] = []
        for rec in day_recs:
            if rec.high <= 0 or rec.t1_open <= 0:
                continue
            pull = rec.high / rec.t1_open - 1.0
            if not (lo <= pull < hi):
                continue
            post = (rec.high - rec.close) / rec.high
            (near if _near_line(rec, lines) else far).append((post, rec.t1_date))
        blk: dict[str, object] = {
            "n_near": len(near),
            "n_far": len(far),
            "post_move_near": quantiles_round([v for v, _ in near]),
            "post_move_far": quantiles_round([v for v, _ in far]),
        }
        if len(near) >= 2 and len(far) >= 2:
            diff, var = _two_sample_cluster(near, far)
            blk["diff"] = diff
            blk["consistent"] = diff > 0
            layers += 1
            if diff > 0:
                consistent += 1
            if var > 0:
                w = 1.0 / var
                num += w * diff
                wsum += w
        strata[key] = blk
    z: float | None = (num / (wsum**0.5)) if wsum > 0 else None
    passed = (
        layers > 0
        and (consistent / layers) >= (2.0 / 3.0)
        and isinstance(z, float)
        and z >= _DUEL_Z_ONE_SIDED
    )
    return {
        "strata": strata,
        "layers": layers,
        "consistent_layers": consistent,
        "z": z,
        "pass": passed,
    }


def level_anatomy(
    uni: _Universe,
    daily: DailyIndex,
    prebuilt: tuple[list[_DayRec], list[float]] | None = None,
) -> dict[str, object]:
    """位階對決:CDP 線距 gate(中位 < 2% 整組出局)→ 各線觸發率 gate(< 10% 出局)
    → 存活線 vs 固定拉幅帶(開盤 × 1.033~1.041)的 post_move 對決。

    適用 = 線值 ≥ T+1 開盤(壓力位語意);觸發 = 當日高距線 ≤ ±0.5%;
    post_move = (當日高 − 收盤)/當日高,正 = 見高回落(位階若有訊息,貼線子集應更差)。
    """
    day_recs, widths = prebuilt if prebuilt is not None else _build_day_recs(uni, daily)

    width_q = quantiles_round(widths)
    width_p50 = width_q.get("p50")
    cdp_drop = not isinstance(width_p50, float) or width_p50 < _WIDTH_DROP_MEDIAN

    lines: dict[str, dict[str, object]] = {}
    for name in _CDP_LINES + _MA_LINES:
        applicable = 0
        trigger = 0
        for rec in day_recs:
            v = rec.levels.get(name)
            if v is None or v <= 0 or v < rec.t1_open:
                continue
            applicable += 1
            if abs(rec.high - v) / v <= _NEAR_EPS:
                trigger += 1
        rate = (trigger / applicable) if applicable else None
        lines[name] = {
            "applicable": applicable,
            "trigger": trigger,
            "trigger_rate": rate,
            "drop": rate is None or rate < _TRIGGER_DROP_RATE,
        }

    surviving = [
        name
        for name, blk in lines.items()
        if not blk["drop"] and not (cdp_drop and name in _CDP_LINES)
    ]

    groups: dict[str, list[tuple[float, str]]] = {
        "near_level_only": [],
        "near_fixed_only": [],
        "both": [],
        "neither": [],
    }
    lo_band, hi_band = _FIXED_PULL_BAND
    for rec in day_recs:
        if rec.high <= 0 or rec.t1_open <= 0:
            continue
        pull = rec.high / rec.t1_open - 1.0
        near_fixed = (lo_band - _NEAR_EPS) <= pull <= (hi_band + _NEAR_EPS)
        near_level = False
        for name in surviving:
            v = rec.levels.get(name)
            if v is not None and v > 0 and abs(rec.high - v) / v <= _NEAR_EPS:
                near_level = True
                break
        key = (
            "both"
            if near_level and near_fixed
            else "near_level_only"
            if near_level
            else "near_fixed_only"
            if near_fixed
            else "neither"
        )
        groups[key].append(((rec.high - rec.close) / rec.high, rec.t1_date))

    group_blocks: dict[str, object] = {
        key: {"n": len(vals), "post_move": quantiles_round([v for v, _ in vals])}
        for key, vals in groups.items()
    }
    a = groups["near_level_only"]
    b = groups["neither"]
    z: float | None = None
    if a and b:
        diff, var = _two_sample_cluster(a, b)
        denom = var**0.5
        if denom > 0:
            z = diff / denom
    go = isinstance(z, float) and z >= _DUEL_Z_ONE_SIDED

    return {
        "n_days": len(day_recs),
        "cdp_width": {**width_q, "median": width_p50},
        "cdp_drop": cdp_drop,
        "lines": lines,
        "surviving_lines": surviving,
        "duel": {
            "fixed_band": list(_FIXED_PULL_BAND),
            **group_blocks,
            "z": z,
            "go": go,
        },
    }


# ---------- CLI 協調 ----------


def run_entry_anatomy(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    report_date: str,
    watchlist_path: Path,
    report_dir: Path | None = None,
) -> Path:
    """§0 進場訊號解剖 → entry_anatomy.json + evidence md(in-window;不入判定)。"""
    from copycat.backtest.fade_cells import build_universes, is_uc_sample
    from copycat.watchlist import load_watchlist

    watchlist = load_watchlist(watchlist_path)
    ids = watchlist.broker_ids
    universes, _counts = build_universes(data_dir, cfg)
    main_uc: _Universe = [
        (s, b)
        for s, b in universes.get("main", [])
        if is_uc_sample(s, ids) and s.t1_date < cfg.forward_start
    ]
    logger.info("entry anatomy universe main_uc=%d", len(main_uc))

    daily = DailyIndex.load(data_dir)
    a = flow_flip_anatomy(main_uc)
    logger.info("entry anatomy (a) flow flip done")
    built = _build_day_recs(main_uc, daily)  # (c) 與 (0′) 共用,建一次
    c = level_anatomy(main_uc, daily, prebuilt=built)
    logger.info("entry anatomy (c) levels done(cdp_drop=%s)", c.get("cdp_drop"))
    strat = level_stratified_duel(main_uc, daily, day_recs=built[0])
    logger.info("entry anatomy (0') stratified duel done(pass=%s)", strat.get("pass"))

    # (a) GO/DROP:各訊號組對照同 ρ×confirm 的 ctrl
    verdicts: dict[str, bool] = {}
    for key, blk in a.items():
        if key.startswith("ctrl_") or not isinstance(blk, dict):
            continue
        ctrl_key = "ctrl_" + key.split("_", 1)[1]
        ctrl = a.get(ctrl_key)
        post = blk.get("post_move")
        p50 = post.get("p50") if isinstance(post, dict) else None
        fr = blk.get("false_rate")
        cfr = ctrl.get("false_rate") if isinstance(ctrl, dict) else None
        verdicts[key] = flow_flip_go(
            p50 if isinstance(p50, float) else None,
            fr if isinstance(fr, float) else None,
            cfr if isinstance(cfr, float) else None,
        )
    flow_go = any(verdicts.values())

    duel = c.get("duel")
    level_go = bool(duel.get("go")) if isinstance(duel, dict) else False
    result: dict[str, object] = {
        "report_date": report_date,
        "in_window_lt": cfg.forward_start,
        "n_uc_main": len(main_uc),
        "a_flow_flip": a,
        "a_verdicts": verdicts,
        "c_levels": c,
        "c_stratified": strat,
        "verdicts": {
            "flow_flip": "GO" if flow_go else "DROP",
            "tick_backfill": "GO" if flow_go else "HOLD",  # (b) 依賴 (a) GO(spec 資料前置 #2)
            "cdp": "DROP" if c.get("cdp_drop") else ("GO" if level_go else "NO_INCREMENT"),
            "level_duel": "GO" if level_go else "DROP",
            # 0′(1) 拉幅混淆補驗(round 5 prereg):FAIL → 位階票降級觀察
            "level_vote": "KEEP" if strat.get("pass") else "DEMOTE",
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"entry_anatomy_{report_date}.json"
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1))

    report_path = out_dir / f"fade_round5_entry_anatomy_{report_date}.md"
    _write_report(result, report_path)
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        _write_report(result, report_dir / report_path.name)
    return report_path


def _fmt_rate(v: object) -> str:
    return format(v, ".1%") if isinstance(v, float) else "—"


def _write_report(result: dict[str, object], path: Path) -> None:
    lines: list[str] = []
    lines.append(
        f"# Round 5 §0 進場訊號解剖({result.get('report_date')};設計輸入,不入判定)"
    )
    lines.append("")
    lines.append(
        f"- 宇宙:UC 池 in-window(< {result.get('in_window_lt')});"
        f"main n={result.get('n_uc_main')};判準凍結出處 = "
        "`docs/superpowers/specs/2026-07-17-fade-round5-entry-anatomy-draft.md`。"
    )
    verdicts = result.get("verdicts")
    if isinstance(verdicts, dict):
        lines.append(
            f"- **判準輸出**:flow_flip: **{verdicts.get('flow_flip')}**;"
            f"tick 回補: **{verdicts.get('tick_backfill')}**;"
            f"CDP: **{verdicts.get('cdp')}**;位階對決: **{verdicts.get('level_duel')}**。"
        )
    lines.append("")

    lines.append("## (a) 流向反轉(攻擊段 = 連續 N 根外盤佔優且段內漲 ≥1%;分鐘級)")
    lines.append("")
    lines.append("| 組 | 出現率 | 首次分鐘 | post_move(正=翻轉後續跌) | 假訊號率 | GO |")
    lines.append("|---|---:|---|---|---:|---|")
    a = result.get("a_flow_flip")
    av = result.get("a_verdicts")
    if isinstance(a, dict):
        for key in sorted(a):
            blk = a[key]
            if not isinstance(blk, dict):
                continue
            go = ""
            if isinstance(av, dict) and key in av:
                go = "**GO**" if av[key] else "DROP"
            lines.append(
                f"| {key} | {_fmt_rate(blk.get('found_rate'))}"
                f" | {fmt_quantiles(blk.get('first_m'), '.0f')} | {fmt_quantiles(blk.get('post_move'))}"
                f" | {_fmt_rate(blk.get('false_rate'))} | {go} |"
            )
    lines.append("")
    lines.append(
        "- 凍結判準:post_move p50 > 0 且假訊號率 < 同 ρ×確認 對照組(ctrl_*,無前置)"
        "× 2/3。ctrl 行即 round 4 已證偽的「隨機時點反轉」語意。"
    )
    lines.append("")

    lines.append("## (c) 位階對決(CDP 由 T 日 H/L/C;MA 以 T 日收盤計)")
    lines.append("")
    c = result.get("c_levels")
    if isinstance(c, dict):
        width = c.get("cdp_width")
        med = width.get("median") if isinstance(width, dict) else None
        lines.append(
            f"- CDP 線距 (AH−AL)/T日收:中位 = {_fmt_rate(med)}"
            f"(分佈 {fmt_quantiles(width)});出局線 2% → "
            f"**{'DROP(全組出局)' if c.get('cdp_drop') else 'PASS'}**。"
        )
        lines.append("")
        lines.append("| 線 | 適用 n(線 ≥ T+1 開盤) | 觸發 n | 觸發率 | 判定 |")
        lines.append("|---|---:|---:|---:|---|")
        lns = c.get("lines")
        if isinstance(lns, dict):
            for name in ("cdp", "ah", "nh", "nl", "al", "ma5", "ma10", "ma20"):
                blk = lns.get(name)
                if not isinstance(blk, dict):
                    continue
                lines.append(
                    f"| {name} | {blk.get('applicable')} | {blk.get('trigger')}"
                    f" | {_fmt_rate(blk.get('trigger_rate'))}"
                    f" | {'出局' if blk.get('drop') else '存活'} |"
                )
        lines.append("")
        lines.append(f"- 存活線:{c.get('surviving_lines') or '(無)'}")
        duel = c.get("duel")
        if isinstance(duel, dict):
            lines.append("")
            lines.append(
                "| 組(當日高的位置) | n | post_move(正=見高回落) |"
            )
            lines.append("|---|---:|---|")
            for key, label in (
                ("near_level_only", "貼位階線(非固定拉幅帶)"),
                ("near_fixed_only", "貼固定拉幅帶 3.3~4.1%"),
                ("both", "兩者皆貼"),
                ("neither", "皆不貼"),
            ):
                blk = duel.get(key)
                if isinstance(blk, dict):
                    lines.append(
                        f"| {label} | {blk.get('n')} | {fmt_quantiles(blk.get('post_move'))} |"
                    )
            z = duel.get("z")
            lines.append("")
            lines.append(
                f"- 增量檢定(貼線 vs 皆不貼,日聚類單尾):z = "
                f"{format(z, '.2f') if isinstance(z, float) else '—'}"
                f"(門檻 1.645)→ **{'GO' if duel.get('go') else 'DROP(無增量)'}**。"
            )
    lines.append("")

    strat = result.get("c_stratified")
    if isinstance(strat, dict):
        lines.append("## (0′) 位階同拉幅分層對照(round 5 prereg;拉幅混淆補驗)")
        lines.append("")
        lines.append("| 拉幅層 | 貼線 n | 不貼 n | 貼線 post_move | 不貼 post_move | 差 |")
        lines.append("|---|---:|---:|---|---|---:|")
        st = strat.get("strata")
        if isinstance(st, dict):
            for key in sorted(st):
                blk = st[key]
                if not isinstance(blk, dict):
                    continue
                d = blk.get("diff")
                lines.append(
                    f"| {key} | {blk.get('n_near')} | {blk.get('n_far')}"
                    f" | {fmt_quantiles(blk.get('post_move_near'))} | {fmt_quantiles(blk.get('post_move_far'))}"
                    f" | {format(d, '+.2%') if isinstance(d, float) else '—'} |"
                )
        sz = strat.get("z")
        lines.append("")
        lines.append(
            f"- 方向一致層:{strat.get('consistent_layers')}/{strat.get('layers')}"
            f"(門檻 ≥2/3);分層合併 z = "
            f"{format(sz, '.2f') if isinstance(sz, float) else '—'}(門檻 1.645)→ "
            f"**{'PASS(位階票保留)' if strat.get('pass') else 'FAIL(位階票降級觀察,投票縮兩訊號)'}**。"
        )
        lines.append("")

    atomic_write_text(path, "\n".join(lines) + "\n")
