"""Evidence 報告(SC-8,spec §9)— determinism:無 timestamp,日期由 CLI 傳入."""

from __future__ import annotations

import json
from pathlib import Path

from copycat.backtest.config import BacktestConfig


def _fmt(v: object) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.4f}" if abs(v) < 1 else f"{v:.2f}"
    return str(v)


def write_report(
    out_dir: Path,
    result: dict[str, object],
    counts: dict[str, object],
    report_date: str,
    cfg: BacktestConfig,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tday_join_ga_backtest_{report_date}.md"
    rules = result.get("rules", [])
    assert isinstance(rules, list)

    lines: list[str] = [
        f"# T 日跟多隔日沖 GA 回測報告(Phase A,{report_date})",
        "",
        "## 方法論",
        "",
        "- 決策點:盤中第一次 high ≥ 前收 ×(1+θ) 的分鐘;特徵只用該時點前資訊(無 lookahead)。",
        "- 進場 = 觸發 bar close + 1 tick(悲觀,cap 漲停價);停損自下一根 bar 起評估;"
        "鎖死 bar 凍結停損。",
        f"- 成本分軌:當日出場稅 {cfg.intraday_tax:.4f}(現股當沖減半)、留倉出場稅 "
        f"{cfg.overnight_tax:.4f}、手續費 {cfg.fee_rate:.6f}×2 — 與 spec 單一 0.585% 假設不同"
        "(全稅會系統性懲罰停損積極臂)。",
        "- GA fitness = 加權扣成本期望值 − 支持不足罰項,**不含 MDD**(偏離 spec §8;"
        "MDD 於階段③展開時計算並過濾)。",
        "- near_miss 樣本為 1/5 抽樣,所有統計加權 ×5。",
        "- dtr_t1(當沖比)Phase A 無資料源,全 None(known limitation)。",
        f"- 時間切分:train < {cfg.split_date} ≤ test;**下表只報 test**。",
        "",
        "## regime × 規則(三道驗證)",
        "",
    ]
    if not rules:
        lines += ["通過三道驗證的規則:**無**。", ""]
    else:
        lines += [
            "| regime | 條件 | test 期望值 | P(win) | 賺賠比 | MDD | n | 月度 | 平台 | 過三道 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rules:
            assert isinstance(r, dict)
            conds = " & ".join(
                f"{c['feature']}{c['op']}{_fmt(c['threshold'])}" for c in r["conditions"]
            )
            lines.append(
                f"| {r['regime']} | {conds} | {_fmt(r.get('test_expectancy'))} "
                f"| {_fmt(r.get('test_p_win'))} | {_fmt(r.get('test_payoff'))} "
                f"| {_fmt(r.get('test_mdd'))} | {r.get('test_n_raw')} "
                f"| {'✓' if r.get('monthly_passed') else '✗'} "
                f"| {'✓' if r.get('plateau_passed') else '✗'} "
                f"| {'**✓**' if r.get('passed_all') else '✗'} |"
            )
        lines.append("")

    lines += ["## θ 曲線(test 期望值,baseline 停損組)", ""]
    curves = result.get("theta_curves", {})
    assert isinstance(curves, dict)
    if curves:
        thetas = sorted({t for c in curves.values() for t in c})
        lines.append("| 規則 | " + " | ".join(f"θ={t}" for t in thetas) + " |")
        lines.append("|---|" + "---|" * len(thetas))
        for name in sorted(curves):
            c = curves[name]
            lines.append(
                f"| {name} | " + " | ".join(_fmt(c.get(t)) for t in thetas) + " |"
            )
    else:
        lines.append("(無資料)")
    lines.append("")

    lines += ["## 停損族對決(test)", ""]
    duel = result.get("stop_duel", {})
    assert isinstance(duel, dict)
    if duel:
        lines.append("| 停損組 | 期望值 | P(win) | 賺賠比 | MDD | n |")
        lines.append("|---|---|---|---|---|---|")
        for combo_id in sorted(duel):
            s = duel[combo_id]
            lines.append(
                f"| {combo_id} | {_fmt(s.get('expectancy'))} | {_fmt(s.get('p_win'))} "
                f"| {_fmt(s.get('payoff'))} | {_fmt(s.get('mdd'))} | {s.get('n_raw')} |"
            )
    else:
        lines.append("(無資料)")
    lines += [
        "",
        "## 出場對決",
        "",
        "Phase A 僅 E1(T+1 開盤價賣);E2/E3(SOP 條件出場 / 鎖板品質分層)待 Phase B "
        "資料回補(ctrl T+1 1K)後補跑。",
        "",
        "## 開盤即攻分桶(<09:05 觸發,悲觀滑價)",
        "",
    ]
    early = result.get("early_attack", {})
    assert isinstance(early, dict)
    lines.append(json.dumps(early, ensure_ascii=False, sort_keys=True) if early else "(無資料)")
    lines += ["", "## 滑價壓測(+1 tick 基準 vs +2 tick)", ""]
    stress = result.get("slippage_stress", {})
    assert isinstance(stress, dict)
    lines.append(json.dumps(stress, ensure_ascii=False, sort_keys=True) if stress else "(無資料)")
    lines += ["", "## 3055 蔚華科 case(低位階啟動 regime sanity)", ""]
    case = result.get("case_3055")
    lines.append(json.dumps(case, ensure_ascii=False, sort_keys=True) if case else "樣本中無 3055 觸發事件。")
    lines += ["", "## 剔除計數(no silent caps)", ""]
    lines.append("```json")
    lines.append(json.dumps(counts, ensure_ascii=False, sort_keys=True, indent=1))
    lines.append("```")
    lines += ["", "## 負結果(與成立的一樣重要)", ""]
    negatives = result.get("negative_findings", [])
    assert isinstance(negatives, list)
    lines += [f"- {n}" for n in negatives] if negatives else ["(無)"]
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
