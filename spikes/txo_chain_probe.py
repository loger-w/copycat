"""SC-1 spike:TXO 期權鏈探測(一次性,收工必 Disconnect)。

驗證:(a) 序列/合約清單可查(最近序列 ≥ 30 檔斷言);(b) 整鏈訂閱成功 + REALTIME 欄位;
(c) 歷史 TICKS 回補可查 + 欄位覆蓋率;(d) 錄檔供 replay golden。
休市日執行時 (b) 降級為「訂閱成功 + snapshot 回傳」(design §9 Known Risk 1)。

用法:.venv\\Scripts\\python spikes\\txo_chain_probe.py [--port 50774] [--date 2026-07-17]
stdout 最後一行 = JSON 摘要;exit 0 = 全部斷言過。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "TCPY"))

import zmq  # noqa: E402
from tcoreapi_mq import QuoteAPI  # noqa: E402  # type: ignore[import-untyped]

APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"
OUT_DIR = Path(__file__).resolve().parent / "out"

OPT_SYMBOL_RE = re.compile(r"TC\.O\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<expiry>[0-9A-Z/]+)")


def walk_strings(node: object, acc: list[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            walk_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            walk_strings(v, acc)
    elif isinstance(node, str):
        acc.append(node)


def poll_history(
    api: QuoteAPI, session: str, sym: str, dtype: str, start: str, end: str, wait_rounds: int = 10
) -> list[dict]:
    api.SubHistory(session, sym, dtype, start, end)
    for _ in range(wait_rounds):
        time.sleep(1)
        his = api.GetHistory(session, sym, dtype, start, end, "0")
        if his and his.get("HisData"):
            break
    else:
        return []
    rows: list[dict] = []
    qry_index = "0"
    while True:
        his = api.GetHistory(session, sym, dtype, start, end, qry_index)
        page = his.get("HisData", [])
        if not page:
            break
        rows.extend(page)
        nxt = page[-1].get("QryIndex", "")
        if not nxt or nxt == qry_index:
            break
        qry_index = nxt
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="50774")
    ap.add_argument("--date", default="2026-07-17")
    ap.add_argument("--atm-halfwidth", type=int, default=15, help="回補鏈 ATM ± N 檔")
    ap.add_argument("--listen-secs", type=int, default=8)
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    summary: dict = {"steps": {}}
    api = QuoteAPI(APPID, SKEY)
    try:
        # ---- 1. 登入 ----
        q = api.Connect(args.port)
        summary["steps"]["connect"] = q.get("Success")
        if q.get("Success") != "OK":
            print(json.dumps({"ok": False, "fail": "connect", "detail": q}))
            return 1
        session = q["SessionKey"]
        sub_port = q["SubPort"]
        api.socket.setsockopt(zmq.RCVTIMEO, 60_000)

        # ---- 2. 期權合約清單 ----
        instruments = None
        for type_name in ("Options", "Opt"):
            try:
                res = api.QueryAllInstrumentInfo(session, type_name)
            except zmq.ZMQError:
                res = None
            if res and res.get("Success") == "OK":
                instruments = res
                summary["steps"]["query_all_type"] = type_name
                break
        if instruments is None:
            print(json.dumps({"ok": False, "fail": "query_all_instrument"}))
            return 1
        (OUT_DIR / "txo_instruments.json").write_text(
            json.dumps(instruments, ensure_ascii=False, indent=1), encoding="utf-8"
        )

        strings: list[str] = []
        walk_strings(instruments, strings)
        opt_syms = sorted({s for s in strings if s.startswith("TC.O.TWF.")})
        summary["steps"]["twf_option_symbols"] = len(opt_syms)

        # 解析:TC.O.TWF.<prod>.<expiry>[.<cp>.<strike>] — 實際層級由 dump 決定,先寬鬆分組
        series: dict[str, list[str]] = {}
        for s in opt_syms:
            m = OPT_SYMBOL_RE.match(s)
            if not m:
                continue
            series.setdefault(f"{m.group('prod')}.{m.group('expiry')}", []).append(s)
        summary["series_found"] = {k: len(v) for k, v in sorted(series.items())[:40]}

        # 履約價層可能不在全清單裡(只有 root/HOT),此時逐序列 QueryInstrumentInfo 展開
        if not series:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "fail": "no_txo_series_parsed",
                        "hint": "檢查 spikes/out/txo_instruments.json 結構",
                    }
                )
            )
            return 1

        def leaf_count(syms: list[str]) -> int:
            return sum(1 for s in syms if re.search(r"\.[CP]\.\d+$", s))

        # 取葉子(含 .C./.P.)最多且 expiry 最近的序列;prod 含 TXO/TX1-5
        candidates = {
            k: v for k, v in series.items() if re.match(r"TX[O1-5]", k) and leaf_count(v) >= 10
        }
        if not candidates:
            # 全清單可能只有產品層,改抓 TXO root 再 QueryInstrumentInfo 展開
            summary["steps"]["expand_mode"] = "per-product query"
            root_res = api.QueryInstrumentInfo(session, "TC.O.TWF.TXO")
            (OUT_DIR / "txo_product_info.json").write_text(
                json.dumps(root_res, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            strings = []
            walk_strings(root_res, strings)
            opt_syms = sorted({s for s in strings if s.startswith("TC.O.TWF.")})
            for s in opt_syms:
                m = OPT_SYMBOL_RE.match(s)
                if m:
                    series.setdefault(f"{m.group('prod')}.{m.group('expiry')}", []).append(s)
            candidates = {
                k: v for k, v in series.items() if re.match(r"TX[O1-5]", k) and leaf_count(v) >= 10
            }
        if not candidates:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "fail": "no_leaf_contracts",
                        "series_sample": dict(list(summary["series_found"].items())[:10]),
                    }
                )
            )
            return 1

        pick = min(candidates, key=lambda k: re.sub(r"\D", "", k.split(".", 1)[1])[:8] or "9" * 8)
        chain = sorted(s for s in candidates[pick] if re.search(r"\.[CP]\.\d+$", s))
        contracts_count = len(chain)
        summary["picked_series"] = pick
        summary["contracts_count"] = contracts_count

        # ---- 3. 歷史 TICKS 回補(ATM ± N)----
        ymd = args.date.replace("-", "")
        start, end = f"{ymd}00", f"{ymd}06"

        strikes = sorted({int(s.rsplit(".", 1)[1]) for s in chain})
        mid = strikes[len(strikes) // 2]
        lo = max(0, len(strikes) // 2 - args.atm_halfwidth)
        hi = len(strikes) // 2 + args.atm_halfwidth
        picked_strikes = set(strikes[lo:hi])
        sub_chain = [s for s in chain if int(s.rsplit(".", 1)[1]) in picked_strikes]
        summary["backfill_symbols"] = len(sub_chain)
        summary["atm_mid_strike"] = mid

        field_counter: Counter[str] = Counter()
        rows_total = 0
        sample_row: dict | None = None
        jsonl_path = OUT_DIR / f"txo_ticks_{ymd}.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for i, sym in enumerate(sub_chain):
                rows = poll_history(api, session, sym, "TICKS", start, end, wait_rounds=6)
                rows_total += len(rows)
                for r in rows:
                    for k, v in r.items():
                        if v not in ("", None):
                            field_counter[k] += 1
                    fh.write(json.dumps({"symbol": sym, "row": r}, ensure_ascii=False) + "\n")
                if rows and sample_row is None:
                    sample_row = rows[0]
                if (i + 1) % 10 == 0:
                    print(f"[backfill] {i + 1}/{len(sub_chain)} rows={rows_total}", file=sys.stderr)
        summary["ticks_fetched"] = rows_total
        summary["tick_field_coverage"] = (
            {k: round(v / rows_total, 4) for k, v in sorted(field_counter.items())}
            if rows_total
            else {}
        )
        summary["tick_sample"] = sample_row

        # ---- 4. 整鏈訂閱 + REALTIME 欄位 ----
        listener_ctx = zmq.Context()
        sock = listener_ctx.socket(zmq.SUB)
        sock.connect(f"tcp://127.0.0.1:{sub_port}")
        sock.setsockopt_string(zmq.SUBSCRIBE, "")
        sock.setsockopt(zmq.RCVTIMEO, 1_000)

        # 現版 TC4 的 SUBQUOTE REALTIME 必須帶 StartTime/EndTime,官方 wrapper 未帶
        # → "invalid Date Time Format"(2026-07-18 實測)。以 raw request 帶當日 UTC 窗。
        today_ymd = time.strftime("%Y%m%d", time.gmtime())
        rt_start, rt_end = f"{today_ymd}00", f"{today_ymd}06"

        def rt_request(request: str, sym: str) -> dict:
            obj = {
                "Request": request,
                "SessionKey": session,
                "Param": {
                    "Symbol": sym,
                    "SubDataType": "REALTIME",
                    "StartTime": rt_start,
                    "EndTime": rt_end,
                },
            }
            api.lock.acquire()
            api.socket.send_string(json.dumps(obj))
            message = api.socket.recv()[:-1]
            api.lock.release()
            return json.loads(message)

        sub_ok = 0
        sub_fail_sample: dict | None = None
        for sym in sub_chain + ["TC.F.TWF.FITX.HOT"]:
            rt_request("UNSUBQUOTE", sym)
            r = rt_request("SUBQUOTE", sym)
            if r.get("Success") == "OK":
                sub_ok += 1
            elif sub_fail_sample is None:
                sub_fail_sample = {"symbol": sym, "resp": r}
        summary["subscribe_ok"] = sub_ok
        summary["subscribe_fail_sample"] = sub_fail_sample

        realtime_msgs = 0
        realtime_symbols: set[str] = set()
        realtime_sample: dict | None = None
        t0 = time.time()
        while time.time() - t0 < args.listen_secs:
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                continue
            idx = raw.find(":")
            if idx < 0:
                continue
            try:
                msg = json.loads(raw[idx + 1 :])
            except json.JSONDecodeError:
                continue
            if msg.get("DataType") == "REALTIME":
                realtime_msgs += 1
                quote = msg.get("Quote", {})
                realtime_symbols.add(quote.get("Symbol", "?"))
                if realtime_sample is None:
                    realtime_sample = quote
        for sym in sub_chain + ["TC.F.TWF.FITX.HOT"]:
            rt_request("UNSUBQUOTE", sym)
        sock.close(linger=0)
        listener_ctx.term()

        summary["realtime_msgs"] = realtime_msgs
        summary["realtime_symbols"] = len(realtime_symbols)
        summary["realtime_sample_keys"] = sorted(realtime_sample.keys()) if realtime_sample else []
        summary["realtime_sample"] = realtime_sample

        # ---- 斷言 ----
        checks = {
            "contracts_count_ge_30": contracts_count >= 30,
            "ticks_fetched_gt_0": rows_total > 0,
            "subscribe_all_ok": sub_ok == len(sub_chain) + 1,  # 鏈 + TXF
        }
        summary["checks"] = checks
        ok = all(checks.values())
        print(json.dumps({"ok": ok, **summary}, ensure_ascii=False))
        return 0 if ok else 1
    finally:
        api.Disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
