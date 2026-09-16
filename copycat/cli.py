"""CLI 入口:import-neigui / replay / validate / compare 逐 task 接上."""

from __future__ import annotations

import argparse
import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

from copycat.data.import_neigui import run_import
from copycat.tc4common import TC4_DEFAULT_PORT

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
    p_bt.add_argument("--port", default=TC4_DEFAULT_PORT)
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

    sub.add_parser("refresh-stkfut-map", help="重抓期交所股票期貨對映(期現對照用)")

    sub.add_parser("refresh-stock-names", help="重抓 TWSE ISIN 全市場股票名稱表(搜尋提示用)")

    p_nt = sub.add_parser("notify-test", help="Discord webhook 實發測試")
    p_nt.add_argument("--message", default="copycat notify-test")
    p_nt.add_argument("--title", default=None)

    p_sc = sub.add_parser("screen", help="盤前選股篩選(#173):印候選名單")
    p_sc.add_argument(
        "--date",
        default=None,
        help="目標交易日 YYYY-MM-DD(名單服務的交易日;EOD 窗自其前一交易日往回、當沖名單抓該日;預設依牆鐘推)",
    )
    p_sc.add_argument(
        "--write",
        action="store_true",
        help="覆寫自選群組「盤前篩選」(直接落檔 —— server 跑著時別用:它讀得到檔,但訂閱池與前端廣播不會跟上,症狀 = 群組出現但整排空卡片)",
    )

    p_cs = sub.add_parser(
        "chain-stats",
        help="回報鏈統計(#234):server log 的乾淨子集(盤中到達 / 單調 / 庫存段 ≥ 500 ms)落地 p50/p90/p99 + 1019 次數",
    )
    p_cs.add_argument("--log", type=Path, nargs="+", required=True, help="logs/server-*.log,可多檔(依序合併)")

    p_tc = sub.add_parser(
        "ticks-compact",
        help="tick 存檔轉檔(spec #257):當日 jsonl → 成交 / 簿兩個 parquet(去重、壞行計數、列數核對才刪 jsonl);server 13:45 以子程序呼叫,排程失敗可手動重跑",
    )
    p_tc.add_argument("--date", required=True, help="交易日 YYYYMMDD(非交易日 / jsonl 不存在 → exit 2)")
    p_tc.add_argument(
        "--dir", type=Path, default=None, help="tick 存檔目錄(預設 configs/ticks.json 的 dir,相對 repo root)"
    )

    p_br = sub.add_parser(
        "book-replay",
        help="簿重播外掛檔(#267):某交易日 tick 存檔 → 每檔一個 keyframe+delta 外掛檔(回看頁重播分頁懶載入);逐檔解回原樣才落檔",
    )
    p_br.add_argument(
        "--date",
        required=True,
        help="交易日 YYYYMMDD(只收已轉檔的日子:成交 + 簿兩個 parquet 都在,否則 exit 2)",
    )
    p_br.add_argument(
        "--dir", type=Path, default=None, help="tick 存檔目錄(預設 configs/ticks.json 的 dir,相對 repo root)"
    )
    p_br.add_argument(
        "--out",
        type=Path,
        default=Path("out/book_replay"),
        help="輸出根目錄,檔案落在 <out>/<YYYY-MM-DD>/<代號>.js(實際使用指向回看頁的外掛資料夾)",
    )

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
    if args.command == "chain-stats":
        from copycat.capital.chain_stats import format_report, summarize

        def _lines() -> Iterator[str]:
            for path in args.log:
                with path.open(encoding="utf-8", errors="replace") as fh:
                    yield from fh

        sys.stdout.write(format_report(summarize(_lines())))
        return 0
    if args.command == "screen":
        import asyncio
        import datetime as _dt

        from copycat.screening import data_date_of, expected_target_date
        from copycat.server import breadth_fetch
        from copycat.server.screen_engine import SCREEN_GROUP, ScreenEngine
        from copycat.stock_watchlist import (
            DEFAULT_PATH,
            WatchlistError,
            fit_group_codes,
            load_watchlist,
            save_watchlist,
            with_group_replaced,
        )
        from copycat.trading_calendar import load_trading_calendar

        cal = load_trading_calendar()
        target = (
            _dt.date.fromisoformat(args.date)
            if args.date
            else expected_target_date(_dt.datetime.now(), cal)
        )
        if not cal.is_trading_day(target):
            # pr-211 F-07:`data_date_of` 的前置是 target 為交易日(prod 唯一來源 expected_target_date
            # 恆滿足);--date 給週末 / 假日會算出與下一交易日相同的資料窗、當沖 fetch 回空,
            # 錯誤訊息會把「你給的日子不是交易日」講成「FinMind 未更新?」—— 在取數前明講。
            sys.stderr.write(
                f"盤前篩選:{target} 是非交易日,--date 須為目標交易日(名單服務的交易日)\n"
            )
            return 2
        engine = ScreenEngine(
            token=_resolve_finmind_token(),
            calendar=cal,
            daily_fetch=breadth_fetch.fetch_daily_prices,
            day_trading_fetch=breadth_fetch.fetch_day_trading,
            disposition_fetch=breadth_fetch.fetch_disposition,
        )
        final = asyncio.run(engine.compute(target))
        sys.stdout.write(f"盤前篩選 {target}(資料日 {data_date_of(target, cal)}):{len(final)} 檔\n")
        sys.stdout.write(f"{'代號':<6}{'還原20日%':>9}{'均量(張)':>10}{'鎖板次':>5}  最近鎖板\n")
        for c in final:
            sys.stdout.write(
                f"{c.code:<6}{c.ret_pct:>9.1f}{c.avg_lots:>10.0f}"
                f"{len(c.lock_dates):>5}  {c.lock_dates[0]}\n"
            )
        if args.write:
            wl = load_watchlist(DEFAULT_PATH)
            # 截位與 server 引擎同一份語意(review F5)—— 不截的話超限直接 WATCHLIST_FULL
            # 整次寫入失敗,兩條路徑對同一份名單一個成一個敗
            fitted, dropped = fit_group_codes(wl, SCREEN_GROUP, [c.code for c in final])
            if dropped:
                sys.stderr.write(f"超出自選上限,截掉排序尾段 {dropped} 檔\n")
            try:
                saved = save_watchlist(DEFAULT_PATH, with_group_replaced(wl, SCREEN_GROUP, fitted))
            except WatchlistError as e:
                sys.stderr.write(f"寫入自選失敗:{e}\n")
                return 1
            sys.stdout.write(f"已覆寫群組「{SCREEN_GROUP}」(自選共 {len(saved['codes'])} 檔)\n")
        return 0
    if args.command == "ticks-compact":
        import datetime as _dt

        from copycat.ticks_compact import (
            CompactFailed,
            CompactRefused,
            compact_day,
            format_compact_line,
        )
        from copycat.ticks_config import load_ticks_config, resolve_ticks_dir
        from copycat.trading_calendar import load_trading_calendar

        try:
            day = _dt.datetime.strptime(args.date, "%Y%m%d").date()
        except ValueError:
            sys.stderr.write(f"tick 轉檔:--date 須為 YYYYMMDD(收到 {args.date!r})\n")
            return 2
        # 目錄解析與寫入端同一份(相對 repo root),不另抄一次規則
        data_dir = args.dir if args.dir is not None else resolve_ticks_dir(load_ticks_config())
        try:
            result = compact_day(day, data_dir, is_trading_day=load_trading_calendar().is_trading_day)
        except CompactRefused as e:
            sys.stderr.write(f"tick 轉檔 {day}:{e}\n")
            return 2
        except CompactFailed as e:
            sys.stderr.write(f"tick 轉檔 {day} 失敗:{e}\n")
            return 1
        except OSError as e:
            # 讀 jsonl / 寫 parquet 的 IO 失敗(權限 / 磁碟):人話一行 exit 1,不吐 traceback(pr-263 F-03)
            sys.stderr.write(f"tick 轉檔 {day} 失敗(IO):{e}\n")
            return 1
        sys.stdout.write(format_compact_line(day, result) + "\n")
        return 0
    if args.command == "book-replay":
        return _book_replay(args.date, args.dir, args.out)
    if args.command == "refresh-stkfut-map":
        from copycat.stkfut_map import refresh

        mapping = refresh()
        sys.stdout.write(f"stkfut map 更新完成:{len(mapping)} 檔\n")
        return 0
    if args.command == "refresh-stock-names":
        from copycat.stock_names import refresh as refresh_names

        names = refresh_names()
        sys.stdout.write(f"股票名稱表更新完成:{len(names)} 檔\n")
        return 0
    return 1


