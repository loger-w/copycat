"""
spike_catalog.py
================

目的:把 Touchance 商品 catalog 抓下來,直接看裡面到底有哪些商品類別、有沒有
台股個股 / ETF / 權證 / 加權指數 / 子指數。

這直接決定 deep-research 報告裡的「待實測」項目。

執行方式:
    python -u spike_catalog.py

輸出:
    catalog_<type>.json — 每個成功 type 的完整 catalog dump
    catalog_summary.txt — 人讀的摘要
"""

from __future__ import annotations
import sys
import io
import json
import time
import threading
import re
from pathlib import Path

# Windows console 用 utf-8 避免 emoji crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

TCPY_DIR = Path(__file__).parent / "TCPY"
sys.path.insert(0, str(TCPY_DIR))

import zmq
from tcoreapi_mq import QuoteAPI

APPID = "ZMQ"
SKEY = "8076c9867a372d2a9a814ae710c256e2"
QUOTE_PORT = "50774"

# 試所有可能的商品類別字串 — 從 sample 註解收集 + 常見命名
CATALOG_TYPES = [
    # 已驗證有效
    "Fut",
    "Opt",
    "Fut2",
    # tcoreapi_mq.py 註解 / history_sample.py 註解
    "Future",
    "Options",
    "Stock",
    "Sto",
    # 大膽猜測 — index / warrant / etf 是否有獨立類
    "Idx",
    "Index",
    "I",
    "Wrt",
    "Warrant",
    "W",
    "ETF",
    "Etf",
    "Stk",
    "STK",
    "Securities",
    "Sec",
]


def safe_login(api: QuoteAPI, port: str, timeout_ms: int = 3000) -> dict:
    api.socket = api.context.socket(zmq.REQ)
    api.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    api.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    api.socket.setsockopt(zmq.LINGER, 0)
    api.socket.connect(f"tcp://127.0.0.1:{port}")
    obj = {
        "Request": "LOGIN",
        "Param": {"SystemName": api.appid, "ServiceKey": api.ServiceKey},
    }
    api.socket.send_string(json.dumps(obj))
    raw = api.socket.recv()[:-1]
    return json.loads(raw)


def walk_node(node: dict, path: list[str], leaves: list[dict]) -> None:
    """遞迴展開 Touchance catalog 樹,收集 leaf 商品。"""
    if not isinstance(node, dict):
        return
    name = node.get("CHT") or node.get("ENG") or node.get("CHS") or "?"
    new_path = path + [name]
    children = node.get("Node")
    if isinstance(children, list) and children:
        for c in children:
            walk_node(c, new_path, leaves)
    else:
        # leaf
        leaves.append({"path": " / ".join(new_path), "node": node})


def analyze_catalog(typ: str, reply: dict, out_dir: Path) -> dict:
    """分析 catalog 結構,印摘要,把完整 dump 寫檔。"""
    if reply.get("Success") != "OK":
        return {"type": typ, "status": "fail", "err": reply.get("ErrMsg")}

    instruments = reply.get("Instruments", {})

    # dump 完整 reply 給後續分析
    out_file = out_dir / f"catalog_{typ}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(reply, f, ensure_ascii=False, indent=2)

    # walk 樹找 leaf
    leaves: list[dict] = []
    if isinstance(instruments, dict):
        walk_node(instruments, [], leaves)

    # 找關鍵字
    keyword_hits = {
        "台積": [],
        "2330": [],
        "0050": [],
        "ETF": [],
        "權證": [],
        "warrant": [],
        "加權": [],
        "TAIEX": [],
        "電子": [],
        "金融": [],
        "TSE": [],
        "TWSE": [],
        "TWF": [],
        "TPEx": [],
        "OTC": [],
    }
    for leaf in leaves:
        path = leaf["path"]
        node = leaf["node"]
        text = path + " " + json.dumps(node, ensure_ascii=False)
        for kw in keyword_hits:
            if kw.lower() in text.lower() and len(keyword_hits[kw]) < 3:
                keyword_hits[kw].append(leaf)

    # 找頂層子節點 — 看到底分類成什麼
    top_children = []
    if isinstance(instruments, dict):
        children = instruments.get("Node", [])
        if isinstance(children, list):
            for c in children[:30]:
                top_children.append(
                    {
                        "CHT": c.get("CHT"),
                        "ENG": c.get("ENG"),
                        "EXGID": c.get("EXGID"),
                        "child_count": len(c.get("Node", []))
                        if isinstance(c.get("Node"), list)
                        else 0,
                    }
                )

    return {
        "type": typ,
        "status": "ok",
        "leaf_count": len(leaves),
        "out_file": str(out_file),
        "top_children_preview": top_children,
        "keyword_hits": {k: v for k, v in keyword_hits.items() if v},
    }


