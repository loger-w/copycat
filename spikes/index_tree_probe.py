"""指數 symbol 樹探測:QUERYALLINSTRUMENT 各 Type 名試打,dump 找櫃買指數(一次性)."""

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

TYPE_CANDIDATES = ["Index", "IDX", "Idx", "Ind", "Spot", "Stock", "Stk", "Sec", "Equity", "S"]


def walk_strings(node: object, acc: list[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            walk_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            walk_strings(v, acc)
    elif isinstance(node, str):
        acc.append(node)


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
        summary: dict = {"types": {}}
        for tname in TYPE_CANDIDATES:
            try:
                res = api.QueryAllInstrumentInfo(session, tname)
            except zmq.ZMQError:
                summary["types"][tname] = "timeout"
                continue
            ok = res.get("Success") == "OK" if isinstance(res, dict) else False
            summary["types"][tname] = "OK" if ok else str(res.get("ErrMsg", "fail"))[:60]
            if ok:
                (OUT_DIR / f"tree_{tname}.json").write_text(
                    json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                strings: list[str] = []
                walk_strings(res, strings)
                syms = sorted({s for s in strings if s.startswith("TC.")})
                summary["types"][tname] = {"symbols": len(syms), "sample": syms[:20]}
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        api.Disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
