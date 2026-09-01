"""DK 凍結快照 probe(fix/dk-frozen-snapshot Phase 1 紅迴圈)。

假說(handoff 2026-09-01):同 session 同窗口的 DK SubHistory 重查回「訂閱建立時點」凍結
快照;逃逸 = 窗口 variant(未驗)。

三臂設計(全部用自己的 session、非 prod 窗口 —— prod TXF DK 窗 start = today-1825d/today-180d,
本 probe 用 today-30d 起,天然不同 key):

  W  = 同一窗口,t0 查一次、等 GAP 秒後再查 —— 預期凍結(兩次逐字節同)。
  V  = 窗口 variant(start 再 -i 日),每次全新 key —— 預期取到前進值。
  U  = 對 W 窗 UNSUBQUOTE 後同窗重 SubHistory —— 額外情報:UNSUB 是否也是逃逸維度。

判定以「末根 bar(今晚夜盤 09-02 bar,若存在)或倒數第二根」的 Volume/Close 是否前進。
窗 end 用 today+1(0902)23:prod 15:16 沒看到 09-02 bar 可能是窗 end=0901 排除所致,順帶驗。

收工紀律:UNSUBQUOTE 所有 history key + LOGOUT + Disconnect(tc4-market-facts)。
用法:.venv\\Scripts\\python dk_frozen_probe.py [--gap-secs 150] [--out <path>]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat\spikes\TCPY")

import zmq  # noqa: E402
from tcoreapi_mq import QuoteAPI  # noqa: E402  # type: ignore[import-untyped]

APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"
SYMBOL = "TC.F.TWF.TXF.HOT"
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


def hist_param(win: tuple[str, str], qry_index: str | None = None) -> dict:
    p: dict = {
        "Symbol": SYMBOL,
        "SubDataType": "DK",
        "StartTime": win[0],
        "EndTime": win[1],
    }
    if qry_index is not None:
        p["QryIndex"] = qry_index
    return p


def query_dk(api: object, session: str, win: tuple[str, str], label: str) -> dict:
    """SubHistory → 首頁 poll(prod _collect_history 同型,退避簡化)→ 只取首頁。

    DK 30 日窗一定塞得進單頁(50 列上限、需 ~23 根),不做分頁收割。
    """
    t0 = time.monotonic()
    sub = req(
        api,
        {"Request": "SUBQUOTE", "SessionKey": session, "Param": hist_param(win)},
    )
    rows: list[dict] = []
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        res = req(
            api,
            {"Request": "GETHISDATA", "SessionKey": session, "Param": hist_param(win, "0")},
            strip_prefix=True,
        )
        rows = res.get("HisData") or []
        if rows:
            break
        time.sleep(0.3)
    tail = rows[-3:]
    rec = {
        "label": label,
        "at": time.strftime("%H:%M:%S"),
        "win": list(win),
        "sub_success": sub.get("Success"),
        "rows": len(rows),
        "tail": tail,
        "elapsed": round(time.monotonic() - t0, 3),
    }
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    return rec


def unsub(api: object, session: str, win: tuple[str, str]) -> dict:
    r = req(
        api,
        {"Request": "UNSUBQUOTE", "SessionKey": session, "Param": hist_param(win)},
    )
    print(f"UNSUB {win}: {r.get('Success')}", flush=True)
    return r


def key_fields(row: dict) -> dict:
    return {k: row.get(k) for k in ("Date", "Time", "Open", "High", "Low", "Close", "Volume")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="50774")
    ap.add_argument("--gap-secs", type=float, default=150.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    today = dt.date.today()
    end = f"{today + dt.timedelta(days=1):%Y%m%d}23"
    win_w = (f"{today - dt.timedelta(days=30):%Y%m%d}00", end)
    win_v1 = (f"{today - dt.timedelta(days=31):%Y%m%d}00", end)
    win_v2 = (f"{today - dt.timedelta(days=32):%Y%m%d}00", end)

    out: dict = {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "records": []}
    api = QuoteAPI(APPID, SKEY)
    api.context.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
    api.context.setsockopt(zmq.SNDTIMEO, _REQ_TIMEOUT_MS)
    api.context.setsockopt(zmq.LINGER, 0)
    opened: list[tuple[str, str]] = []
    try:
        q = api.Connect(args.port)
        if q.get("Success") != "OK":
            print(f"login failed: {q}")
            return 1
        session = q["SessionKey"]
        print(f"connected session={session[:8]}", flush=True)

        w1 = query_dk(api, session, win_w, "W1(t0 同窗首查)")
        opened.append(win_w)
        out["records"].append(w1)

        print(f"sleep {args.gap_secs}s 等行情前進 …", flush=True)
        time.sleep(args.gap_secs)

        w2 = query_dk(api, session, win_w, "W2(同窗重查)")
        v1 = query_dk(api, session, win_v1, "V1(窗口 variant 首查)")
        opened.append(win_v1)
        out["records"] += [w2, v1]

        # U 臂:UNSUB W 窗後同窗重 SubHistory —— UNSUB 是否也是逃逸
        unsub(api, session, win_w)
        opened.remove(win_w)
        u1 = query_dk(api, session, win_w, "U1(UNSUB 後同窗重查)")
        opened.append(win_w)
        out["records"].append(u1)

        # 判定
        w1t, w2t = w1["tail"], w2["tail"]
        v1t, u1t = v1["tail"], u1["tail"]
        frozen = w1t == w2t
        v_diff = [key_fields(r) for r in v1t] != [key_fields(r) for r in w2t]
        u_diff = [key_fields(r) for r in u1t] != [key_fields(r) for r in w2t]
        out["verdict"] = {
            "W_frozen(同窗兩查逐字節同)": frozen,
            "V_escapes(variant 取到不同值)": v_diff,
            "U_escapes(UNSUB 後取到不同值)": u_diff,
            "note": "frozen=True 且 v_diff=True → 紅迴圈成立 + variant 逃逸驗證通過;"
            "v_diff=False 先看行情有沒有動(V1 末根 vs W1 末根)",
        }
        print(json.dumps(out["verdict"], ensure_ascii=False, indent=1), flush=True)

        # 補一輪:若行情沒動(V1==W1),再等一輪 gap 重比
        if frozen and not v_diff:
            print("行情可能沒動,再等一輪 …", flush=True)
            time.sleep(args.gap_secs)
            w3 = query_dk(api, session, win_w, "W3(同窗三查)")
            v2 = query_dk(api, session, win_v2, "V2(第二把 variant)")
            opened.append(win_v2)
            out["records"] += [w3, v2]
            out["verdict"]["round2_W_frozen"] = w3["tail"] == w1t
            out["verdict"]["round2_V_diff"] = [key_fields(r) for r in v2["tail"]] != [
                key_fields(r) for r in w3["tail"]
            ]
            print(json.dumps(out["verdict"], ensure_ascii=False, indent=1), flush=True)
    finally:
        try:
            for win in opened:
                unsub(api, session, win)
            r = req(api, {"Request": "LOGOUT", "SessionKey": session})
            print(f"LOGOUT: {r.get('Success')}", flush=True)
        except Exception as exc:  # 收工 best-effort,Disconnect 必走
            print(f"cleanup error: {exc}", flush=True)
        api.Disconnect()
        print("disconnected", flush=True)

    if args.out:
        Path(args.out).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
