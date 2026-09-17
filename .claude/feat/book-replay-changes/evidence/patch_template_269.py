"""#269 回看頁模板改動(套在現用模板的複本上;保留 CRLF)。review round 1 收修版。

重播分頁:認外掛檔 v2(`chg` 變動分解、`eat` 吃檔)、三欄「價格階梯 | 這一則變了什麼 | 成交明細」,
中間欄與成交明細都只讀則號 RP.i(畫在 rpDraw 裡);定義與規則補說明。JS 只渲染:變動、掛入 / 撤單張數與吃檔
都由 copycat `book_replay` 算好寫進檔(格式唯一來源 = 模組說明「外掛檔 v2」),這裡不做加減。

review round 1 收修(code-review-round-1.json):
- P-02 中間欄改列最近 60 則(user 2026-09-17 拍板),定義與規則不再寫「播放跨過的則也看得到」
- S-10 價位變動讀 7 格 [碼, 價, 前量, 後量, 掛入, 成交, 撤單];空變動的說明用「當日第一份五檔」
  (= 第一則不是五檔全空的則,與 copycat decode 同一把尺),不再用 j === 0
- S-11 rpBuild 驗 chg 種類碼 0–7 與每項格數(RP_CHG_WIDTH,rpChangeLines 也用它推進)、eat 三格一組與值域;
  新碼的「價 null → —」收成 rpPrice(既有 rpKind 那行不動)
- S-04 新常數插在 RP_SPEEDS 整行(含行尾註解)之後;區段頭 v1 → v2;RP.i 註解列入中間欄 / 成交明細,
  刪掉「得自己記上次畫到哪一則」
- 重驗時 AI 截圖對照發現:中間欄長行折行後與下一行變動同一起點,數行容易數錯 → 變動行改懸掛縮排(折行縮進 12px,
  「回到五檔」的分行位置不變)

用法:python patch_template_269.py <工作模板路徑> [<diff 輸出路徑>]
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_bytes()
assert b"\r\n" in raw, "模板應為 CRLF"
original = raw.decode("utf-8").replace("\r\n", "\n")
s = original


def rep(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, (old[:90], s.count(old))
    s = s.replace(old, new)


def insert_after_line(anchor: str, lines: str) -> None:
    """在含 `anchor` 的那一整行(含行尾註解)之後插入 `lines`(每行以 \\n 結尾)。"""
    global s
    assert s.count(anchor) == 1, (anchor[:90], s.count(anchor))
    end = s.index("\n", s.index(anchor)) + 1
    s = s[:end] + lines + s[end:]


def rep_in_line(anchor: str, old: str, new: str, times: int) -> None:
    """含 `anchor` 的那一行裡,`old` 恰好出現 `times` 次,全部換成 `new`。"""
    global s
    assert s.count(anchor) == 1, (anchor[:90], s.count(anchor))
    start = s.rindex("\n", 0, s.index(anchor)) + 1
    end = s.index("\n", start)
    line = s[start:end]
    assert line.count(old) == times, (line[:90], line.count(old))
    s = s[:start] + line.replace(old, new) + s[end:]


# ---- CSS:三欄版面、變動清單、成交明細
rep(
    r""".rp-ctrl button:disabled{opacity:.45;cursor:default} .rp-ctrl button:disabled:hover{border-color:var(--line)}
""",
    r""".rp-ctrl button:disabled{opacity:.45;cursor:default} .rp-ctrl button:disabled:hover{border-color:var(--line)}
