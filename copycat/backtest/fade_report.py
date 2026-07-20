"""T+1 Fade 報告模板(design.md v2 §10)."""

from __future__ import annotations

from pathlib import Path

from copycat.fileio import atomic_write_text


def _fmt(v: object, fmt: str = ".4f") -> str:
    return f"{v:{fmt}}" if isinstance(v, float | int) else "—"


def write_fade_report(
    results: list[dict[str, object]],
    cfg: object,
    report_date: str,
    out_dir: Path,
    evidence_dir: Path | None = None,
    cross_arm_table: list[dict[str, object]] | None = None,
    diagnose: dict[str, object] | None = None,
    universe_counts: dict[str, int] | None = None,
) -> Path:
    """Markdown 報告."""
    fee_rate = float(getattr(cfg, "fee_rate", 0.001425))
    fee_discount = float(getattr(cfg, "fee_discount", 0.0))
    tax = float(getattr(cfg, "intraday_tax", 0.0015))
    cost = fee_rate * (1.0 - fee_discount) * 2.0 + tax
    guard = getattr(cfg, "guard_limit_dist", None)
    disaster = getattr(cfg, "disaster_x", None)
    lock_pen = getattr(cfg, "lock_penalty", None)
    wf_starts = tuple(getattr(cfg, "wf_test_starts", ()) or ())
    dt_filter = bool(getattr(cfg, "universe_daytrade_filter", False))

    lines: list[str] = []
    lines.append(f"# T+1 Fade(跟倒貨做空)GA 回測報告({report_date})")
    lines.append("")
    lines.append("## 方法論")
    lines.append("")
    lines.append("- 方向:T+1 當沖先賣(空),當日回補。")
    lines.append("- 進場:7 臂竭盡訊號偵測拉高翻轉,以觸發 bar close − 1 tick 悲觀賣出。")
    lines.append(
        f"- 成本:手續費 {fee_rate:.6f} ×(1−{fee_discount:.2f})× 2 + 當沖稅 {tax:.4f}"
        f" = **{cost:.4%}**/來回。"
    )
    if guard is not None or disaster is not None:
        lines.append(
            f"- 強制風控:防鎖 guard 距漲停 {_fmt(guard, '.1%')} 強制回補、"
            f"災難停損 entry+{_fmt(disaster, '.1%')}(不入搜索,永遠生效)。"
        )
    if lock_pen is not None:
        lines.append(f"- 鎖死語意(悲觀化):全日鎖死 → 漲停 ×(1+{lock_pen:.2f})回補。")
    else:
        lines.append("- 鎖死語意:漲停鎖死 → 凍結停損;全日鎖死 → 漲停價回補(最大損失)。")
    lines.append(
        f"- 當沖資格過濾:{'**生效**(處置期間 + 非當沖名單剔除)' if dt_filter else '未啟用'}。"
    )
    if wf_starts:
        lines.append(
            f"- 驗證:**walk-forward**(fold test 起點 {', '.join(wf_starts)};"
            "GA 只在 core、選擇只在 val,fold-test 不進任何選擇)。"
            "OOS = 各 fold top-1 串接。"
        )
    else:
        lines.append("- GA fitness = 加權扣成本期望值;三道驗證(test>0 / 月度 / 平台)。")
    if universe_counts:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(universe_counts.items()))
        lines.append(f"- Universe counts:{parts}。")
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

    if cross_arm_table:
        min_n = int(getattr(cfg, "min_n_test", 0))
        main_rows = [r for r in cross_arm_table if not r.get("appendix")]
        appendix_rows = [r for r in cross_arm_table if r.get("appendix")]

        def _cross_row(row: dict[str, object]) -> str:
            stress = "PASS" if row.get("stress_passed") else "FAIL"
            extra = ""
            if wf_starts:
                extra = f" {row.get('fold_positive', '—')}/{row.get('n_folds', '—')} |"
            return (
                f"| {row.get('rank', '?')} | {row.get('arm', '?')}"
                f" | {row.get('param', '')}"
                f" | {_fmt(row.get('test_exp'))}"
                f" | {_fmt(row.get('stress_exp'))}"
                f" | {_fmt(row.get('p_win'), '.2f')}"
                f" | {_fmt(row.get('payoff'), '.1f')}"
                f" | {_fmt(row.get('mdd'))}"
                f" | {_fmt(row.get('lock_pct'), '.1%') if isinstance(row.get('lock_pct'), float | int) else '—'}"
                f" | {stress}"
                f" | {row.get('best_stop', '—')}"
                f" | {row.get('best_tp', '—')}"
                f" | {row.get('n_test', '?')} |" + extra
            )

        header = (
            "| rank | arm | param | test_exp | stress_exp"
            " | p_win | payoff | MDD | lock% | stress | best_stop | best_tp | n_test |"
        )
        sep = "|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|"
        if wf_starts:
            header += " fold+ |"
            sep += "---:|"

        lines.append("## 臂間對決" + ("(walk-forward OOS)" if wf_starts else "(Phase B)"))
        lines.append("")
        if wf_starts:
            lines.append(
                "> ⚠ 17 臂多重比較 caveat:本表排序僅供展示;每臂代表規則於 val 側選定,"
                "但「挑最高的臂」仍消耗 OOS,不得以本表排名回頭調參(R4/R5)。"
            )
            lines.append("")
        lines.append(header)
        lines.append(sep)
        for row in main_rows:
            lines.append(_cross_row(row))
        lines.append("")
        if appendix_rows:
            lines.append(f"### 附錄:n_test < {min_n} 的臂(樣本不足,不列入主表)")
            lines.append("")
            lines.append(header)
            lines.append(sep)
            for row in appendix_rows:
                lines.append(_cross_row(row))
            lines.append("")

    wf_results = [r for r in results if isinstance(r.get("wf"), dict)]
    if wf_results:
        lines.append("## Walk-forward 分層(tiger vs control)")
        lines.append("")
        lines.append("| arm | param | source | OOS exp | p_win | payoff | MDD | n |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for r in wf_results:
            wf = r["wf"]
            assert isinstance(wf, dict)
            by_source = wf.get("oos_by_source")
            if not isinstance(by_source, dict):
                continue
            for src, s in sorted(by_source.items()):
                if not isinstance(s, dict):
                    continue
                lines.append(
                    f"| {r.get('arm', '?')} | {r.get('param', '')} | {src}"
                    f" | {_fmt(s.get('expectancy'))} | {_fmt(s.get('p_win'), '.2f')}"
                    f" | {_fmt(s.get('payoff'), '.1f')} | {_fmt(s.get('mdd'))}"
                    f" | {s.get('n', 0)} |"
                )
        lines.append("")

        lines.append("## Guard 敏感度(僅診斷;dist 選擇依據 = train/val,不得依此表調參)")
        lines.append("")
        lines.append("| arm | param | guard dist | OOS exp | n |")
        lines.append("|---|---|---:|---:|---:|")
        for r in wf_results:
            wf = r["wf"]
            assert isinstance(wf, dict)
            sens = wf.get("guard_sensitivity")
            if not isinstance(sens, dict):
                continue
            for dist, s in sorted(sens.items()):
                if not isinstance(s, dict):
                    continue
                lines.append(
                    f"| {r.get('arm', '?')} | {r.get('param', '')} | {dist}"
                    f" | {_fmt(s.get('expectancy'))} | {s.get('n', 0)} |"
                )
        lines.append("")

    if diagnose:
        lines.append("## 逼近漲停診斷(全 universe;P(鎖|逼近)與嘎空回落深度)")
        lines.append("")
        lines.append(
            "| dist | bucket | n | P(鎖) | P(回落) | 回落深度 med | p25 | p75 |"
        )
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
        per_dist = diagnose.get("per_dist")
        if isinstance(per_dist, dict):
            for dist, entry in sorted(per_dist.items()):
                if not isinstance(entry, dict):
                    continue
                overall = entry.get("overall")
                rows_to_show: list[tuple[str, object]] = [("overall", overall)]
                buckets = entry.get("buckets")
                if isinstance(buckets, dict):
                    rows_to_show.extend(sorted(buckets.items()))
                for name, s in rows_to_show:
                    if not isinstance(s, dict):
                        continue
                    lines.append(
                        f"| {dist} | {name} | {s.get('n', 0)}"
                        f" | {_fmt(s.get('p_lock'), '.1%')}"
                        f" | {_fmt(s.get('p_reverse'), '.1%')}"
                        f" | {_fmt(s.get('reversal_depth_med'), '.2%')}"
                        f" | {_fmt(s.get('reversal_depth_p25'), '.2%')}"
                        f" | {_fmt(s.get('reversal_depth_p75'), '.2%')} |"
                    )
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
    atomic_write_text(report_path, content)

    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ev_path = evidence_dir / f"tday_fade_backtest_{report_date}.md"
        atomic_write_text(ev_path, content)

    return report_path
