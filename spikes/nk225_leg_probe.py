"""日經腿前置探測(一次性,收工必 Disconnect):R5「相關係數加小日經第七腿」spec 第一步。

四件事:
1. QUERYALLINSTRUMENT Fut 全量 dump → 交易所段清單(ENG)+ OSE HOT 節點內容;對照
   2026-06-30 快照 `spikes/catalog_dump/catalog_Fut.json`,確認 OSE NK225M 仍在、KRX 仍無。
2. QUERYINSTRUMENTINFO 存在性 oracle(SUBQUOTE 對不存在 symbol 也回 OK,tc4-market-facts):
   三候選 + 一個必不存在的負對照。
3. UNSUB→SUB REALTIME(全天窗,同 corr_source.all_day_window)監聽 N 秒推播計數,比較
   OSE NK225 / OSE NK225M / SGX NK 流動性;每檔留一則原始 quote,並實跑
   `parse_stock_realtime` + `minute_end_from_utc_hhmmss`(新交易所段必實跑 parse 層,
   core-flow §1)。對照組 = CME MES。**對 prod 已訂的 symbol 多掛一把 refcount key,
   收工退訂時會把 prod 的 feed 一起帶走**(見 `.claude/skills/tc4-market-facts/SKILL.md`):
   NK225M 自 2026-08-17 起已是 prod 第七腿 → 本腳本 `main()` 開頭檢查 :8721 是否有 server 在跑,
   有就拒跑(`--force` 才放行);其餘候選(NK225 / SGX NK / MES)不在 prod 訂閱清單。
4. 1K 當日窗回補支援度(SubHistory 1K → 首頁 rows)+ `parse_1k_minutes` 實跑。

用法:.venv\\Scripts\\python spikes\\nk225_leg_probe.py [--port 50774] [--listen-secs 60] [--out <path>]
stdout 最後一行 = JSON 摘要;完整結果寫 --out(預設 spikes/out/nk225_leg_probe.json)。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "TCPY"))
sys.path.insert(0, str(ROOT.parent))

import zmq  # noqa: E402
from tcoreapi_mq import QuoteAPI  # noqa: E402  # type: ignore[import-untyped]

from copycat.live.river_models import (  # noqa: E402
    minute_end_from_utc_hhmmss,
    parse_1k_minutes,
)
from copycat.live.stock_models import parse_stock_realtime  # noqa: E402

APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"
OUT_DIR = ROOT / "out"

CONTROL = "TC.F.CME.MES.HOT"
CANDIDATES = ["TC.F.OSE.NK225.HOT", "TC.F.OSE.NK225M.HOT", "TC.F.SGX.NK.HOT"]
NEGATIVE = "TC.F.OSE.NOPE_XX.HOT"
_REQ_TIMEOUT_MS = 15_000


def req(api: object, obj: dict, *, strip_prefix: bool = False) -> dict:
    sock = api.socket  # type: ignore[attr-defined]
    with api.lock:  # type: ignore[attr-defined]
        sock.send_string(json.dumps(obj))
        raw = sock.recv()[:-1].decode("utf-8")
    if strip_prefix:
        idx = raw.find(":")
        if idx >= 0:
            raw = raw[idx + 1 :]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_parse_failed": raw[:200]}


def walk_exchanges(node: object, acc: dict[str, dict]) -> None:
    """遞迴收 EXGID 節點 → {EXGID: {"CHT":..., "instrument_ids": [...]}}。"""
    if isinstance(node, dict):
        exg = node.get("EXGID")
        # root 節點也帶 EXGID="TC4_EXG",不能在此 return,否則整棵樹只剩一個段(首跑實踐)
        if exg and exg != "TC4_EXG":
            ids: list[str] = []
            _collect_ids(node, ids)
            acc[str(exg)] = {
                "CHT": node.get("CHT"),
                "ENG": node.get("ENG"),
                "instrument_ids": sorted(set(ids)),
            }
        for v in node.values():
            walk_exchanges(v, acc)
    elif isinstance(node, list):
        for v in node:
            walk_exchanges(v, acc)


def _collect_ids(node: object, out: list[str]) -> None:
    if isinstance(node, dict):
        ids = node.get("InstrumentID")
        if isinstance(ids, list):
            out.extend(str(x) for x in ids)
        for v in node.values():
            _collect_ids(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_ids(v, out)


def probe_1k(
    api: object, session: str, symbol: str, start: str, end: str, poll_secs: float
) -> dict:
    sub = req(
        api,
        {
            "Request": "SUBQUOTE",
            "SessionKey": session,
            "Param": {"Symbol": symbol, "SubDataType": "1K", "StartTime": start, "EndTime": end},
        },
    )
    deadline = time.monotonic() + poll_secs
    rows: list[dict] = []
    while time.monotonic() < deadline:
        res = req(
            api,
            {
                "Request": "GETHISDATA",
                "SessionKey": session,
                "Param": {
                    "Symbol": symbol,
                    "SubDataType": "1K",
                    "StartTime": start,
                    "EndTime": end,
                    "QryIndex": "0",
                },
            },
            strip_prefix=True,
        )
        rows = res.get("HisData") or []
        if rows:
            break
        time.sleep(0.5)
    parsed = parse_1k_minutes(rows)
    return {
        "sub_success": sub.get("Success"),
        "rows_first_page": len(rows),
        "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
        "parsed_minutes": len(parsed),
        "parsed_first": parsed[0] if parsed else None,
        "parsed_last": parsed[-1] if parsed else None,
    }


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="50774")
    ap.add_argument("--listen-secs", type=int, default=60)
    ap.add_argument("--poll-secs", type=float, default=8.0)
    ap.add_argument("--out", default=str(OUT_DIR / "nk225_leg_probe.json"))
    ap.add_argument(
        "--force", action="store_true", help="prod :8721 在跑時仍要探測(會搶走 prod 小日經推播)"
    )
    args = ap.parse_args()

    if not args.force and _port_in_use(8721):
        print(
            json.dumps(
                {
                    "ok": False,
                    "fail": "prod :8721 在跑;NK225M 是 prod 第七腿,探測會搶走推播。"
                    "停 prod 或加 --force。",
                },
                ensure_ascii=False,
            )
        )
        return 2

    OUT_DIR.mkdir(exist_ok=True)
    out: dict = {
        "probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_now": time.strftime("%H:%M:%S", time.gmtime()),
    }

    api = QuoteAPI(APPID, SKEY)
    api.context.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
    api.context.setsockopt(zmq.SNDTIMEO, _REQ_TIMEOUT_MS)
    api.context.setsockopt(zmq.LINGER, 0)
    try:
        q = api.Connect(args.port)
        if q.get("Success") != "OK":
            print(json.dumps({"ok": False, "fail": "connect", "detail": q}, ensure_ascii=False))
            return 1
        session = q["SessionKey"]
        sub_port = q["SubPort"]

        # ---- 1. 全量 dump ----
        api.socket.setsockopt(zmq.RCVTIMEO, 60_000)
        cat = api.QueryAllInstrumentInfo(session, "Fut")
        api.socket.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
        (OUT_DIR / "catalog_Fut_2026-08-17.json").write_text(
            json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        exchanges: dict[str, dict] = {}
        walk_exchanges(cat, exchanges)
        old = json.loads((ROOT / "catalog_dump" / "catalog_Fut.json").read_text(encoding="utf-8"))
        old_exchanges: dict[str, dict] = {}
        walk_exchanges(old, old_exchanges)
        ose = exchanges.get("OSE", {}).get("instrument_ids", [])
        out["catalog"] = {
            "exchange_ids_now": sorted(exchanges),
            "exchange_ids_2026_06_30": sorted(old_exchanges),
            "added": sorted(set(exchanges) - set(old_exchanges)),
            "removed": sorted(set(old_exchanges) - set(exchanges)),
            "krx_present": any(
                "KRX" in k.upper() or "KOSPI" in json.dumps(v, ensure_ascii=False).upper()
                for k, v in exchanges.items()
            ),
            "ose_instrument_ids": ose,
            "ose_has_nk225m": "NK225M" in ose,
            "sgx_has_nk": "NK" in exchanges.get("SGX", {}).get("instrument_ids", []),
        }
        print("catalog:", json.dumps(out["catalog"], ensure_ascii=False))

        # ---- 2. 存在性 oracle ----
        oracle: dict[str, dict] = {}
        for sym in CANDIDATES + [NEGATIVE, CONTROL]:
            info = req(
                api, {"Request": "QUERYINSTRUMENTINFO", "SessionKey": session, "Symbol": sym}
            )
            oracle[sym] = {
                "exists": "_parse_failed" not in info and info.get("Success") == "OK",
                "keys": sorted(info)[:10],
                "info": info.get("Info") if isinstance(info, dict) else None,
            }
        out["oracle"] = oracle
        print(
            "oracle:", json.dumps({k: v["exists"] for k, v in oracle.items()}, ensure_ascii=False)
        )

        # ---- 3. 推播計數(全天窗)----
        today = time.strftime("%Y%m%d", time.gmtime())
        rt_start, rt_end = f"{today}00", f"{today}23"

        def rt(request: str, sym: str) -> dict:
            return req(
                api,
                {
                    "Request": request,
                    "SessionKey": session,
                    "Param": {
                        "Symbol": sym,
                        "SubDataType": "REALTIME",
                        "StartTime": rt_start,
                        "EndTime": rt_end,
                    },
                },
            )

        listener_ctx = zmq.Context()
        sock = listener_ctx.socket(zmq.SUB)
        sock.connect(f"tcp://127.0.0.1:{sub_port}")
        sock.setsockopt_string(zmq.SUBSCRIBE, "")
        sock.setsockopt(zmq.RCVTIMEO, 1_000)
        syms = [CONTROL] + CANDIDATES
        sub_resp = {}
        for sym in syms:
            rt("UNSUBQUOTE", sym)
            sub_resp[sym] = str(rt("SUBQUOTE", sym).get("Success"))
        counts: dict[str, int] = {s: 0 for s in syms}
        trade_counts: dict[str, int] = {s: 0 for s in syms}
        sample: dict[str, dict] = {}
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
            if msg.get("DataType") != "REALTIME":
                continue
            quote = msg.get("Quote", {})
            sym = str(quote.get("Symbol", "?"))
            if sym not in counts:
                continue
            counts[sym] += 1
            tick, book, _meta = parse_stock_realtime(quote, trial_windows=())
            if tick is not None:
                trade_counts[sym] += 1
            if sym not in sample or (tick is not None and sample[sym].get("tick") is None):
                sample[sym] = {
                    "SecurityName": quote.get("SecurityName"),
                    "TradingPrice": quote.get("TradingPrice"),
                    "TradeQuantity": quote.get("TradeQuantity"),
                    "FilledTime": quote.get("FilledTime"),
                    "PreciseTime": quote.get("PreciseTime"),
                    "TradeDate": quote.get("TradeDate"),
                    "Bid": quote.get("Bid"),
                    "Ask": quote.get("Ask"),
                    "BidVolume": quote.get("BidVolume"),
                    "AskVolume": quote.get("AskVolume"),
                    "ReferencePrice": quote.get("ReferencePrice"),
                    "OpenTime": quote.get("OpenTime"),
                    "CloseTime": quote.get("CloseTime"),
                    "keys": sorted(quote.keys()),
                    "tick": None
                    if tick is None
                    else {"price_milli": tick.price_milli, "qty": tick.qty, "time": tick.time},
                    "book_bids": book.bids[:2],
                    "book_asks": book.asks[:2],
                    "minute_end_from_filledtime": minute_end_from_utc_hhmmss(
                        str(quote.get("FilledTime", ""))
                    ),
                }
        for sym in syms:
            rt("UNSUBQUOTE", sym)
        sock.close(linger=0)
        listener_ctx.term()
        out["realtime"] = {
            "listen_secs": args.listen_secs,
            "sub_resp": sub_resp,
            "push_counts": counts,
            "trade_counts": trade_counts,
            "samples": sample,
        }
        print("push_counts:", json.dumps(counts), "trade_counts:", json.dumps(trade_counts))

        # ---- 4. 1K 當日回補 ----
        out["k1"] = {
            sym: probe_1k(api, session, sym, rt_start, rt_end, args.poll_secs) for sym in CANDIDATES
        }
        print(
            "1k:",
            json.dumps(
                {k: (v["rows_first_page"], v["parsed_minutes"]) for k, v in out["k1"].items()}
            ),
        )
    finally:
        api.Disconnect()
        print("disconnected")

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "ok": out.get("catalog", {}).get("ose_has_nk225m", False)
        and out.get("realtime", {}).get("push_counts", {}).get(CONTROL, 0) > 0,
        "krx_present": out.get("catalog", {}).get("krx_present"),
        "push_counts": out.get("realtime", {}).get("push_counts"),
        "trade_counts": out.get("realtime", {}).get("trade_counts"),
        "out": args.out,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
