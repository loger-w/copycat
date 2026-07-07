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
            f"新增 {stats['added_rows']} rows\n"
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
        report = pipeline.run_search(args.data_dir, args.out, cfg, args.report_date)
        sys.stdout.write(f"回測報告 → {report}\n")
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
