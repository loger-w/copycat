# -*- coding: utf-8 -*-
"""#272 我的委託 / 成交:build_viewer_cdp.py 的補丁(CRLF 原樣保留;每個錨點必須恰好命中一次)。"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SRC = Path(r"C:\Users\USER\Documents\copycat-trading-review\scripts\week0909\build_viewer_cdp.py")
txt = SRC.read_text(encoding="utf-8", newline="")

EDITS = [
    # 1. docstring
    ('讀 data/ticks、data/daily_groups.json、data/cdp_events.csv、data/cdp_trades.csv、fills;輸出 ../../viewer-cdp.html。"""',
     '讀 data/ticks、data/daily_groups.json、data/cdp_events.csv、data/cdp_trades.csv、fills、群益審計 jsonl;輸出 ../../viewer-cdp.html。"""'),
    # 2. 群組股的 day dict 加 mo=[](我的委託;o 已被開盤價佔用)
    ('cdp=cdp, e=evs, f=[], s=[], t=defaultdict(list), op=e["open_pos"]',
     'cdp=cdp, e=evs, f=[], mo=[], s=[], t=defaultdict(list), op=e["open_pos"]'),
    # 3. 非群組(簿重播)的 day dict 加 mo=[]
    ('cdp=cdp, e=[], f=[], s=[], t=defaultdict(list), op=op',
     'cdp=cdp, e=[], f=[], mo=[], s=[], t=defaultdict(list), op=op'),
]

ORDERS_BLOCK = r'''# 我的委託(#272):群益審計 jsonl 的 order / cancel。送出時刻只到秒;result 為 null(送出前那一列)、被安全閘擋下
# (blocked)、送單失敗(ok=false)都不算掛出去的單。結束時刻:成交 = 上面那份成交清單配對到的那一筆(同日同檔同買賣
# 同價、時刻在送單之後、在刪單送出之前,每筆成交只配一次);沒配到成交而有刪單 = 刪單送出時刻;兩者都沒有且當日成交
# 已補 = 到收盤沒成交也沒刪單;當日成交還沒補 = 未知(頁面標「?」,不假裝它掛到收盤)。頁面只渲染,不做任何配對。
AUDIT_DIR = Path(r"C:\side-project\copycat\data\audit")
fill_pool = defaultdict(list)  # (日, 代號, 買賣, 價) -> 成交秒(由早到晚);配過的移除,同價多筆各配各的
for fl in fills:
    fill_pool[(fl["d"], fl["code"], 1 if "買進" in fl["kind"] else -1, round(fl["px"], 4))].append(tsec(fl["t"]))
for v in fill_pool.values():
    v.sort()
fill_days = {fl["d"] for fl in fills}
orders_n = 0
for p in sorted(AUDIT_DIR.glob("capital-*.jsonl")):
    d = f"{p.stem[-8:-4]}-{p.stem[-4:-2]}-{p.stem[-2:]}"
    if d not in DATES:
        continue
    sent, cancel_at = [], {}
    for line in open(p, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        res = r["result"]
        if res is None or r["blocked"] or not res.get("ok"):
            continue
        sec = tsec(r["ts"][11:19])
        if r["action"] == "order":
            sent.append((sec, r["req"], res["seq_no"]))
        elif r["action"] == "cancel":
            cancel_at.setdefault(r["req"]["seq_no"], sec)  # 要刪的單在 req;刪單 result 的 seq_no 是訊息回音,不是委託序號
    for sec, req, seq in sorted(sent, key=lambda x: x[0]):
        code = req["stock_no"]
        if code not in day or d not in day[code]:
            continue
        side = 1 if req["buy_sell"] == "buy" else -1
        cancel = cancel_at.get(seq)
        pool = fill_pool[(d, code, side, round(req["price"], 4))]
        hit = next((x for x in pool if x >= sec - 1 and (cancel is None or x < cancel)), None)
        if hit is not None:
            pool.remove(hit)
            end, kind = hit, "成交"
        elif cancel is not None:
            end, kind = cancel, "刪單"
        else:
            end, kind = None, ("到收盤" if d in fill_days else "未知")
        day[code][d]["mo"].append([sec, end, req["price"], req["qty"], side, kind, req["price_type"]])
        orders_n += 1
'''

ANCHOR_AFTER_FILLS = "# prod signals + 政策\r\n"
PRINT_OLD = 'print("codes", len(payload["codes"]), "extras", len(extras_in), "code-days", sum(len(v) for v in day.values()),'
PRINT_NEW = 'print("codes", len(payload["codes"]), "extras", len(extras_in), "code-days", sum(len(v) for v in day.values()), "orders", orders_n,'


def sub(text, old, new):
    n = text.count(old)
    assert n == 1, f"錨點命中 {n} 次(要 1):{old[:60]!r}"
    return text.replace(old, new)


for old, new in EDITS:
    txt = sub(txt, old, new)
txt = sub(txt, ANCHOR_AFTER_FILLS, ORDERS_BLOCK.replace("\n", "\r\n") + ANCHOR_AFTER_FILLS)
txt = sub(txt, PRINT_OLD, PRINT_NEW)
SRC.write_text(txt, encoding="utf-8", newline="")
b = SRC.read_bytes()
print("build_viewer_cdp.py 已補丁; CRLF", b.count(b"\r\n"), "LF", b.count(b"\n"))