def _book_replay(date_arg: str, dir_arg: Path | None, out_root: Path) -> int:
    """`book-replay` 薄殼:讀一天 tick 存檔 → 簿重播引擎 → 每檔編碼、解回自檢、落檔。"""
    import datetime as _dt
    import time

    from copycat import book_replay
    from copycat.fileio import atomic_write_text
    from copycat.ticks import book_parquet_path, jsonl_path, load_day, parquet_path
    from copycat.ticks_config import load_ticks_config, resolve_ticks_dir

    try:
        day = _dt.datetime.strptime(date_arg, "%Y%m%d").date()
    except ValueError:
        sys.stderr.write(f"簿重播:--date 須為 YYYYMMDD(收到 {date_arg!r})\n")
        return 2
    date = day.isoformat()
    data_dir = dir_arg if dir_arg is not None else resolve_ticks_dir(load_ticks_config())
    # 只重播已轉檔的日子(成交 + 簿兩個 parquet 都在),外掛檔永久保留、殘缺版會蓋掉完整版:
    # 盤中 jsonl 還在寫、成交還沒以 (代號, 累積量) 去重;簿 parquet 只留 120 交易日,過期只剩成交列
    if not parquet_path(data_dir, date).exists():
        if jsonl_path(data_dir, date).exists():
            sys.stderr.write(f"簿重播 {date}:tick 存檔還沒轉檔(13:45 排程或手動 ticks-compact 之後再跑)\n")
        else:
            sys.stderr.write(f"簿重播 {date}:{data_dir} 沒有這天的 tick 存檔\n")
        return 2
    if not book_parquet_path(data_dir, date).exists():
        sys.stderr.write(
            f"簿重播 {date}:只有成交 parquet、簿 parquet 不在(過了保留期?),拒絕產出以免蓋掉既有外掛檔\n"
        )
        return 2
    started = time.monotonic()
    out_dir = out_root / date
    messages = anomalous_trades = total_bytes = 0
    try:
        # 先建輸出目錄:--out 寫不進去,不必等讀完整天(約 30 秒)才知道(pr-275 review F-06)
        out_dir.mkdir(parents=True, exist_ok=True)
        # 讀檔的權限 / 磁碟錯同樣印一行人話;壞 parquet 是 pyarrow 的 ValueError,這裡不接、照舊大聲失敗
        code_days = book_replay.replay_books(load_day(day, data_dir))
        codes = sorted(code_days)
        for code in codes:
            code_day = code_days.pop(code)
            text = book_replay.plugin_js(book_replay.encode(code_day))
            if book_replay.decode(book_replay.parse_plugin_js(text)) != code_day:
                sys.stderr.write(f"簿重播 {date} {code}:自檢失敗,外掛檔解不回原樣,未落檔\n")
                return 1
            atomic_write_text(out_dir / f"{code}.js", text)
            messages += len(code_day.frames)
            anomalous_trades += code_day.anomalous_trades
            total_bytes += len(text)
    except book_replay.PluginFormatError as e:
        sys.stderr.write(f"簿重播 {date}:自檢失敗,{e}\n")
        return 1
    except OSError as e:
        sys.stderr.write(f"簿重播 {date} 失敗(IO):{e}\n")
        return 1
    sys.stdout.write(
        f"簿重播 {date}:{len(codes)} 檔、{messages} 則(達錢時刻異常、不當標籤時刻的成交 {anomalous_trades} 則),"
        f"外掛檔 {total_bytes / 1_000_000:.1f} MB,耗時 {time.monotonic() - started:.1f} 秒 → {out_dir}\n"
    )
    return 0


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