def main() -> None:
    print("=" * 76, flush=True)
    print(f"Touchance catalog spike — port {QUOTE_PORT}", flush=True)
    print("=" * 76, flush=True)

    out_dir = Path(__file__).parent / "catalog_dump"
    out_dir.mkdir(exist_ok=True)
    print(f"Dump dir: {out_dir}", flush=True)

    api = QuoteAPI(APPID, SKEY)
    print(f"\n[1] Login...", flush=True)
    login = safe_login(api, QUOTE_PORT, timeout_ms=3000)
    print(f"    LOGIN: {json.dumps(login, ensure_ascii=False)[:300]}", flush=True)
    if login.get("Success") != "OK":
        print("[FAIL] login", flush=True)
        return
    session = login["SessionKey"]
    print(f"    [OK] SessionKey={session[:16]}...", flush=True)

    print(f"\n[2] 試 {len(CATALOG_TYPES)} 種 type:", flush=True)
    results = {}
    for typ in CATALOG_TYPES:
        try:
            r = api.QueryAllInstrumentInfo(session, typ)
            ok = r.get("Success", "?")
            err = r.get("ErrMsg", "")
            if ok == "OK":
                analysis = analyze_catalog(typ, r, out_dir)
                results[typ] = analysis
                print(
                    f"    [OK]   type={typ!r:12} leaves={analysis['leaf_count']:5} dump={analysis['out_file']}",
                    flush=True,
                )
            else:
                results[typ] = {"type": typ, "status": "fail", "err": err}
                print(f"    [FAIL] type={typ!r:12} ErrMsg={err!r}", flush=True)
        except Exception as e:
            print(f"    [EXC]  type={typ!r:12} {type(e).__name__}: {e}", flush=True)

    print(f"\n[3] 每個成功 type 的摘要", flush=True)
    summary_lines = []
    for typ, info in results.items():
        if info.get("status") != "ok":
            continue
        print(f"\n  ====== {typ} ({info['leaf_count']} leaves) ======", flush=True)
        print(f"  頂層子節點 (前 30):", flush=True)
        for c in info["top_children_preview"]:
            print(f"    {c}", flush=True)
        if info["keyword_hits"]:
            print(f"  關鍵字命中:", flush=True)
            for kw, hits in info["keyword_hits"].items():
                print(f"    '{kw}' = {len(hits)} 筆,範例:", flush=True)
                for h in hits[:2]:
                    print(f"      path: {h['path']}", flush=True)
                    print(
                        f"      node: {json.dumps(h['node'], ensure_ascii=False)[:300]}",
                        flush=True,
                    )
        summary_lines.append(
            {"type": typ, **{k: v for k, v in info.items() if k != "out_file"}}
        )

    # 寫摘要
    summary_path = out_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary_lines, f, ensure_ascii=False, indent=2)
    print(f"\n[4] 摘要寫入 {summary_path}", flush=True)
    print("\n=== Catalog spike 完成 ===", flush=True)


if __name__ == "__main__":
    main()
