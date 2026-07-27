"""CLI 入口:import-neigui / replay / validate / compare 逐 task 接上."""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

from copycat.data.import_neigui import run_import

logger = logging.getLogger(__name__)

_DEFAULT_EVENTS_CSV = Path("docs/evidence/five_tigers_events_2025-06-30_2026-06-26.csv")


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console cp950
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # stderr 與 stdout 同編碼
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="copycat")
    sub = parser.add_subparsers(dest="command", required=True)

    p_imp = sub.add_parser("import-neigui", help="匯入 neigui five-tigers 種子資料")
    p_imp.add_argument("--src", type=Path, required=True)
    p_imp.add_argument("--events-csv", type=Path, default=_DEFAULT_EVENTS_CSV)
    p_imp.add_argument("--data-dir", type=Path, default=Path("data"))

    p_rep = sub.add_parser("replay", help="對事件清單跑評分引擎")
    p_rep.add_argument("--watchlist", type=Path, default=Path("watchlists/four_tigers.json"))
    p_rep.add_argument("--config", type=Path, default=None)
    p_rep.add_argument("--data-dir", type=Path, default=Path("data"))
    p_rep.add_argument("--out", type=Path, default=Path("out"))

    p_val = sub.add_parser("validate", help="replay 彙總 vs evidence golden")
    p_val.add_argument("--run-five", type=Path, default=Path("out/five_tigers"))
    p_val.add_argument("--run-four", type=Path, default=Path("out/four_tigers"))
    p_val.add_argument("--out", type=Path, default=None)

    p_cmp = sub.add_parser("compare", help="兩份 replay run 並排對照")
    p_cmp.add_argument("run_a", type=Path)
    p_cmp.add_argument("run_b", type=Path)
    p_cmp.add_argument("--out", type=Path, default=Path("out/compare.md"))

    p_bf = sub.add_parser("backfill-daily", help="FinMind 日線回補(位階特徵前置)")
    p_bf.add_argument("--data-dir", type=Path, default=Path("data"))
    p_bf.add_argument("--start", default="2024-06-02")
    p_bf.add_argument("--end", default="2025-05-01")

    p_tf = sub.add_parser("tday-features", help="T 日跟多回測:觸發特徵管線")
    p_tf.add_argument("--data-dir", type=Path, default=Path("data"))
    p_tf.add_argument("--out", type=Path, default=Path("out/tday_ga"))
    p_tf.add_argument("--config", type=Path, default=None)
    p_tf.add_argument("--watchlist-core", type=Path, default=Path("watchlists/four_tigers.json"))
    p_tf.add_argument("--watchlist-aux", type=Path, default=Path("watchlists/fubon_9600.json"))

    p_ts = sub.add_parser("tday-search", help="T 日跟多回測:模擬 + 三段式搜索 + 報告")
    p_ts.add_argument("--data-dir", type=Path, default=Path("data"))
    p_ts.add_argument("--out", type=Path, default=Path("out/tday_ga"))
    p_ts.add_argument("--config", type=Path, default=None)
    p_ts.add_argument("--report-date", required=True)
    p_ts.add_argument("--report-dir", type=Path, default=Path("docs/evidence"))

    p_se = sub.add_parser("scan-events", help="自產漲停事件掃描(append events.csv + limitup_all)")
    p_se.add_argument("--data-dir", type=Path, default=Path("data"))
    p_se.add_argument("--start", required=True)
    p_se.add_argument("--end", required=True)

    p_bt = sub.add_parser("backfill-tc4", help="TC4 歷史 1K 回補(缺的 stock-day)")
    p_bt.add_argument("--data-dir", type=Path, default=Path("data"))
    # scan 補全後的全事件池;種子 CSV(_DEFAULT_EVENTS_CSV)只在 import-neigui 用
    p_bt.add_argument("--events-csv", type=Path, default=Path("data/events/events.csv"))
    p_bt.add_argument("--port", default="50774")
    p_bt.add_argument("--batch", type=int, default=0, help="0=全部")

    p_dt = sub.add_parser("backfill-daytrade", help="FinMind 當沖資格 + 處置期間回補")
    p_dt.add_argument("--data-dir", type=Path, default=Path("data"))
    p_dt.add_argument("--start", required=True)
    p_dt.add_argument("--end", required=True)

    p_bb = sub.add_parser("backfill-brokers", help="FinMind 分點日報回補(events T 日,完整聚合)")
    p_bb.add_argument("--data-dir", type=Path, default=Path("data"))
    p_bb.add_argument("--events-csv", type=Path, default=Path("data/events/events.csv"))
    p_bb.add_argument("--limit", type=int, default=None, help="樣本驗證用,只抓前 N 筆")

    p_le = sub.add_parser("label-events", help="events.csv 分點標籤(watchlist ∈ T 日 top-5 淨買超)")
    p_le.add_argument("--data-dir", type=Path, default=Path("data"))
    p_le.add_argument("--events-csv", type=Path, default=Path("data/events/events.csv"))
    p_le.add_argument("--watchlist", type=Path, default=Path("watchlists/five_tigers.json"))
    p_le.add_argument("--verify-existing", action="store_true", help="只比對既有標籤,不寫檔")

    p_fd = sub.add_parser("fade-diagnose", help="三池無條件 fade 複驗(主問題判定式)")
    p_fd.add_argument("--data-dir", type=Path, default=Path("data"))
    p_fd.add_argument("--out", type=Path, default=Path("out/fade_diagnose"))
    p_fd.add_argument("--config", type=Path, default=None)
    p_fd.add_argument("--report-date", required=True)
    p_fd.add_argument("--report-dir", type=Path, default=Path("docs/evidence"))
    p_fd.add_argument("--label-cutoff", required=True, help="標記截止日(共同期間上界)")
    p_fd.add_argument("--watchlist", type=Path, default=Path("watchlists/five_tigers.json"))

    p_fc = sub.add_parser("fade-cells", help="UC 池劇本格子評估(pre-registered,D5 判定)")
    p_fc.add_argument("--data-dir", type=Path, default=Path("data"))
    p_fc.add_argument("--out", type=Path, default=Path("out/fade_cells"))
    p_fc.add_argument("--config", type=Path, default=None)
    p_fc.add_argument("--report-date", required=True)
    p_fc.add_argument("--report-dir", type=Path, default=Path("docs/evidence"))
    p_fc.add_argument("--watchlist", type=Path, default=Path("watchlists/five_tigers.json"))

    p_fa = sub.add_parser("fade-anatomy", help="round 4 §0 前置描述統計(設計輸入,不入判定)")
    p_fa.add_argument("--data-dir", type=Path, default=Path("data"))
    p_fa.add_argument("--out", type=Path, default=Path("out/fade_anatomy"))
    p_fa.add_argument("--config", type=Path, default=None)
    p_fa.add_argument("--report-date", required=True)
    p_fa.add_argument("--report-dir", type=Path, default=Path("docs/evidence"))
    p_fa.add_argument("--watchlist", type=Path, default=Path("watchlists/five_tigers.json"))

    p_fe = sub.add_parser(
        "fade-entry-anatomy", help="round 5 §0 進場訊號解剖(流向反轉/位階對決,不入判定)"
    )
    p_fe.add_argument("--data-dir", type=Path, default=Path("data"))
    p_fe.add_argument("--out", type=Path, default=Path("out/fade_entry_anatomy"))
    p_fe.add_argument("--config", type=Path, default=None)
    p_fe.add_argument("--report-date", required=True)
    p_fe.add_argument("--report-dir", type=Path, default=Path("docs/evidence"))
    p_fe.add_argument("--watchlist", type=Path, default=Path("watchlists/five_tigers.json"))

    p_fs = sub.add_parser("fade-search", help="T+1 fade 回測:GA 搜索 + 報告")
    p_fs.add_argument("--data-dir", type=Path, default=Path("data"))
    p_fs.add_argument("--out", type=Path, default=Path("out/fade_ga"))
    p_fs.add_argument("--config", type=Path, default=None)
    p_fs.add_argument("--report-date", required=True)
    p_fs.add_argument("--report-dir", type=Path, default=Path("docs/evidence"))

    sub.add_parser("refresh-stkfut-map", help="重抓期交所股票期貨對映(期現對照用)")

    p_nt = sub.add_parser("notify-test", help="Discord webhook 實發測試")
    p_nt.add_argument("--message", default="copycat notify-test")
    p_nt.add_argument("--title", default=None)

    args = parser.parse_args(argv)
    if args.command == "import-neigui":
        manifest = run_import(args.src, args.events_csv, args.data_dir)
        missing_t = manifest["missing_t_1k"]
        missing_t1 = manifest["missing_t1_1k"]
        assert isinstance(missing_t, list) and isinstance(missing_t1, list)
        sys.stdout.write(
            f"匯入完成:1K {manifest['k1_days']} stock-day、"
            f"虎事件 {manifest['tiger_events']}、對照 {manifest['control_events']}、"
            f"缺 T 日 1K {len(missing_t)} 筆、缺 T+1 1K {len(missing_t1)} 筆\n"
        )
        return 0
    if args.command == "replay":
        from copycat.replay.runner import run_replay

        run_dir = run_replay(args.data_dir, args.watchlist, args.out, args.config)
        sys.stdout.write(f"replay 完成 → {run_dir}\n")
        return 0
    if args.command == "validate":
        from copycat.replay.validate import format_validate, run_validate

        checks = run_validate(args.run_five, args.run_four)
        text = format_validate(checks)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        sys.stdout.write(text + "\n")
        return 0 if all(c["ok"] for c in checks) else 1
    if args.command == "compare":
        from copycat.replay.compare import write_compare

        out = write_compare(args.run_a, args.run_b, args.out)
        sys.stdout.write(f"對照表 → {out}\n")
        return 0
    if args.command == "backfill-daily":
        import copycat.data.backfill_finmind as backfill_finmind

        stats = backfill_finmind.run_backfill(
            args.data_dir, args.start, args.end, _resolve_finmind_token()
        )
        sys.stdout.write(
            f"回補完成:fetch {stats['fetched_days']} 日、跳過 {stats['skipped_days']} 日、"
            f"新增 {stats['added_rows']} rows、過濾未知代碼 {stats.get('filtered_rows', 0)} rows\n"
        )
        return 0
    if args.command in ("tday-features", "tday-search"):
        import copycat.backtest.pipeline as pipeline
        from copycat.backtest.config import BacktestConfig, load_backtest_config

        cfg = load_backtest_config(args.config) if args.config else BacktestConfig.default()
        if args.command == "tday-features":
            out_dir = pipeline.run_features(
                args.data_dir, args.out, cfg, args.watchlist_core, args.watchlist_aux
            )
            sys.stdout.write(f"features 完成 → {out_dir}\n")
            return 0
        report = pipeline.run_search(
            args.data_dir, args.out, cfg, args.report_date, report_dir=args.report_dir
        )
        sys.stdout.write(f"回測報告 → {report}\n")
        return 0
    if args.command == "scan-events":
        from copycat.data.scan_events import scan_limitup_events

        stats = scan_limitup_events(args.data_dir, args.start, args.end)
        sys.stdout.write(
            f"掃描完成:events 新增 {stats['events_appended']} 筆、"
            f"limitup_all 新增 {stats['limitup_appended']} 筆、"
            f"t1_date 修復 {stats['t1_fixed']} 筆\n"
        )
        return 0
    if args.command == "backfill-tc4":
        from copycat.data.backfill_tc4 import run_backfill_tc4

        stats = run_backfill_tc4(args.data_dir, args.events_csv, args.port, args.batch)
        sys.stdout.write(
            f"TC4 回補完成:缺 {stats['total_missing']} 筆、"
            f"成功 {stats['fetched']} 筆、失敗 {stats['failed']} 筆\n"
        )
        return 0
    if args.command == "backfill-daytrade":
        from copycat.data.backfill_daytrade import run_backfill_daytrade

        stats = run_backfill_daytrade(args.data_dir, args.start, args.end, _resolve_finmind_token())
        sys.stdout.write(
            f"當沖資格回補完成:fetch {stats['fetched_days']} 日、"
            f"新增 {stats['added_rows']} rows、處置期間 {stats['disposition_rows']} 筆\n"
        )
        return 0
    if args.command == "backfill-brokers":
        from copycat.data.backfill_brokers import run_backfill_brokers

        stats = run_backfill_brokers(
            args.data_dir, args.events_csv, _resolve_finmind_token(), limit=args.limit
        )
        sys.stdout.write(
            f"分點日報回補完成:fetch {stats['fetched']}、跳過 {stats['skipped']}、"
            f"空回應 {stats['empty']}、目標 {stats['targets']} 筆\n"
        )
        return 0
    if args.command == "label-events":
        from copycat.data.label_events import label_events

        stats = label_events(
            args.data_dir, args.events_csv, args.watchlist, verify_existing=args.verify_existing
        )
        if args.verify_existing:
            compared = stats["verified_matched"] + stats["verified_mismatched"]
            rate = stats["verified_matched"] / compared if compared else 0.0
            sys.stdout.write(
                f"標籤一致率 {rate:.2%}({stats['verified_matched']}/{compared};"
                f"無分點檔 {stats['verified_uncovered']} 筆)\n"
            )
            return 0 if rate >= 0.99 else 1
        sys.stdout.write(
            f"標籤完成:命中 {stats['labeled_hit']}、無命中 {stats['labeled_no_hit']}、"
            f"無分點檔 {stats['uncovered']}、既有標籤 {stats['already_labeled']}\n"
        )
        return 0
    if args.command == "fade-diagnose":
        from copycat.backtest.fade_config import FadeBacktestConfig, load_fade_config
        from copycat.backtest.fade_diagnose import run_pool_diagnose

        diag_cfg = load_fade_config(args.config) if args.config else FadeBacktestConfig.default()
        report = run_pool_diagnose(
            args.data_dir,
            args.out,
            diag_cfg,
            args.report_date,
            args.label_cutoff,
            args.watchlist,
            report_dir=args.report_dir,
        )
        sys.stdout.write(f"三池複驗報告 → {report}\n")
        return 0
    if args.command == "fade-cells":
        from copycat.backtest.fade_cells import run_cells
        from copycat.backtest.fade_config import FadeBacktestConfig, load_fade_config

        cells_cfg = load_fade_config(args.config) if args.config else FadeBacktestConfig.default()
        report = run_cells(
            args.data_dir,
            args.out,
            cells_cfg,
            args.report_date,
            args.watchlist,
            report_dir=args.report_dir,
        )
        sys.stdout.write(f"劇本格子報告 → {report}\n")
        return 0
    if args.command == "fade-anatomy":
        from copycat.backtest.fade_anatomy import run_anatomy
        from copycat.backtest.fade_config import FadeBacktestConfig, load_fade_config

        anat_cfg = load_fade_config(args.config) if args.config else FadeBacktestConfig.default()
        report = run_anatomy(
            args.data_dir,
            args.out,
            anat_cfg,
            args.report_date,
            args.watchlist,
            report_dir=args.report_dir,
        )
        sys.stdout.write(f"§0 前置統計報告 → {report}\n")
        return 0
    if args.command == "fade-entry-anatomy":
        from copycat.backtest.fade_config import FadeBacktestConfig, load_fade_config
        from copycat.backtest.fade_entry_anatomy import run_entry_anatomy

        entry_cfg = load_fade_config(args.config) if args.config else FadeBacktestConfig.default()
        report = run_entry_anatomy(
            args.data_dir,
            args.out,
            entry_cfg,
            args.report_date,
            args.watchlist,
            report_dir=args.report_dir,
        )
        sys.stdout.write(f"進場訊號解剖報告 → {report}\n")
        return 0
    if args.command == "fade-search":
        from copycat.backtest.fade_config import FadeBacktestConfig, load_fade_config
        from copycat.backtest.fade_pipeline import run_fade_pipeline

        fade_cfg = load_fade_config(args.config) if args.config else FadeBacktestConfig.default()
        result = run_fade_pipeline(
            args.data_dir, args.out, fade_cfg, args.report_date,
            evidence_dir=args.report_dir,
        )
        sys.stdout.write(f"fade 回測報告 → {result.get('report', args.out)}\n")
        return 0
    if args.command == "notify-test":
        from copycat import notify

        if notify.resolve_webhook_url() is None:
            sys.stderr.write("DISCORD_WEBHOOK_URL 未設定(env 或 repo root .env)\n")
            return 1
        if notify.notify_discord(args.message, title=args.title):
            sys.stdout.write("Discord webhook 發送成功\n")
            return 0
        sys.stderr.write("Discord webhook 發送失敗(詳見 log)\n")
        return 1
    if args.command == "refresh-stkfut-map":
        from copycat.stkfut_map import refresh

        mapping = refresh()
        sys.stdout.write(f"stkfut map 更新完成:{len(mapping)} 檔\n")
        return 0
    return 1


def _resolve_finmind_token() -> str:
    """讀取順序:env → repo root .env → 明確錯誤(design round 1 R12)."""
    import os

    token = os.environ.get("FINMIND_TOKEN")
    if token:
        return token
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "FINMIND_TOKEN" and value.strip():
                return value.strip()
    raise RuntimeError("FINMIND_TOKEN 未設定(env 或 repo root .env)")


if __name__ == "__main__":
    raise SystemExit(main())
