"""指數 symbol 探測(一次性,收工必 Disconnect):加權/櫃買在 TC4 symbol 樹的代碼.

背景:股票類 QUERYALLINSTRUMENT 無有效 Type(2026-07-21 實測),symbol 存在性只能靠
「訂閱後有無推播」判定;盤後 fresh subscribe 會回當日收盤 snapshot(分鐘級延遲)。
對照組 = TC.S.TWS.2330 與 TC.F.TWF.TXF.HOT(已知存在):對照組有推播而候選沒有
→ 候選不存在;對照組也沒有 → 本次觀察窗無效(TC4 離線或無 snapshot 重送)。

用法:.venv\\Scripts\\python spikes\\index_symbol_probe.py [--port 50774] [--listen-secs 20]
stdout 最後一行 = JSON 摘要。
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
OUT_DIR = Path(__file__).resolve().parent / "out"

CONTROLS = ["TC.S.TWS.2330", "TC.F.TWF.TXF.HOT"]
CANDIDATES = [
    # 加權指數候選
    "TC.S.TWS.TSE",
    "TC.S.TWS.TSE001",
    "TC.S.TWS.IX0001",
    "TC.S.TWS.t00",
    "TC.S.TWS.0000",
    "TC.S.TWS.TWII",
    # 櫃買指數候選
    "TC.S.TWS.OTC",
    "TC.S.TWS.OTC101",
    "TC.S.TWS.IX0043",
    "TC.S.TWS.o00",
    # 其他段猜測
    "TC.S.TSE.TSE",
    "TC.I.TWS.TSE",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="50774")
    ap.add_argument("--listen-secs", type=int, default=20)
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    api = QuoteAPI(APPID, SKEY)
    try:
        q = api.Connect(args.port)
        if q.get("Success") != "OK":
            print(json.dumps({"ok": False, "fail": "connect", "detail": q}, ensure_ascii=False))
            return 1
        session = q["SessionKey"]
        sub_port = q["SubPort"]
        api.socket.setsockopt(zmq.RCVTIMEO, 60_000)

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

        listener_ctx = zmq.Context()
        sock = listener_ctx.socket(zmq.SUB)
        sock.connect(f"tcp://127.0.0.1:{sub_port}")
        sock.setsockopt_string(zmq.SUBSCRIBE, "")
        sock.setsockopt(zmq.RCVTIMEO, 1_000)

        all_syms = CONTROLS + CANDIDATES
        sub_resp: dict[str, str] = {}
        for sym in all_syms:
            rt_request("UNSUBQUOTE", sym)
            r = rt_request("SUBQUOTE", sym)
            sub_resp[sym] = str(r.get("Success"))

        pushed: dict[str, dict] = {}
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
            sym = quote.get("Symbol", "?")
            if sym not in pushed:
                pushed[sym] = {
                    "SecurityName": quote.get("SecurityName"),
                    "TradingPrice": quote.get("TradingPrice"),
                    "ReferencePrice": quote.get("ReferencePrice"),
                    "keys": sorted(quote.keys()),
                }
        for sym in all_syms:
            rt_request("UNSUBQUOTE", sym)
        sock.close(linger=0)
        listener_ctx.term()

        controls_pushed = [s for s in CONTROLS if s in pushed]
        candidates_pushed = [s for s in CANDIDATES if s in pushed]
        summary = {
            "ok": bool(controls_pushed),
            "window_valid": bool(controls_pushed),
            "sub_resp": sub_resp,
            "controls_pushed": controls_pushed,
            "candidates_pushed": candidates_pushed,
            "pushed_detail": pushed,
        }
        (OUT_DIR / "index_symbol_probe.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["ok"] else 1
    finally:
        api.Disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
