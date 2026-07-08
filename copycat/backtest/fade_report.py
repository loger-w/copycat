"""T+1 Fade 報告模板(design.md v2 §10)."""

from __future__ import annotations

import os
from pathlib import Path


def write_fade_report(
    results: list[dict[str, object]],
    cfg: object,
    report_date: str,
    out_dir: Path,
    evidence_dir: Path | None = None,
) -> Path:
    """Markdown 報告."""
    lines: list[str] = []
    lines.append(f"# T+1 Fade(跟倒貨做空)GA 回測報告({report_date})")
    lines.append("")
    lines.append("## 方法論")
    lines.append("")
    lines.append("- 方向:T+1 當沖先賣(空),當日回補。")
    lines.append("- 進場:7 臂竭盡訊號偵測拉高翻轉,以觸發 bar close − 1 tick 悲觀賣出。")
    lines.append("- 成本:手續費 0.1425% × 2 + 當沖稅 0.15% = 0.435%。")
    lines.append("- 鎖死語意:漲停鎖死 → 凍結停損;全日鎖死 → 漲停價回補(最大損失)。")
    lines.append("- GA fitness = 加權扣成本期望值;三道驗證(test>0 / 月度 / 平台)。")
    lines.append("")

    lines.append("## 各臂結果")
    lines.append("")
    lines.append("| arm | param | triggered | rules(過三道) | lock_events |")
    lines.append("|---|---|---:|---:|---:|")

    for r in results:
        arm = r.get("arm", "?")
        param = r.get("param", {})
        n_trig = r.get("n_triggered", 0)
        rules = r.get("rules", [])
        n_rules = len(rules) if isinstance(rules, list) else 0
        lock = r.get("lock_events", 0)
        param_str = (
            " ".join(f"{k}={v}" for k, v in param.items())
            if isinstance(param, dict)
            else str(param)
        )
        lines.append(f"| {arm} | {param_str} | {n_trig} | {n_rules} | {lock} |")

    lines.append("")

    has_rules = False
    for r in results:
        rules = r.get("rules", [])
        if isinstance(rules, list) and rules:
            has_rules = True
            break

    if has_rules:
        lines.append("## 存活規則(三道驗證)")
        lines.append("")
        for r in results:
            rules = r.get("rules", [])
            if not isinstance(rules, list) or not rules:
                continue
            arm = r.get("arm", "?")
            param = r.get("param", {})
            lines.append(f"### {arm} ({param})")
            lines.append("")
            for i, rule in enumerate(rules[:10]):
                conds = rule.get("conditions", [])
                exp = rule.get("expectancy_train", 0)
                lines.append(f"- rank {i}: {conds} (train exp={exp:.4f})")
            lines.append("")
    else:
        lines.append("## 存活規則")
        lines.append("")
        lines.append("無規則通過三道驗證。")
        lines.append("")

    lines.append("## 負結果")
    lines.append("")
    for r in results:
        arm = r.get("arm", "?")
        param = r.get("param", {})
        rules = r.get("rules", [])
        n_rules = len(rules) if isinstance(rules, list) else 0
        n_trig = r.get("n_triggered", 0)
        lines.append(f"- {arm} ({param}): triggered={n_trig}, rules={n_rules}")
    lines.append("")

    content = "\n".join(lines) + "\n"

    report_path = out_dir / f"tday_fade_backtest_{report_date}.md"
    tmp = report_path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, report_path)

    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ev_path = evidence_dir / f"tday_fade_backtest_{report_date}.md"
        ev_tmp = ev_path.with_suffix(".tmp")
        ev_tmp.write_text(content, encoding="utf-8")
        os.replace(ev_tmp, ev_path)

    return report_path
