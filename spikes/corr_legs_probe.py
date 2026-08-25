"""相關係數加腿前置探測(一次性,收工必 Disconnect):feat/chart-ux-batch-0826 F4 第一步。

沿 `nk225_leg_probe.py` 四步:catalog dump(CFE / CME 段 + 全樹掃 TWD)→ QUERYINSTRUMENTINFO
存在性 oracle → REALTIME 全天窗推播計數(對照組 CME MES)→ 1K 當日窗回補。候選:
VIX(CFE VX / VXM)、原油(CME CL / MCL)、黃金(CME GC / MGC)。台幣匯率沒有任何候選 symbol
(TC4 現貨段只有 TWS;CME 匯率期貨無 TWD 腿)→ 只做全樹掃描證明「找不到」。2330 現貨已由
tc4-market-facts 驗證(`TC.S.TWS.2330`),不重探(夜間也沒推播)。

候選全不在 prod 訂閱清單(configs/correlation.json)→ 不需停 prod;腳本開頭仍核對一次。
TCPY wrapper 在 worktree 缺檔時走 `TCPY_DIR` env(gitignored 產物,ops-discipline worktree 三險)。

用法:.venv/Scripts/python spikes/corr_legs_probe.py [--port 50774] [--listen-secs 45] [--out <path>]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import os  # noqa: E402

_TCPY = ROOT / "TCPY"
if not _TCPY.exists() and os.environ.get("TCPY_DIR"):
    _TCPY = Path(os.environ["TCPY_DIR"])
sys.path.insert(0, str(_TCPY))
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
CANDIDATES = [
    "TC.F.CFE.VX.HOT",
    "TC.F.CFE.VXM.HOT",
    "TC.F.CME.CL.HOT",
    "TC.F.CME.MCL.HOT",
    "TC.F.CME.GC.HOT",
    "TC.F.CME.MGC.HOT",
]
NEGATIVE = "TC.F.CFE.NOPE_XX.HOT"
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
    ap.add_argument("--out", default=str(OUT_DIR / "corr_legs_probe.json"))
    ap.add_argument(
        "--force", action="store_true", help="prod :8721 在跑時仍要探測(會搶走 prod 小日經推播)"
    )
    args = ap.parse_args()

    # 候選若已是 prod 腿,探測的 UNSUB 會把 prod 的 refcount 一起帶走(tc4-market-facts)
    cfg_path = ROOT.parent / "configs" / "correlation.json"
    prod_syms: set[str] = set()
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        prod_syms = {str(leg.get("symbol")) for leg in cfg.get("legs", [])}
    overlap = sorted(set(CANDIDATES + [CONTROL]) & prod_syms)
    if overlap and not args.force and _port_in_use(8721):
        print(json.dumps({"ok": False, "fail": f"候選已是 prod 腿:{overlap};停 prod 或加 --force"}, ensure_ascii=False))
        return 2

    OUT_DIR.mkdir(exist_ok=True)
    out: dict = {
        "probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_now": time.strftime("%H:%M:%S", time.gmtime()),
    }

    api = QuoteAPI(APPID, SKEY)
    # 收工序資源(review F-07):全部在 finally 收,中途拋錯也不留殭屍 session / 訂閱
    session: str | None = None
    sock = None
    listener_ctx = None
    subscribed: list[str] = []
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
        (OUT_DIR / "catalog_Fut_2026-08-26.json").write_text(
            json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        exchanges: dict[str, dict] = {}
        walk_exchanges(cat, exchanges)
        # 2026-06-30 基線快照是 gitignored 產物(worktree 缺檔):缺就只報「無基線」,不擋探測
        base_path = ROOT / "catalog_dump" / "catalog_Fut.json"
        old_exchanges: dict[str, dict] = {}
        if base_path.exists():
            walk_exchanges(json.loads(base_path.read_text(encoding="utf-8")), old_exchanges)
        all_ids = {k: v.get("instrument_ids", []) for k, v in exchanges.items()}
        twd_hits = {
            k: [i for i in ids if "TWD" in i.upper() or i.upper().startswith("TW")]
            for k, ids in all_ids.items()
        }
        out["catalog"] = {
            "exchange_ids_now": sorted(exchanges),
            "exchange_ids_2026_06_30": sorted(old_exchanges),
            "added": sorted(set(exchanges) - set(old_exchanges)),
            "removed": sorted(set(old_exchanges) - set(exchanges)),
            "cfe_instrument_ids": all_ids.get("CFE", []),
            "cme_has": {
                k: k in all_ids.get("CME", []) for k in ("CL", "MCL", "GC", "MGC", "6E", "6J")
            },
            "twd_hits": {k: v for k, v in twd_hits.items() if v},
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
            subscribed.append(sym)
        counts: dict[str, int] = {s: 0 for s in syms}
        trade_counts: dict[str, int] = {s: 0 for s in syms}
        sample: dict[str, dict] = {}
        t0 = time.time()
        while time.time() - t0 < args.listen_secs:
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.Again:
                continue  # RCVTIMEO 到期才續等;ETERM / ENOTSOCK 等其餘錯誤照拋(review F-13)
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
        # 收工序 = UNSUB 全部 → 關 listener → LOGOUT → Disconnect,各自 best-effort(review F-07;
        # 沿 copycat/data/backfill_tc4.py 同款):沒送 LOGOUT 的 session 60 s 後被 reap,reap 時它獨持的
        # key 歸零 → 上游退訂整個 symbol,連 prod 同 symbol 的活 key 一起斷(tc4-market-facts (b)(c))。
        if session is not None:
            for sym in subscribed:
                try:
                    req(api, {"Request": "UNSUBQUOTE", "SessionKey": session, "Param": {
                        "Symbol": sym, "SubDataType": "REALTIME",
                        "StartTime": f"{time.strftime('%Y%m%d', time.gmtime())}00",
                        "EndTime": f"{time.strftime('%Y%m%d', time.gmtime())}23",
                    }})
                except (zmq.ZMQError, OSError, ValueError) as exc:
                    print("UNSUB 失敗(略過):", sym, exc)
        if sock is not None:
            sock.close(linger=0)
        if listener_ctx is not None:
            listener_ctx.term()
        if session is not None:
            try:
                api.Logout(session)
            except (zmq.ZMQError, OSError, ValueError) as exc:
                print("LOGOUT 失敗(略過):", exc)
        api.Disconnect()
        print("disconnected")

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "ok": out.get("realtime", {}).get("push_counts", {}).get(CONTROL, 0) > 0,
        "oracle": {k: v["exists"] for k, v in out.get("oracle", {}).items()},
        "twd_hits": out.get("catalog", {}).get("twd_hits"),
        "push_counts": out.get("realtime", {}).get("push_counts"),
        "trade_counts": out.get("realtime", {}).get("trade_counts"),
        "out": args.out,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
