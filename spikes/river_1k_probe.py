"""六腿江波圖 Phase 0 probe:海外/台期交各段的 **1K 當日回補支援度**。

為什麼不直接 probe 六腿本體:六腿(TXF/TWN/YM/ES/NQ/SXF)在 :8721 的 server 內已被
`futures_engine` / `corr_engine` 訂閱 REALTIME。從另一個 process 對同 symbol 發請求會
**多掛一把 TC4 refcount key**,而上游 feed 以 symbol 為單位 —— probe 收工退訂時整個 symbol
的推播一起斷(見 `.claude/skills/tc4-market-facts/SKILL.md`)→ 會弄壞 user 正在看的畫面。故改 probe **同段但沒被訂閱的兄弟商品**(存在性以 catalog_dump 確認):

| 段 | probe symbol | 對應六腿 |
|---|---|---|
| CME | `TC.F.CME.MES.HOT`(微型小標普) | ES / NQ |
| CBOT | `TC.F.CBOT.MYM.HOT`(微型道瓊;存在性未確認) | YM |
| SGX | `TC.F.SGX.MTWN.HOT`(小富台) | TWN |
| TWF | `TC.F.TWF.UDF.HOT`(台期交道瓊) | TXF / SXF |

每檔問四件事:QUERYINSTRUMENTINFO(存在性 oracle)、1K 當日窗、1K 近 3 日窗、DK(對照)。

用法:`.venv\\Scripts\\python spikes\\river_1k_probe.py [--port 50774] [--out <path>]`
收工必呼叫 Disconnect(),否則 KeepAlive 執行緒讓 process 不退出(docs/research/
2026-07-06-tc4-stock-tick-1k-api-report.md §11)。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "TCPY"))

import zmq  # noqa: E402
from tcoreapi_mq import QuoteAPI  # noqa: E402  # type: ignore[import-untyped]

APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"

SYMBOLS = [
    "TC.F.CME.MES.HOT",
    "TC.F.CBOT.MYM.HOT",
    "TC.F.SGX.MTWN.HOT",
    "TC.F.TWF.UDF.HOT",
]

_REQ_TIMEOUT_MS = 10_000


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


def probe_history(
    api: object, session: str, symbol: str, data_type: str, start: str, end: str, poll_secs: float
) -> dict:
    """SubHistory → 輪詢首頁 → 回 row 數與首末列(不做完整分頁收割,只判支援度)。"""
    t0 = time.monotonic()
    sub = req(
        api,
        {
            "Request": "SUBQUOTE",
            "SessionKey": session,
            "Param": {
                "Symbol": symbol,
                "SubDataType": data_type,
                "StartTime": start,
                "EndTime": end,
            },
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
                    "SubDataType": data_type,
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
    return {
        "sub_success": sub.get("Success"),
        "rows_first_page": len(rows),
        "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
        "elapsed_secs": round(time.monotonic() - t0, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="50774")
    ap.add_argument("--poll-secs", type=float, default=8.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    today = time.strftime("%Y%m%d", time.gmtime())
    day3 = time.strftime("%Y%m%d", time.gmtime(time.time() - 3 * 86400))
    out: dict = {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "utc_today": today, "results": {}}

    api = QuoteAPI(APPID, SKEY)
    api.context.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
    api.context.setsockopt(zmq.SNDTIMEO, _REQ_TIMEOUT_MS)
    api.context.setsockopt(zmq.LINGER, 0)
    try:
        q = api.Connect(args.port)
        if q.get("Success") != "OK":
            print(f"login failed: {q}")
            return 1
        session = q["SessionKey"]
        print(f"connected session={session[:8]}")
        for symbol in SYMBOLS:
            info = req(
                api,
                {
                    "Request": "QUERYINSTRUMENTINFO",
                    "SessionKey": session,
                    "Symbol": symbol,
                },
            )
            exists = "_parse_failed" not in info and info.get("Success") == "OK"
            entry: dict = {"exists": exists, "info_keys": sorted(info)[:8]}
            if exists:
                entry["1k_today"] = probe_history(
                    api, session, symbol, "1K", f"{today}00", f"{today}23", args.poll_secs
                )
                entry["1k_3days"] = probe_history(
                    api, session, symbol, "1K", f"{day3}00", f"{today}23", args.poll_secs
                )
                entry["dk"] = probe_history(
                    api, session, symbol, "DK", f"{day3}00", f"{today}23", args.poll_secs
                )
            out["results"][symbol] = entry
            print(f"{symbol}: {json.dumps(entry, ensure_ascii=False)}")
    finally:
        api.Disconnect()
        print("disconnected")

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
