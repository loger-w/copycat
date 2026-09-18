# -*- coding: utf-8 -*-
"""#272 two-axis review round-1 收修(CRLF 原樣保留;每個錨點必須恰好命中一次)。

Spec 軸:C1 成交回報早於審計 ts(全集 9 筆)→ 委託整天不顯示;C2 委託結束與成交顯示兩把時間尺;
C3「到收盤」是沒根據的斷言;C4 開關關掉後跳成交按鈕還能按;A2 `mo` 不帶委託序號,同價同秒兩筆分不開。
Standards 軸:S-03 有沒有標記算兩次;S-04 上 / 下一筆兩份實作;S-05 `mkt` 名實不符;S-06 `at` 名字說不出用途;
S-07 浮點價當配對鍵;S-08 `sec - 1` 沒寫 why。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BUILD = Path(r"C:\Users\USER\Documents\copycat-trading-review\scripts\week0909\build_viewer_cdp.py")
TPL = Path(r"C:\Users\USER\Documents\copycat-trading-review\scripts\week0909\viewer_cdp_template.html")


def sub(text, old, new, what):
    n = text.count(old)
    assert n == 1, f"{what}:錨點命中 {n} 次(要 1):{old[:70]!r}"
    return text.replace(old, new)


# ---------------------------------------------------------------- build 腳本
b = BUILD.read_text(encoding="utf-8", newline="")

OLD_HEAD = """# 已補 = 到收盤沒成交也沒刪單;當日成交還沒補 = 未知(頁面標「?」,不假裝它掛到收盤)。頁面只渲染,不做任何配對。
AUDIT_DIR = Path(r"C:\\side-project\\copycat\\data\\audit")
fill_pool = defaultdict(list)  # (日, 代號, 買賣, 價) -> 成交秒(由早到晚);配過的移除,同價多筆各配各的
for fl in fills:
    fill_pool[(fl["d"], fl["code"], 1 if "買進" in fl["kind"] else -1, round(fl["px"], 4))].append(tsec(fl["t"]))
for v in fill_pool.values():
    v.sort()
fill_days = {fl["d"] for fl in fills}
orders_n = 0
"""
NEW_HEAD = """# 已補 = 沒配到(頁面寫明可能掛到收盤、也可能成交清單漏了);當日成交還沒補 = 未知(頁面標「?」)。頁面只渲染不配對。
AUDIT_DIR = Path(r"C:\\side-project\\copycat\\data\\audit")
# 價用毫元整數當鍵(同 market.py 的理由:兩個來源的小數表示不同時,浮點等值比較會靜默配不到);
# 成交秒與頁面上「你的成交」同樣先 round(.,1),兩邊才是同一把尺 —— 否則會出現最多 50 ms「委已消失、成還沒出現」的空窗。
fill_pool = defaultdict(list)  # (日, 代號, 買賣, 毫元價) -> 成交秒(由早到晚);配過的移除,同價多筆各配各的
for fl in fills:
    fill_pool[(fl["d"], fl["code"], 1 if "買進" in fl["kind"] else -1, round(fl["px"] * 1000))].append(round(tsec(fl["t"]), 1))
for v in fill_pool.values():
    v.sort()
fill_days = {fl["d"] for fl in fills}
orders_n = clamped_n = 0
"""
b = sub(b, OLD_HEAD.replace("\n", "\r\n"), NEW_HEAD.replace("\n", "\r\n"), "build head")

OLD_MATCH = """        side = 1 if req["buy_sell"] == "buy" else -1
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
"""
NEW_MATCH = """        side = 1 if req["buy_sell"] == "buy" else -1
        cancel = cancel_at.get(seq)
        pool = fill_pool[(d, code, side, round(req["price"] * 1000))]
        # 審計 ts 是「送單回來之後」才蓋的、又只到秒,所以它系統性地比真正送出去的時刻晚一點;
        # 配對窗因此自 sec − 1 起算。配到之後把送出時刻收斂成「不晚於成交」(單子不可能晚於它自己的成交才送出) ——
        # 不收斂就會出現結束早於送出的列(全集 9 筆,差 0.08–0.95 秒),那種列頁面條件恆不成立 = 整天不顯示、零訊號。
        hit = next((x for x in pool if x >= sec - 1 and (cancel is None or x < cancel)), None)
        if hit is not None:
            pool.remove(hit)
            end, kind = hit, "成交"
            if hit < sec:
                sec, clamped_n = hit, clamped_n + 1
        elif cancel is not None:
            end, kind = cancel, "刪單"
        else:
            end, kind = None, ("未配到" if d in fill_days else "未知")
        day[code][d]["mo"].append([sec, end, req["price"], req["qty"], side, kind, req["price_type"], seq])
        orders_n += 1