.rp-body{display:grid;gap:10px;align-items:start;grid-template-columns:minmax(300px,460px) minmax(260px,1fr) minmax(300px,390px);grid-template-areas:"ladder chg tape"}
.rp-body>.rp-ladder{grid-area:ladder;max-width:none}
.rp-col{min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.rp-col-chg{grid-area:chg} .rp-col-tape{grid-area:tape}
.rp-col-h{margin:0;padding:4px 10px;font-size:12px;font-weight:500;color:var(--ink-2);border-bottom:1px solid var(--grid);display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline}
.rp-chg{max-height:500px;overflow-y:auto;font-size:12px}
.rp-msg{padding:4px 10px;border-bottom:1px solid var(--grid)}
.rp-msg.cur{background:var(--sel)}
.rp-msg-h{display:flex;flex-wrap:wrap;gap:0 10px;color:var(--muted);font-size:11px}
.rp-msg.cur .rp-msg-h{color:var(--ink-2)}
.rp-line{padding:1px 0 1px 22px;text-indent:-12px}
.rp-line.dim{color:var(--muted)}
.rp-line .sub{display:block;padding-left:calc(1.4em - 12px);text-indent:0;color:var(--ink-2)}
.rp-tape{max-height:500px;overflow:auto}
.rp-tape th,.rp-tape td{padding:2px 8px;font-size:12px}
.rp-tape tr.cur td{background:var(--sel)}
.rp-tape td.dim{color:var(--muted)}
@media (max-width:1180px){ .rp-body{grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-areas:"ladder tape" "chg chg"} }
@media (max-width:820px){ .rp-body{grid-template-columns:minmax(0,1fr);grid-template-areas:"ladder" "chg" "tape"} }
""",
)

# ---- 定義與規則
rep(
    r"""以 <code>book-replay</code> 指令產生、放在同資料夾 <code>viewer-cdp-book/</code>(每檔每日一檔,切到重播分頁才載入)。""",
    r"""以 <code>book-replay</code> 指令產生、放在同資料夾 <code>viewer-cdp-book/</code>(每檔每日一檔,切到重播分頁才載入;本頁只讀外掛檔 v2,舊檔要用新版 <code>book-replay</code> 重產)。""",
)
rep(
    r"""        <li><b>非群組(簿重播)</b>:""",
    r"""        <li><b>這一則變了什麼</b>(中間欄):列到目前這一則為止最近 60 則,最新在上、目前這則標亮,往下捲看較早的則。播放時一次重畫常跨過好幾則,跨過的通常也在清單裡;高速播放遇到密集時段,一次可能跨過 60 則以上,要看每一則請暫停後逐則步進。每則以<b>價格</b>跟前一則比,只比兩則都<b>看得到</b>的價位(買方 = 第五檔買價以上、賣方 = 第五檔賣價以下;某側不滿五檔 = 整側看得到):量增加 = 掛單;量減少先扣這個價位的成交,剩下的算撤單。成交則附的五檔常晚幾則才更新(一口氣連吃好幾檔時),所以之後 8 則、1 秒內同價位減少的量仍先算成交;鎖漲跌停時市價排隊減少也先算成交。</li>
        <li><b>被擠出五檔 / 回到五檔</b>:價位掉到第五檔之外(掛單通常還在,只是看不到)列「被擠出五檔」;回到看得到的範圍列「⟳ 回到五檔」,給離開時量、現在量、離開期間這個價位的成交、淨掛(= 現在 − 離開時 + 期間成交)與離開多久 —— <b>不算掛單</b>,看不到的那段無法分辨是一次掛進或分次堆積;量沒變、期間也沒成交時淡色一行。從沒看過的價位帶量進來列「首次進入五檔」,也不算掛單。價格穿過某個價位(賣方價位變成買方價位)一直看得到,不算被擠出。</li>
        <li><b>五檔全空</b>:達錢在暫緩撮合開始那一刻會送一則買賣兩側全空的五檔(之後改每 5 秒更新),這一則不算撤單,下一則跟全空之前那一份比。</li>
        <li><b>成交明細</b>(右欄):到目前這一則為止最近 20 筆成交,跟階梯永遠是同一刻;目前這則是成交時標亮。時間 = 達錢成交時刻(即時只到整秒)。<b>吃檔</b> = 這筆成交扣到成交前那一則五檔的第幾檔,例「吃 賣1 −12」;一口氣連吃好幾檔會依序出現 賣1、賣2…;鎖漲停時吃的是市價排隊(「吃 市價買」);價位在第五檔之外列「五檔外」;看不出吃了哪一檔(開收盤集合競價、同一則又掛進來)列「—」。</li>
        <li><b>非群組(簿重播)</b>:""",
)

# ---- JS:區段頭 v1 → v2(S-04)
rep_in_line("  // ---- 重播(簿重播外掛檔 v1", "外掛檔 v1", "外掛檔 v2", times=2)

# ---- JS:常數,插在 RP_SPEEDS 整行(含行尾註解)之後(S-04)
insert_after_line(
    "  const RP_SPEEDS = [1, 2, 5, 10], RP_MAX_DT = 250;",
    r"""  const RP_CHG_KEEP = 60, RP_TAPE_KEEP = 20; // 中間欄列幾則變動、成交明細列幾筆(都到目前這一則為止,新的在上;user 2026-09-17 拍板 60 則)
  const RP_CHG_WIDTH = [7, 3, 8, 3]; // 外掛檔 v2 chg 每項佔幾格(含種類碼),依基本碼 ÷ 2:價位變動 / 被擠出五檔 / 重新可見 / 首次進入五檔(= copycat book_replay 的 _CHANGE_KINDS)
""",
)

# ---- JS:RP.i 說明(S-04)
rep(
    r"""階梯、標籤、現價、十字線都讀它,重繪不從時刻回推。""",
    r"""階梯、標籤、現價、十字線、中間欄(這一則變了什麼)與成交明細都讀它,重繪不從時刻回推。""",
)
rep(
    r"""可能跨過好幾則,要逐則交代變動的面板得自己記上次畫到哪一則。""",
    r"""可能跨過好幾則;中間欄不另記狀態,列到 RP.i 為止最近 RP_CHG_KEEP 則,一次跨過更多則時較早的那幾則要逐則步進才看得到。""",
)

# ---- rpBuild:v2、chg / eat 形狀與內容、成交則號、五檔全空、當日第一份五檔
rep(
    r"""    if(p.v !== 1) bad(`版本 ${p.v}(本頁只認 1)`);""",
    r"""    if(p.v !== 2) bad(`版本 ${p.v}(本頁只認 2;舊檔請用新版 copycat book-replay 重產)`);""",
)
rep(
    r"""    if(p.kf.length !== Math.ceil(n/K)) bad("keyframe 個數與 n 不符");""",
    r"""    if(p.kf.length !== Math.ceil(n/K)) bad("keyframe 個數與 n 不符");
    if(!Array.isArray(p.chg) || p.chg.length !== n) bad("chg(變動分解)長度與 n 不符");""",
)
rep(
    r"""    const clockAt = new Int32Array(n), tradeAt = new Int32Array(n); // 則號 ≤ i 的最後一個時鐘點 / 最後一個成交(在 trade 的序號);-1 = 還沒有
    let k = -1, ci = -1, clock = -Infinity;
    for(let i=0;i<n;i++){
      const ch = p.kind[i];
      if(ch === "t"){ k++; if(""",
    r"""    const clockAt = new Int32Array(n), tradeAt = new Int32Array(n); // 則號 ≤ i 的最後一個時鐘點 / 最後一個成交(在 trade 的序號);-1 = 還沒有
    const tradeIdx = []; // 第 k 筆成交在第幾則
    let k = -1, ci = -1, clock = -Infinity;
    for(let i=0;i<n;i++){
      const ch = p.kind[i];
      if(ch === "t"){ k++; tradeIdx.push(i); if(""",
)
rep(
    r"""    if(p.trade.length !== (k+1)*4) bad("trade 長度與成交則數不符");
    const book = new Array(20).fill(null); let qmax = 0, qmaxDay = 0; const prices = new Set();""",
    r"""    if(p.trade.length !== (k+1)*4) bad("trade 長度與成交則數不符");
    if(!Array.isArray(p.eat) || p.eat.length !== k+1) bad("eat(吃檔)長度與成交則數不符");
    const book = new Array(20).fill(null); let qmax = 0, qmaxDay = 0; const prices = new Set();
    const cleared = new Uint8Array(n); let filled = 0; // 五檔全空(達錢清空)的則;filled = 目前有值的格數""",
)
rep(
    r"""      for(let j=0;j<d.length;j+=2){ const f = d[j]; if(!Number.isInteger(f) || f < 0 || f > 19) bad(`第 ${i} 則欄號 ${f}`); book[f] = d[j+1]; touched[sideOf[f]*5 + levelOf[f]] = 1; }""",
    r"""      for(let j=0;j<d.length;j+=2){ const f = d[j]; if(!Number.isInteger(f) || f < 0 || f > 19) bad(`第 ${i} 則欄號 ${f}`); filled += (d[j+1] != null) - (book[f] != null); book[f] = d[j+1]; touched[sideOf[f]*5 + levelOf[f]] = 1; }
      cleared[i] = filled === 0;""",
)
rep(
    r"""    for(let t=0;t<=k;t++){ const px = p.trade[t*4+1]; if(px > 0) prices.add(px); }""",
    r"""    // chg / eat 的結構(種類碼、每項格數、吃檔三格一組與值域);數值與前後兩則五檔的一致由 copycat decode 落檔前核對
    for(let i=0;i<n;i++){ const c = p.chg[i]; if(!Array.isArray(c)) bad(`第 ${i} 則 chg 不是陣列`);
      for(let q=0;q<c.length;){ const code = c[q]; if(!Number.isInteger(code) || code < 0 || code >= 2*RP_CHG_WIDTH.length) bad(`第 ${i} 則變動種類碼 ${code}`); const w = RP_CHG_WIDTH[code >> 1]; if(q + w > c.length) bad(`第 ${i} 則變動項目格數不足(種類碼 ${code})`); q += w; } }
    for(let t=0;t<=k;t++){ const e = p.eat[t]; if(!Array.isArray(e) || e.length % 3) bad(`第 ${tradeIdx[t]} 則吃檔不是三格一組`);
      for(let q=0;q<e.length;q+=3){ const lv = e[q+1]; if((e[q] !== 0 && e[q] !== 1) || !(lv === null || (Number.isInteger(lv) && lv >= 0 && lv <= 5)) || !Number.isInteger(e[q+2]) || e[q+2] <= 0) bad(`第 ${tradeIdx[t]} 則吃檔 [${e[q]}, ${lv}, ${e[q+2]}]`); } }
    for(let t=0;t<=k;t++){ const px = p.trade[t*4+1]; if(px > 0) prices.add(px); }""",
)
rep(
    r"""    return {key, code:p.code, date:p.date, n, K, kf:p.kf, d:p.d, kind:p.kind, recv, trade:p.trade, anom, clockAt, tradeAt, qmax, prices, BP, BQ, AP, AQ};""",
    r"""    return {key, code:p.code, date:p.date, n, K, kf:p.kf, d:p.d, kind:p.kind, recv, trade:p.trade, anom, clockAt, tradeAt, qmax, prices, BP, BQ, AP, AQ, chg:p.chg, eat:p.eat, tradeIdx:Int32Array.from(tradeIdx), cleared, firstBook:cleared.indexOf(0)};""",
)

# ---- 變動清單與成交明細(只渲染)
rep(
    r"""  const rpPx = p => { const tk = tickMilli(p);""",
    r"""  // ---- 這一則變了什麼 / 成交明細(外掛檔 v2 `chg` / `eat`,copycat 算好寫進檔;這裡只排版,不做加減)
  const rpSideTxt = s => s ? "賣" : "買";
  const rpAt = (s, p) => p === 0 ? `市價${rpSideTxt(s)}` : `${rpSideTxt(s)} ${rpPx(p)}`;
  const rpQty = q => q.toLocaleString();
  const rpPrice = m => m == null ? "—" : fmtP(m/1000);
  const rpDur = ms => { if(ms < 9950) return `${(ms/1000).toFixed(1)} 秒`; const s = Math.round(ms/1000); if(s < 60) return `${s} 秒`; if(s < 3600) return `${Math.floor(s/60)} 分 ${s%60} 秒`; return `${Math.floor(s/3600)} 時 ${Math.floor(s%3600/60)} 分`; };
  const rpSideCell = side => side === "outer" ? '<span class="pos">外</span>' : side === "inner" ? '<span class="neg">內</span>' : "中";
  function rpChangeLines(R, j){ // 第 j 則的變動(格式見 copycat book_replay 模組說明「外掛檔 v2」的 chg;rpBuild 已驗種類碼與格數)
    const c = R.chg[j];
    if(!c.length) return `<div class="rp-line dim">${j === R.firstBook ? "當日第一份五檔(沒有前一份可比)" : R.cleared[j] ? "五檔全空(達錢清空五檔,常見於暫緩撮合開始;不算撤單)" : "五檔沒有變動"}</div>`;
    let h = "";
    for(let q=0; q<c.length; q += RP_CHG_WIDTH[c[q] >> 1]){
      const at = rpAt(c[q] % 2, c[q+1]);
      switch(c[q] >> 1){
        case 0: { const parts = []; // [碼, 價, 前量, 後量, 掛入, 成交, 撤單]
          if(c[q+4]) parts.push(`+${rpQty(c[q+4])} 掛單`);
          if(c[q+5]) parts.push(`−${rpQty(c[q+5])} 成交`);
          if(c[q+6]) parts.push(`−${rpQty(c[q+6])} 撤單`);
          h += `<div class="rp-line">${at} <span class="mono">${rpQty(c[q+2])} → ${rpQty(c[q+3])}</span> ${parts.join("、")}</div>`; break; }
        case 1: h += `<div class="rp-line dim">${at} ${rpQty(c[q+2])} 張被擠出五檔</div>`; break; // [碼, 價, 離開前的量]
        case 2: { const left = c[q+2], now = c[q+3], traded = c[q+4], net = c[q+5], away = rpDur(c[q+7]); // [碼, 價, 離開時量, 現在量, 期間成交, 淨掛, 離開則號, 離開毫秒]
          h += left === now && !traded
            ? `<div class="rp-line dim">⟳ ${at} 回到五檔,量沒變(${rpQty(now)} 張,離開 ${away})</div>`
            : `<div class="rp-line">⟳ ${at} 回到五檔<span class="sub">離開時 ${rpQty(left)} → 現在 ${rpQty(now)}</span><span class="sub">離開期間成交 ${rpQty(traded)} → 淨掛 ${net > 0 ? "+" : net < 0 ? "−" : ""}${rpQty(Math.abs(net))}</span><span class="sub">離開 ${away}</span><span class="sub">(一次掛進或分次堆積無法分辨)</span></div>`;
          break; }
        case 3: h += `<div class="rp-line">${at} 首次進入五檔 ${rpQty(c[q+2])} 張(之前沒看過,不算掛單)</div>`; break; // [碼, 價, 量]
      }
    }
    return h;
  }
  function rpChanges(R, i){ // 中間欄:第 i 則往前最近 RP_CHG_KEEP 則,新的在上(只看則號,不記上次畫到哪一則)
    let h = "";
    for(let j=i; j>=0 && j>i-RP_CHG_KEEP; j--){
      const t = R.kind[j] === "t" ? R.tradeAt[j]*4 : -1;
      const tr = t < 0 ? "" : `<span>成交 ${rpPrice(R.trade[t+1])} × ${R.trade[t+2]==null?"—":rpQty(R.trade[t+2])} ${rpSideCell(R.trade[t+3])}</span>`;
      h += `<div class="rp-msg${j === i ? " cur" : ""}"><div class="rp-msg-h"><span class="mono">第 ${(j+1).toLocaleString()} 則</span><span class="mono">${fmtMs(R.recv[j])} 收到</span>${tr}</div>${rpChangeLines(R, j)}</div>`;
    }
    $("rpChg").innerHTML = h;
  }
  const rpEatText = e => { if(!e.length) return "—"; const out = []; for(let q=0;q<e.length;q+=3){ const s = rpSideTxt(e[q]), lv = e[q+1]; out.push(`吃 ${lv === null ? s + "五檔外" : lv === 0 ? "市價" + s : s + lv} −${rpQty(e[q+2])}`); } return out.join("、"); };
  function rpTape(R, i){ // 成交明細:則號 ≤ i 的最後 RP_TAPE_KEEP 筆成交,新的在上
    const last = R.tradeAt[i]; let h = "";
    if(last < 0) h = '<tr><td colspan="5" class="dim">這一則之前還沒有成交</td></tr>';
    for(let k=last; k>=0 && k>last-RP_TAPE_KEEP; k--){
      const j = R.tradeIdx[k], t = k*4, ms = R.trade[t], anom = R.anom.has(j);
      h += `<tr class="${j === i ? "cur" : ""}"><td class="mono${anom ? " dim" : ""}"${anom ? ' title="達錢時刻異常,不當標籤時刻"' : ""}>${ms == null ? "—" : fmtT(Math.floor(ms/1000))}</td><td class="num mono">${rpPrice(R.trade[t+1])}</td><td class="num mono">${R.trade[t+2]==null?"—":rpQty(R.trade[t+2])}</td><td>${rpSideCell(R.trade[t+3])}</td><td class="mono">${rpEatText(R.eat[k])}</td></tr>`;
    }
    $("rpTape").innerHTML = h;
  }
  const rpPx = p => { const tk = tickMilli(p);""",
)

# ---- rpMount:三欄
rep(
    r"""      <div class="rp-ladder" id="rpLadder" role="table" aria-label="價格階梯"></div>
""",
    r"""      <div class="rp-body"><div class="rp-ladder" id="rpLadder" role="table" aria-label="價格階梯"></div><section class="rp-col rp-col-chg" aria-label="這一則變了什麼"><h3 class="rp-col-h">這一則變了什麼<span class="kbd">最近 ${RP_CHG_KEEP} 則,新的在上</span></h3><div class="rp-chg" id="rpChg"></div></section><section class="rp-col rp-col-tape" aria-label="成交明細"><h3 class="rp-col-h">成交明細<span class="kbd">到這一則為止最近 ${RP_TAPE_KEEP} 筆,新的在上</span></h3><div class="rp-tape"><table><thead><tr><th>時間</th><th class="num">價</th><th class="num">張</th><th>內外</th><th>吃檔</th></tr></thead><tbody id="rpTape"></tbody></table></div></section></div>
""",
)

# ---- rpDraw:同一則號畫中間欄與成交明細(放在階梯之前:階梯在沒有價位時會提早 return)
rep(
    r"""    $("rpClock").textContent = clockTxt;
    rpCtrl();""",
    r"""    $("rpClock").textContent = clockTxt;
    rpCtrl();
    rpChanges(R, i); rpTape(R, i);""",
)

path.write_bytes(s.replace("\n", "\r\n").encode("utf-8"))
print("patched", path)
if len(sys.argv) > 2:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        s.splitlines(keepends=True),
        "viewer_cdp_template.html (live, before #269)",
        "viewer_cdp_template.html (#269)",
    )
    text = "".join(diff)
    Path(sys.argv[2]).write_text(text, encoding="utf-8", newline="\n")
    added = sum(1 for line in text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in text.splitlines() if line.startswith("-") and not line.startswith("---"))
    print(f"diff → {sys.argv[2]}(+{added} / −{removed})")
