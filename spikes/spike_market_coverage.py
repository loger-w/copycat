"""
spike_market_coverage.py
========================

目的:一次性實測 Touchance Python API 對「個股 / 指數 / 權證 / 期權」的真實涵蓋
是 deep-research 報告中所有「🔬 待實測」項目的決定性實驗。

針對 4 個監控需求(個股大單 / 權證大量 / 指數新高 / 個股新高)決定 Touchance 路徑是否可行。

執行方式:
    py spike_market_coverage.py

不用 pipenv shell — 系統 Python 3.13 + pyzmq 已驗證可用。
"""
from __future__ import annotations
import sys
import json
import time
import threading
import re
from pathlib import Path

# 把 TCPY repo 加進 path
TCPY_DIR = Path(__file__).parent / "TCPY"
sys.path.insert(0, str(TCPY_DIR))

import zmq
from tcoreapi_mq import QuoteAPI

# 公開 sample 的 APPID / Key — 如果這組不行,要換成 user 自己的授權 key
APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"
# 從 C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-*.log 抓
# TCPY sample 寫死 51237 是過時的,實際 port 是動態
QUOTE_PORT = "50774"

# tcoreapi_mq.py 註解 = Future / Options / Stock
# quote_sample.py 註解 = Fut / Opt / Fut2
# 兩種都試,看哪個是 canonical
CATALOG_TYPES = ["Future", "Options", "Stock", "Fut", "Opt", "Fut2"]

# 測試 symbol 涵蓋 4 類 × 多種命名格式
TEST_SYMBOLS = [
    "TC.F.TWF.FITX.HOT",  # 台指期(已知 OK)— 基準對照
    "TC.S.TWSE.2330",     # 個股:台積電
    "TC.S.TWSE.0050",     # ETF:0050
    "TC.I.TWSE.001",      # 加權指數 — 格式 A
    "TC.I.TWF.IX0001",    # 加權指數 — 格式 B
    "TC.O.TWF.TXO.HOT",   # TXO 熱門月期權
]

collected_messages: dict[str, dict] = {}
collected_lock = threading.Lock()
stop_event = threading.Event()


def safe_login(api: QuoteAPI, port: str, timeout_ms: int = 3000) -> dict:
    """覆寫 tcoreapi_mq.Connect — 加 socket timeout 避免無限 hang。"""
    api.socket = api.context.socket(zmq.REQ)
    api.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    api.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    api.socket.setsockopt(zmq.LINGER, 0)
    api.socket.connect(f"tcp://127.0.0.1:{port}")
    login_obj = {"Request": "LOGIN", "Param": {"SystemName": api.appid, "ServiceKey": api.ServiceKey}}
    api.socket.send_string(json.dumps(login_obj))
    raw = api.socket.recv()[:-1]
    data = json.loads(raw)
    if data.get("Success") == "OK":
        api.CreatePingPong(data["SessionKey"], data["SubPort"])
    return data


def _p(*args, **kwargs) -> None:
    """強制 flush 的 print。"""
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)


def quote_listener(sub_port: str) -> None:
    socket_sub = zmq.Context().socket(zmq.SUB)
    socket_sub.connect(f"tcp://127.0.0.1:{sub_port}")
    socket_sub.setsockopt_string(zmq.SUBSCRIBE, "")
    socket_sub.RCVTIMEO = 1000
    while not stop_event.is_set():
        try:
            raw = socket_sub.recv()[:-1].decode("utf-8")
        except zmq.error.Again:
            continue
        except Exception as e:
            _p(f"    [listener] recv err: {e}")
            continue
        try:
            m = re.search(":", raw)
            if not m:
                continue
            msg = json.loads(raw[m.span()[1]:])
        except Exception:
            continue
        if msg.get("DataType") != "REALTIME":
            continue
        quote = msg.get("Quote", {})
        sym = quote.get("Symbol", "")
        with collected_lock:
            if sym and sym not in collected_messages:
                collected_messages[sym] = quote


def short(obj, n: int = 280) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " ..."