"""
b = sub(b, OLD_MATCH.replace("\n", "\r\n"), NEW_MATCH.replace("\n", "\r\n"), "build match")
b = sub(b, '"orders", orders_n,', '"orders", orders_n, "orders-clamped", clamped_n,', "build print")
BUILD.write_text(b, encoding="utf-8", newline="")

# ---------------------------------------------------------------- 模板
t = TPL.read_text(encoding="utf-8", newline="")

EDITS = [
    # S-05 `mkt` 名實:PriceType 只有 limit / market,非限價就是市價;把值域寫在現場 + A2 帶委託序號
    (
        "    const ord = mo.filter(o => o[6] === \"limit\").map(o => ({t0: Math.round(o[0]*1000), t1: o[1] == null ? null : Math.round(o[1]*1000), px: Math.round(o[2]*1000), qty: o[3], side: o[4], kind: o[5]}));",
        "    // 只有限價單停得在某一格;非限價 = 市價(群益 PriceType 只有 limit / market),另外計數由說明列交代,不畫。\n"
        "    const ord = mo.filter(o => o[6] === \"limit\").map(o => ({t0: Math.round(o[0]*1000), t1: o[1] == null ? null : Math.round(o[1]*1000), px: Math.round(o[2]*1000), qty: o[3], side: o[4], kind: o[5], seq: o[7]}));",
    ),
    # S-06 `at` → `bucket`;A2 tooltip 帶委託序號;C3「未配到」不作斷言
    (
        "      const at = (side, px) => { const m = side > 0 ? meBuy : meSell; let v = m.get(px); if(!v){ v = {oq:0, on:0, unk:0, fq:0, fn:0, tip:[]}; m.set(px, v); } return v; };\n"
        "      RP.my.ord.forEach(o => { if(o.t0 > now || (o.t1 != null && o.t1 <= now)) return;\n"
        "        const v = at(o.side, o.px); v.oq += o.qty; v.on++; if(o.kind === \"未知\") v.unk++;\n"
        "        v.tip.push(`委託 ${fmtT(o.t0/1000)} ${o.side > 0 ? \"買\" : \"賣\"} ${rpPx(o.px)} × ${o.qty} 張 → ${o.t1 == null ? (o.kind === \"未知\" ? \"當日成交資料還沒補,不知道它何時消失\" : \"到收盤沒成交也沒刪單\") : o.kind + \" \" + fmtT(o.t1/1000)}`); });\n"
        "      RP.my.fill.forEach(f => { if(f.t > now) return;\n"
        "        const v = at(f.side, f.px); v.fq += f.qty; v.fn++;\n",
        "      const bucket = (side, px) => { const m = side > 0 ? meBuy : meSell; let v = m.get(px); if(!v){ v = {oq:0, on:0, unk:0, fq:0, fn:0, tip:[]}; m.set(px, v); } return v; };\n"
        "      const endTxt = o => o.t1 != null ? o.kind + \" \" + fmtT(o.t1/1000)\n"
        "        : o.kind === \"未知\" ? \"當日成交資料還沒補,不知道它何時消失\"\n"
        "        : \"沒配到成交也沒刪單(可能掛到收盤,也可能當日成交清單漏了這筆)\";\n"
        "      RP.my.ord.forEach(o => { if(o.t0 > now || (o.t1 != null && o.t1 <= now)) return;\n"
        "        const v = bucket(o.side, o.px); v.oq += o.qty; v.on++; if(o.kind === \"未知\") v.unk++;\n"
        "        v.tip.push(`委託 ${fmtT(o.t0/1000)} ${o.side > 0 ? \"買\" : \"賣\"} ${rpPx(o.px)} × ${o.qty} 張(委託序號 ${o.seq}) → ${endTxt(o)}`); });\n"
        "      RP.my.fill.forEach(f => { if(f.t > now) return;\n"
        "        const v = bucket(f.side, f.px); v.fq += f.qty; v.fn++;\n",
    ),
    # S-03:整列有沒有標記直接用算好的 tag,不再各查一次 Map
    (
        "    const cell = (q, side, p) => { const tag = meTag(p, side);\n"
        "      if(q == null) return `<div class=\"rp-q ${side}\" role=\"cell\">${tag}</div>`;\n",
        "    const cell = (q, side, tag) => {\n"
        "      if(q == null) return `<div class=\"rp-q ${side}\" role=\"cell\">${tag}</div>`;\n",
    ),
    (
        "      const me = meBuy.has(p) || meSell.has(p);\n"
        "      h += `<div class=\"rp-row${p===px?\" cur\":\"\"}${p===G.limUp||p===G.limDn?\" lim\":\"\"}${me?\" me\":\"\"}\" role=\"row\" data-p=\"${p}\">${cell(buy.get(p), \"buy\", p)}<div class=\"rp-p mono ${pcls}\" role=\"cell\"${p===G.limUp?' title=\"漲停\"':p===G.limDn?' title=\"跌停\"':\"\"}>${rpPx(p)}</div>${cell(sell.get(p), \"sell\", p)}</div>`; }",
        "      const tb = meTag(p, \"buy\"), ts = meTag(p, \"sell\");\n"
        "      h += `<div class=\"rp-row${p===px?\" cur\":\"\"}${p===G.limUp||p===G.limDn?\" lim\":\"\"}${tb||ts?\" me\":\"\"}\" role=\"row\" data-p=\"${p}\">${cell(buy.get(p), \"buy\", tb)}<div class=\"rp-p mono ${pcls}\" role=\"cell\"${p===G.limUp?' title=\"漲停\"':p===G.limDn?' title=\"跌停\"':\"\"}>${rpPx(p)}</div>${cell(sell.get(p), \"sell\", ts)}</div>`; }",
    ),
    # S-04:「有沒有上 / 下一筆」一份實作,按鈕停用與跳轉讀同一個答案;C4:開關關掉 = 隱藏,連導航一起停
    (
        "  function rpGoFill(dir){ // 跳到上一筆 / 下一筆我自己的成交(則號 = 收到時刻 ≤ 該成交回報時刻的最後一則)\n"
        "    if(!RP) return; const xs = RP.my.idx, i = RP.i;\n"
        "    let to = null;\n"
        "    if(dir < 0){ for(const k of xs){ if(k >= i) break; to = k; } } else to = xs.find(k => k > i);\n"
        "    if(to != null) rpGo(to);\n"
        "  }\n",
        "  // 上一筆 / 下一筆我自己的成交(則號 = 收到時刻 ≤ 該成交回報時刻的最後一則);null = 這個方向沒有了。\n"
        "  // 按鈕停用與跳轉讀同一個答案,不會出現「按得下去卻跳不動」。關掉「你的委託 / 成交」= 隱藏,連導航一起停。\n"
        "  function rpFillNear(dir){\n"
        "    if(!RP || !state.show.fills) return null;\n"
        "    const xs = RP.my.idx, i = RP.i;\n"
        "    if(dir > 0) return xs.find(k => k > i) ?? null;\n"
        "    let to = null; for(const k of xs){ if(k >= i) break; to = k; } return to;\n"
        "  }\n"
        "  function rpGoFill(dir){ const to = rpFillNear(dir); if(to != null) rpGo(to); }\n",
    ),
    (
        "    el.fprev.disabled = !RP.my.idx.some(k => k < i); el.fnext.disabled = !RP.my.idx.some(k => k > i);",
        "    el.fprev.disabled = rpFillNear(-1) == null; el.fnext.disabled = rpFillNear(1) == null;",
    ),
    # 按鈕 title:停用時說得出為什麼
    (
        '<button type="button" id="rpFPrev" title="上一筆你自己的成交(回報收到時刻)">◀ 上一筆我的成交</button>'
        '<button type="button" id="rpFNext" title="下一筆你自己的成交(回報收到時刻)">下一筆我的成交 ▶</button>',
        '<button type="button" id="rpFPrev" title="上一筆你自己的成交(回報收到時刻;關掉「你的委託 / 成交」時停用)">◀ 上一筆我的成交</button>'
        '<button type="button" id="rpFNext" title="下一筆你自己的成交(回報收到時刻;關掉「你的委託 / 成交」時停用)">下一筆我的成交 ▶</button>',
    ),
    # 定義與規則:補送出時刻系統性偏晚、委託序號、「沒配到」的措辭
    (
        "委託自送出畫到「成交」(配對到你的成交那一筆)或「刪單」(刪單送出時刻),兩者都沒有就畫到收盤。",
        "委託自送出畫到「成交」(配對到你的成交那一筆)或「刪單」(刪單送出時刻)。審計的送出時刻是<b>送單呼叫回來之後才蓋的章</b>,"
        "系統性地比真正送出去晚一點(全部資料裡有 9 筆的成交回報比它還早,差 0.08–0.95 秒;這種單子的送出時刻會收斂成不晚於成交,"
        "因此在畫面上沒有可見的停留時間)。兩者都沒配到時寫「沒配到成交也沒刪單」——<b>可能真的掛到收盤,也可能當日成交清單漏了這筆</b>,分不出來。"
        "同一格同一秒掛好幾筆時,滑鼠移上去的每一行都帶<b>委託序號</b>可以分辨。",
    ),
]
for old, new in EDITS:
    t = sub(t, old.replace("\n", "\r\n"), new.replace("\n", "\r\n"), "tpl")
TPL.write_text(t, encoding="utf-8", newline="")

for f in (BUILD, TPL):
    raw = f.read_bytes()
    print(f.name, "CRLF", raw.count(b"\r\n"), "LF", raw.count(b"\n"))
