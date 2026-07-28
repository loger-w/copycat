"""QUERYINSTRUMENTINFO 節點展開:找指數分類節點(一次性)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "TCPY"))

import zmq  # noqa: E402
from tcoreapi_mq import QuoteAPI  # noqa: E402  # type: ignore[import-untyped]

APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"
OUT_DIR = Path(__file__).resolve().parent / "out"

NODES = ["TC.S", "TC.S.TWS", "TC.S.TWS.IX0001", "TC.S2", "ICE.S"]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    api = QuoteAPI(APPID, SKEY)
    try:
        q = api.Connect("50774")
        if q.get("Success") != "OK":
            print(json.dumps({"ok": False, "fail": "connect"}))
            return 1
        session = q["SessionKey"]
        api.socket.setsockopt(zmq.RCVTIMEO, 30_000)
        summary: dict = {}
        for node in NODES:
            try:
                res = api.QueryInstrumentInfo(session, node)
            except zmq.ZMQError:
                summary[node] = "timeout"
                continue
            if not isinstance(res, dict) or res.get("Success") != "OK":
                summary[node] = (
                    str(res.get("ErrMsg", "fail"))[:60] if isinstance(res, dict) else "?"
                )
                continue
            fname = "node_" + node.replace(".", "_") + ".json"
            (OUT_DIR / fname).write_text(
                json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            summary[node] = {
                "keys": sorted(res.keys()),
                "dump": fname,
                "bytes": len(json.dumps(res)),
            }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        api.Disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
