// #269 回歸(沿 #270 dom_regression):舊頁(現用 viewer-cdp.html 複本,讀 v1)與測試頁(讀暫存 v2)各開獨立 context,
// 做同樣操作後逐區塊比對。
// (1) 既有分頁:6 組 代號|日期(含 09-17 與非群組 2305)+ 一組互動(開前三個圖例、回測選 A、K 週期 5)後,分時 / K 線 SVG、
//     頁頭、族群列、圖例、左欄、逐筆、當日事件、回測、活潑日索引、分頁鈕、定義與規則(新頁扣掉新增的四條重播說明與
//     「本頁只讀外掛檔 v2」一句後須相同);逐筆分頁上 ← → 換日後的日期與畫面。
// (2) 重播分頁原有部分:同一組拖曳時刻,階梯 innerHTML、標籤、成交則、收到、現價、市價佇列、展開鈕、兩張圖(十字線)須相同
//     (v1 / v2 的簿、收到時刻、成交完全相同,只多變動與吃檔)。
// 用法:node dom_regression.mjs <out.json>
import { writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { launch, openPage, selectDay, clickTab, openReplay, setFull, drag, NEW_PAGE, OLD_PAGE } from './pp_common.mjs';

const OUT = process.argv[2];
const COMBOS = [['2426', '2026-09-16'], ['8064', '2026-09-09'], ['1815', '2026-07-01'], ['3441', '2026-09-10'], ['2344', '2026-08-20'], ['2426', '2026-09-17'], ['2305', '2026-09-16']];
const NEW_DEF_LIS = ['<li><b>這一則變了什麼</b>', '<li><b>被擠出五檔 / 回到五檔</b>', '<li><b>五檔全空</b>', '<li><b>成交明細</b>'];
const NEW_DEF_SENTENCE = ';本頁只讀外掛檔 v2,舊檔要用新版 <code>book-replay</code> 重產';
const REPLAY = [['2426', '2026-09-16'], ['1815', '2026-09-16'], ['3441', '2026-09-16'], ['8064', '2026-09-16'], ['2344', '2026-09-16'], ['2305', '2026-09-16'], ['2426', '2026-09-17'], ['2303', '2026-09-17']];
const sha = s => createHash('sha1').update(s).digest('hex').slice(0, 12) + ':' + s.length;

async function waitTicks(page) {
  await page.waitForFunction(() => { const t = document.getElementById('tab-ticks').textContent; return !/載入逐筆中/.test(t); }, { timeout: 60000 });
}
async function capture(page) {
  return page.evaluate(() => {
    const h = id => document.getElementById(id).innerHTML;
    return { chartL: h('chartL'), chartR: h('chartR'), dayInfo: h('dayInfo'), groupInfo: h('groupInfo'), legend: h('legend'), rail: h('codeList'),
      ticks: h('tab-ticks'), events: h('tab-events'), bt: h('tab-bt'), idx: h('tab-idx'), tabs: document.querySelector('.tabs').outerHTML, def: h('tab-def'),
      date: document.getElementById('dateSel').value, code: document.getElementById('codeSel').value };
  });
}
async function run(url) {
  const browser = await launch();
  const { page, errors } = await openPage(browser, url);
  const caps = [];
  for (const [c, d] of COMBOS) { await selectDay(page, c, d); await waitTicks(page); caps.push(['' + c + '|' + d, await capture(page)]); }
  await selectDay(page, '2426', '2026-09-16'); await waitTicks(page);
  await page.evaluate(() => { const chips = [...document.querySelectorAll('#legend button.chip')].slice(0, 3); chips.forEach(b => b.click());
    const bt = document.getElementById('btSel'); bt.value = 'A_AH_hold'; bt.dispatchEvent(new Event('change'));
    const kn = document.getElementById('knSel'); kn.value = '5'; kn.dispatchEvent(new Event('change')); });
  await waitTicks(page);
  caps.push(['互動後 2426|09-16', await capture(page)]);
  for (const tab of ['events', 'bt', 'idx', 'def', 'ticks']) { await clickTab(page, tab); }
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('ArrowLeft'); await waitTicks(page); caps.push(['逐筆分頁 ← 後', await capture(page)]);
  await page.keyboard.press('ArrowRight'); await waitTicks(page); caps.push(['逐筆分頁 → 後', await capture(page)]);
  const rp = [];
  for (const [code, date] of REPLAY) {
    await openReplay(page, code, date);
    const [t0, t1] = await page.evaluate(() => { const r = document.getElementById('rpRange'); return [Number(r.min), Number(r.max)]; });
    let seed = Number(code) + Number(date.slice(-2)); const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
    const ts = [t0, t1, ...Array.from({ length: 13 }, () => t0 + Math.floor(rnd() * (t1 - t0)))];
    for (const [k, t] of ts.entries()) {
      await setFull(page, k % 5 === 4);
      await drag(page, t);
      rp.push([`${code}|${date}@${t}${k % 5 === 4 ? ' 展開' : ''}`, await page.evaluate(() => {
        const h = id => document.getElementById(id).innerHTML;
        return { ladder: h('rpLadder'), clock: h('rpClock'), kind: h('rpKind'), recv: h('rpRecv'), px: h('rpPx'), mkt: h('rpMkt'), full: h('rpFull'), idx: h('rpIdx'), chartL: h('chartL'), chartR: h('chartR') };
      })]);
    }
    await setFull(page, false);
  }
  await browser.close();
  return { caps, rp, errors };
}

const oldR = await run(OLD_PAGE);
const newR = await run(NEW_PAGE);
const diffs = [];
let compared = 0;
for (const [k, [label, o]] of oldR.caps.entries()) {
  const n = newR.caps[k][1];
  for (const key of Object.keys(o)) {
    let nv = n[key];
    if (key === 'def') nv = nv.split('\n').filter(line => !NEW_DEF_LIS.some(p => line.trim().startsWith(p))).join('\n').replace(NEW_DEF_SENTENCE, '');
    compared++;
    if (nv !== o[key]) diffs.push({ label, key, old: sha(o[key]), new: sha(nv) });
  }
}
for (const [k, [label, o]] of oldR.rp.entries()) {
  const n = newR.rp[k][1];
  for (const key of Object.keys(o)) { compared++; if (n[key] !== o[key]) diffs.push({ label: '重播 ' + label, key, old: sha(o[key]), new: sha(n[key]) }); }
}
const defAdded = newR.caps[0][1].def.split('\n').filter(line => NEW_DEF_LIS.some(p => line.trim().startsWith(p))).length;
const hashesDistinct = new Set(oldR.caps.map(([, o]) => sha(o.chartL))).size;
const out = { compared, diffs, replaySamples: oldR.rp.length, defAddedLines: defAdded, defSentenceFound: newR.caps[0][1].def.includes(NEW_DEF_SENTENCE),
  distinctChartHashes: hashesDistinct, oldErrors: oldR.errors, newErrors: newR.errors };
writeFileSync(OUT, JSON.stringify(out, null, 1));
console.log(JSON.stringify({ compared, diffs: diffs.length, firstDiffs: diffs.slice(0, 8), replaySamples: oldR.rp.length, defAddedLines: defAdded, defSentenceFound: out.defSentenceFound, distinctChartHashes: hashesDistinct, oldErrors: oldR.errors, newErrors: newR.errors }, null, 1));