def main() -> None:
    _p("=" * 76)
    _p(f"Touchance ZMQ spike — quote port {QUOTE_PORT}")
    _p(f"目標:驗證個股 / 指數 / 權證 / 期權的真實 API 涵蓋")
    _p("=" * 76)

    api = QuoteAPI(APPID, SKEY)

    _p(f"\n[1] Login → tcp://127.0.0.1:{QUOTE_PORT}")
    try:
        login = safe_login(api, QUOTE_PORT, timeout_ms=3000)
    except zmq.error.ZMQError as e:
        _p(f"    [FAIL] ZMQ error: {e}")
        _p(f"    可能原因:port {QUOTE_PORT} 沒在 listen")
        return
    except Exception as e:
        _p(f"    [FAIL] {type(e).__name__}: {e}")
        return

    _p(f"    LOGIN reply: {short(login, 500)}")
    if login.get("Success") != "OK":
        _p(f"    [FAIL] login 失敗")
        _p(f"    可能原因:")
        _p(f"      (a) Touchance app 內的「行情服務 / API service」沒啟用")
        _p(f"      (b) sample 的 APPID/ServiceKey 對你的安裝無效,需用自己的授權 key")
        _p(f"      (c) port {QUOTE_PORT} 不對")
        return

    session = login["SessionKey"]
    sub_port = login["SubPort"]
    _p(f"    [OK] SessionKey={session[:16]}..., SubPort={sub_port}")

    # listener
    t = threading.Thread(target=quote_listener, args=(sub_port,), daemon=True)
    t.start()

    # [2] 商品目錄查詢
    _p(f"\n[2] QueryAllInstrumentInfo — 試 6 種 type 字串")
    catalog_results = {}
    for typ in CATALOG_TYPES:
        try:
            r = api.QueryAllInstrumentInfo(session, typ)
            catalog_results[typ] = r
            success = r.get("Success", "?")
            err = r.get("ErrMsg", "")
            _p(f"    type={typ!r:10}: Success={success!r:6} ErrMsg={err!r:20} reply_len={len(json.dumps(r))}")
            _p(f"      top-level keys: {list(r.keys())}")
            for k, v in r.items():
                if isinstance(v, list) and len(v) > 0:
                    _p(f"      {k!r}: list[{len(v)}], sample[0]={short(v[0], 200)}")
                elif isinstance(v, dict):
                    _p(f"      {k!r}: dict keys={list(v.keys())[:8]}")
        except Exception as e:
            _p(f"    type={typ!r:10}: EXCEPTION {type(e).__name__}: {e}")

    # [3] 測訂閱
    _p(f"\n[3] SubQuote test (6 symbols)")
    sub_results = {}
    for sym in TEST_SYMBOLS:
        try:
            api.UnsubQuote(session, sym)
            time.sleep(0.05)
            r = api.SubQuote(session, sym)
            sub_results[sym] = r
            ok = r.get("Success", "?")
            err = r.get("ErrMsg", "")
            sec_name = r.get("Param", {}).get("SecurityName") if isinstance(r.get("Param"), dict) else None
            _p(f"    {sym:28}: Success={ok!r:6} ErrMsg={err!r:30} SecurityName={sec_name!r}")
        except Exception as e:
            _p(f"    {sym:28}: EXCEPTION {type(e).__name__}: {e}")

    _p(f"\n[4] 等 25 秒收 REALTIME push ...")
    for i in range(25):
        time.sleep(1)
        with collected_lock:
            got = len(collected_messages)
        if i % 5 == 4:
            _p(f"    {i + 1}s 已收 {got} symbols 的訊息")
    stop_event.set()
    time.sleep(2)

    # [5] 分析
    _p(f"\n[5] Push 結果分析")
    _p(f"    收到 push: {sorted(collected_messages.keys())}")
    _p()
    for sym in TEST_SYMBOLS:
        if sym not in collected_messages:
            _p(f"    [{sym}] ❌ 無 push 接收 — symbol 不存在 / 訂閱被拒 / 該商品市場關閉")
            continue
        msg = collected_messages[sym]
        keys = sorted(msg.keys())
        _p(f"\n    === [{sym}] ===")
        _p(f"    SecurityName={msg.get('SecurityName')!r}")
        _p(f"    全部欄位 ({len(keys)} 個): {keys}")

        # 一檔買賣 — 樣本已知
        _p(f"    一檔: Bid1={msg.get('Bid1')} BidVol={msg.get('BidVolume')} | Ask1={msg.get('Ask1')} AskVol={msg.get('AskVolume')}")

        # 五檔 — 重點!
        has_bid5 = any(f"Bid{i}" in msg for i in range(2, 6))
        has_ask5 = any(f"Ask{i}" in msg for i in range(2, 6))
        if has_bid5 or has_ask5:
            _p(f"    ✅ 五檔買: Bid1={msg.get('Bid1')} Bid2={msg.get('Bid2')} Bid3={msg.get('Bid3')} Bid4={msg.get('Bid4')} Bid5={msg.get('Bid5')}")
            _p(f"    ✅ 五檔賣: Ask1={msg.get('Ask1')} Ask2={msg.get('Ask2')} Ask3={msg.get('Ask3')} Ask4={msg.get('Ask4')} Ask5={msg.get('Ask5')}")
        else:
            _p(f"    ❌ 無五檔(只有 Bid1/Ask1)")

        # 內外盤 — 可能的欄位名
        inout_keys = ["TickType", "InOutSide", "BidAskFlag", "TradeFlag", "AggressorSide", "Side", "TradeFlag"]
        found_inout = {k: msg[k] for k in inout_keys if k in msg}
        if found_inout:
            _p(f"    ✅ 內外盤候選欄位: {found_inout}")
        else:
            _p(f"    ❌ 沒看到內外盤類欄位")

        # 完整 dump
        _p(f"    完整 JSON:")
        for line in json.dumps(msg, ensure_ascii=False, indent=2).split("\n"):
            _p(f"      {line}")

    # cleanup
    try:
        for sym in TEST_SYMBOLS:
            try:
                api.UnsubQuote(session, sym)
            except Exception:
                pass
        api.Logout(session)
    except Exception:
        pass
    _p(f"\n=" * 38)
    _p("Spike 完成")


if __name__ == "__main__":
    main()
