# -*- coding: utf-8 -*-
"""#272 我的委託 / 成交:viewer_cdp_template.html 的補丁(CRLF 原樣保留;每個錨點必須恰好命中一次)。"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SRC = Path(r"C:\Users\USER\Documents\copycat-trading-review\scripts\week0909\viewer_cdp_template.html")
txt = SRC.read_text(encoding="utf-8", newline="")

EDITS = []

# ---- 1. CSS
EDITS.append((
    ".rp-row.lim .rp-p{text-decoration:underline dotted}",
    ".rp-row.lim .rp-p{text-decoration:underline dotted}\n"
    ".rp-me{position:relative;display:inline-flex;align-items:center;margin:0 3px;padding:0 4px;border-radius:3px;font-size:10px;font-weight:700;line-height:14px;white-space:nowrap}\n"
    ".rp-me.ord{border:1px solid var(--accent);color:var(--accent)}\n"
    ".rp-me.ord.unk{border-style:dashed;opacity:.8}\n"
    ".rp-me.fill.buy{background:var(--up);color:#fff} .rp-me.fill.sell{background:var(--down);color:#fff}\n"
    ".rp-row.me{outline:1px solid var(--accent);outline-offset:-1px}",
))

# ---- 2. 圖例:同一個開關管委託與成交
EDITS.append((
    '[["fills","你的成交","var(--up)"]',
    '[["fills","你的委託 / 成交","var(--up)"]',
))

# ---- 3. rpMy:把「我的委託 / 成交」對齊到重播時間軸(頁面只換算單位,配對在 build_viewer_cdp.py 做完)
EDITS.append((
    "  let RP = null; // 目前掛載的重播",
    "  // 我的委託 / 成交(#272):委託 = 群益審計的下單 / 刪單,結束時刻(刪單 / 成交 / 到收盤 / 未知)由 build_viewer_cdp.py 配好;\n"
    "  // 這裡只把秒換成毫秒、價換成毫元,對齊重播時間軸(審計與 tick 存檔的收到時刻同一台機器的鐘)。市價單不畫在格子上。\n"
    "  function rpMy(R){\n"
    "    const D = DATA.d[R.code] && DATA.d[R.code][R.date], mo = (D && D.mo) || [], fl = (D && D.f) || [];\n"
    "    const ord = mo.filter(o => o[6] === \"limit\").map(o => ({t0: Math.round(o[0]*1000), t1: o[1] == null ? null : Math.round(o[1]*1000), px: Math.round(o[2]*1000), qty: o[3], side: o[4], kind: o[5]}));\n"
    "    const fill = fl.map(f => ({t: Math.round(f[0]*1000), px: Math.round(f[1]*1000), qty: f[2], side: f[3], label: f[4]}));\n"
    "    return {ord, fill, mkt: mo.length - ord.length, idx: [...new Set(fill.map(f => rpIndexAt(R, f.t)))].sort((a,b)=>a-b)};\n"
    "  }\n"
    "  let RP = null; // 目前掛載的重播",
))

# ---- 4. rpMount:算我的委託 / 成交
EDITS.append((
    "    const G = rpGrid(R);\n",
    "    const G = rpGrid(R), my = rpMy(R);\n",
))
EDITS.append((
    "    RP = {R, G, i, t, center:null, full: rpKeepFull, raf:0, play:null, speed: rpKeepSpeed, firstLock, el:null};",
    "    RP = {R, G, my, i, t, center:null, full: rpKeepFull, raf:0, play:null, speed: rpKeepSpeed, firstLock, el:null};",
))

# ---- 5. 控制列:跳到上一筆 / 下一筆我自己的成交
EDITS.append((
    ">${lockTxt}</button></div>",
    ">${lockTxt}</button>"
    '<button type="button" id="rpFPrev" title="上一筆你自己的成交(回報收到時刻)">◀ 上一筆我的成交</button>'
    '<button type="button" id="rpFNext" title="下一筆你自己的成交(回報收到時刻)">下一筆我的成交 ▶</button></div>',
))
EDITS.append((
    'RP.el = {range: $("rpRange"), play: $("rpPlay"), prev: $("rpPrev"), next: $("rpNext"), lock: $("rpLock"), speed:',
    'RP.el = {range: $("rpRange"), play: $("rpPlay"), prev: $("rpPrev"), next: $("rpNext"), lock: $("rpLock"), fprev: $("rpFPrev"), fnext: $("rpFNext"), speed:',
))
EDITS.append((
    '    RP.el.lock.addEventListener("click", ()=> rpGo(RP.firstLock));\n',
    '    RP.el.lock.addEventListener("click", ()=> rpGo(RP.firstLock));\n'
    '    RP.el.fprev.addEventListener("click", ()=> rpGoFill(-1));\n'
    '    RP.el.fnext.addEventListener("click", ()=> rpGoFill(1));\n',
))

# ---- 6. 說明列
EDITS.append((
    "橫條按這檔當天 13:25 前最大單格量 ${R.qmax.toLocaleString()} 張歸一(之後的收盤集合競價 / 排隊量超過就畫滿)。</p>`;",
    "橫條按這檔當天 13:25 前最大單格量 ${R.qmax.toLocaleString()} 張歸一(之後的收盤集合競價 / 排隊量超過就畫滿)。"
    "階梯上的「委」/「成」= 你自己的委託與成交(上方圖例「你的委託 / 成交」一起開關):委託自送出畫到刪單或成交,"
    "不推估佇列順位(五檔只有總量)。${my.mkt ? `這天這檔另有 ${my.mkt} 筆市價委託沒畫在格子上(市價單不停在任何價位)。` : \"\"}</p>`;",
))

# ---- 7. rpGoFill
EDITS.append((
    "  function rpStop(){",
    "  function rpGoFill(dir){ // 跳到上一筆 / 下一筆我自己的成交(則號 = 收到時刻 ≤ 該成交回報時刻的最後一則)\n"
    "    if(!RP) return; const xs = RP.my.idx, i = RP.i;\n"
    "    let to = null;\n"
    "    if(dir < 0){ for(const k of xs){ if(k >= i) break; to = k; } } else to = xs.find(k => k > i);\n"
    "    if(to != null) rpGo(to);\n"
    "  }\n"
    "  function rpStop(){",
))

# ---- 8. rpCtrl:兩顆新按鈕的停用狀態
EDITS.append((
    "    el.prev.disabled = i <= 0; el.next.disabled = last; el.lock.disabled = RP.firstLock < 0;",
    "    el.prev.disabled = i <= 0; el.next.disabled = last; el.lock.disabled = RP.firstLock < 0;\n"
    "    el.fprev.disabled = !RP.my.idx.some(k => k < i); el.fnext.disabled = !RP.my.idx.some(k => k > i);",
))

# ---- 9. rpDraw:格子上的「委」/「成」
EDITS.append((
    "    const qmax = Math.max(1, R.qmax);\n"
    "    const cell = (q, side) => q == null ? `<div class=\"rp-q ${side}\" role=\"cell\"></div>` : `<div class=\"rp-q ${side}\" role=\"cell\"><span class=\"rp-bar\" style=\"width:${Math.min(100, q/qmax*100).toFixed(1)}%\"></span><span class=\"rp-n mono\">${q.toLocaleString()}</span></div>`;\n",
    "    const qmax = Math.max(1, R.qmax);\n"
    "    // 我的委託 / 成交:委託 = 送出 ≤ 這一則收到時刻 < 結束(結束為 null = 畫到收盤);成交 = 回報收到時刻 ≤ 這一則。\n"
    "    // 一個開關(圖例「你的委託 / 成交」)同時管上方圖的成交標記與這裡的兩種標記。\n"
    "    const meBuy = new Map(), meSell = new Map();\n"
    "    if(state.show.fills){\n"
    "      const now = R.recv[i];\n"
    "      const at = (side, px) => { const m = side > 0 ? meBuy : meSell; let v = m.get(px); if(!v){ v = {oq:0, on:0, unk:0, fq:0, fn:0, tip:[]}; m.set(px, v); } return v; };\n"
    "      RP.my.ord.forEach(o => { if(o.t0 > now || (o.t1 != null && o.t1 <= now)) return;\n"
    "        const v = at(o.side, o.px); v.oq += o.qty; v.on++; if(o.kind === \"未知\") v.unk++;\n"
    "        v.tip.push(`委託 ${fmtT(o.t0/1000)} ${o.side > 0 ? \"買\" : \"賣\"} ${rpPx(o.px)} × ${o.qty} 張 → ${o.t1 == null ? (o.kind === \"未知\" ? \"當日成交資料還沒補,不知道它何時消失\" : \"到收盤沒成交也沒刪單\") : o.kind + \" \" + fmtT(o.t1/1000)}`); });\n"
    "      RP.my.fill.forEach(f => { if(f.t > now) return;\n"
    "        const v = at(f.side, f.px); v.fq += f.qty; v.fn++;\n"
    "        v.tip.push(`成交 ${fmtT(f.t/1000)} ${f.label} ${rpPx(f.px)} × ${f.qty} 張(回報收到時刻)`); });\n"
    "    }\n"
    "    const meTag = (p, side) => { const v = (side === \"buy\" ? meBuy : meSell).get(p); if(!v) return \"\";\n"
    "      const tip = ` title=\"${esc(v.tip.join(\"\\n\"))}\"`;\n"
    "      return (v.on ? `<span class=\"rp-me ord${v.unk ? \" unk\" : \"\"}\"${tip}>委${v.unk ? \"?\" : \"\"} ${v.oq}</span>` : \"\") + (v.fn ? `<span class=\"rp-me fill ${side}\"${tip}>成 ${v.fq}</span>` : \"\"); };\n"
    "    const cell = (q, side, p) => { const tag = meTag(p, side);\n"
    "      if(q == null) return `<div class=\"rp-q ${side}\" role=\"cell\">${tag}</div>`;\n"
    "      const bar = `<span class=\"rp-bar\" style=\"width:${Math.min(100, q/qmax*100).toFixed(1)}%\"></span>`, num = `<span class=\"rp-n mono\">${q.toLocaleString()}</span>`;\n"
    "      return `<div class=\"rp-q ${side}\" role=\"cell\">${bar}${side === \"buy\" ? tag + num : num + tag}</div>`; };\n",
))
EDITS.append((
    "      h += `<div class=\"rp-row${p===px?\" cur\":\"\"}${p===G.limUp||p===G.limDn?\" lim\":\"\"}\" role=\"row\" data-p=\"${p}\">${cell(buy.get(p), \"buy\")}<div class=\"rp-p mono ${pcls}\" role=\"cell\"${p===G.limUp?' title=\"漲停\"':p===G.limDn?' title=\"跌停\"':\"\"}>${rpPx(p)}</div>${cell(sell.get(p), \"sell\")}</div>`; }",
    "      const me = meBuy.has(p) || meSell.has(p);\n"
    "      h += `<div class=\"rp-row${p===px?\" cur\":\"\"}${p===G.limUp||p===G.limDn?\" lim\":\"\"}${me?\" me\":\"\"}\" role=\"row\" data-p=\"${p}\">${cell(buy.get(p), \"buy\", p)}<div class=\"rp-p mono ${pcls}\" role=\"cell\"${p===G.limUp?' title=\"漲停\"':p===G.limDn?' title=\"跌停\"':\"\"}>${rpPx(p)}</div>${cell(sell.get(p), \"sell\", p)}</div>`; }",
))

# ---- 10. 定義與規則
EDITS.append((
    "        <li><b>限制</b>:五檔是聚合量",
    "        <li><b>我的委託 / 成交</b>:格子上的「委 n」= 你自己當時掛在那一格的委託張數,「成 n」= 到目前這一則為止你在那一格成交的張數(有標記的整列外框變色),滑鼠移上去看時刻明細;上方圖例的「你的委託 / 成交」一個開關同時關掉上方圖的成交標記與階梯上這兩種標記。「◀ 上一筆我的成交 / 下一筆我的成交 ▶」跳到自己的成交那一則(會先暫停播放)。委託來源 = 群益審計記錄的下單 / 刪單(<b>送出時刻只到秒</b>,且只知道送出去了,不知道交易所何時收到 / 刪成功);委託自送出畫到「成交」(配對到你的成交那一筆)或「刪單」(刪單送出時刻),兩者都沒有就畫到收盤。當天的成交資料還沒補時畫成虛線的「委?」並註明不知道何時消失,<b>不假裝它掛到收盤</b>。市價單不畫在格子上(它不停在任何價位),說明列會寫當天有幾筆;成交時刻是<b>回報收到時刻</b>(比交易所成交晚一點)。<b>不顯示委託的佇列順位</b> —— 五檔只有總量,排第幾推不出來,硬推是編數字。預設視野只有現價上下 10 檔,離現價較遠的委託要按「展開漲停–跌停」才看得到。</li>\n"
    "        <li><b>限制</b>:五檔是聚合量",
))


def sub(text, old, new):
    n = text.count(old)
    assert n == 1, f"錨點命中 {n} 次(要 1):{old[:70]!r}"
    return text.replace(old, new)


for old, new in EDITS:
    txt = sub(txt, old.replace("\n", "\r\n"), new.replace("\n", "\r\n"))
SRC.write_text(txt, encoding="utf-8", newline="")
b = SRC.read_bytes()
print("viewer_cdp_template.html 已補丁; CRLF", b.count(b"\r\n"), "LF", b.count(b"\n"))
