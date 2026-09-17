// #270 回歸:改前頁(viewer-cdp.pre270.html)與新頁各開獨立 context,做同樣操作後逐區塊比對。
// (1) 既有分頁:5 組 代號|日期 + 一組互動(開前三個圖例、回測選 A、K 週期 5)後,分時 / K 線 SVG、頁頭、族群列、圖例、
//     左欄、逐筆、當日事件、回測、活潑日索引、分頁鈕、定義與規則(新頁扣掉新增的三條重播說明後須相同);
//     逐筆分頁上 ← → 換日後的日期與畫面。
// (2) 重播分頁本體:同一組拖曳時刻,階梯 innerHTML、標籤、成交則、收到、現價、市價佇列、展開鈕、兩張圖(十字線)須相同
//     (新頁多出的只有「第幾則」與播放控制列、說明文字)。
// 用法:node dom_regression.mjs <out.json>
import { writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { launch, openPage, selectDay, clickTab, openReplay, setFull, drag, NEW_PAGE, OLD_PAGE } from './pp_common.mjs';

const OUT = process.argv[2];
const COMBOS = [['2426', '2026-09-16'], ['8064', '2026-09-09'], ['1815', '2026-07-01'], ['3441', '2026-09-10'], ['2344', '2026-08-20']];
const NEW_DEF_LIS = ['<li><b>播放</b>', '<li><b>逐則步進</b>', '<li><b>跳到首次鎖漲停</b>'];
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
async function existingTabs(url) {
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
  // 重播分頁本體
  const rp = [];
  for (const code of ['2426', '1815', '3441', '8064', '2344', '6770', '2305']) {
    await openReplay(page, code, '2026-09-16');
    const [t0, t1] = await page.evaluate(() => { const r = document.getElementById('rpRange'); return [Number(r.min), Number(r.max)]; });
    let seed = Number(code); const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
    const ts = [t0, t1, ...Array.from({ length: 13 }, () => t0 + Math.floor(rnd() * (t1 - t0)))];
    for (const [k, t] of ts.entries()) {
      await setFull(page, k % 5 === 4);
      await drag(page, t);
      rp.push([`${code}@${t}${k % 5 === 4 ? ' 展開' : ''}`, await page.evaluate(() => {
        const h = id => document.getElementById(id).innerHTML;
        return { ladder: h('rpLadder'), clock: h('rpClock'), kind: h('rpKind'), recv: h('rpRecv'), px: h('rpPx'), mkt: h('rpMkt'), full: h('rpFull'), chartL: h('chartL'), chartR: h('chartR') };
      })]);
    }
    await setFull(page, false);
  }
  await browser.close();
  return { caps, rp, errors };
}

const oldR = await existingTabs(OLD_PAGE);
const newR = await existingTabs(NEW_PAGE);
const diffs = [];
let compared = 0;
for (const [k, [label, o]] of oldR.caps.entries()) {
  const n = newR.caps[k][1];
  for (const key of Object.keys(o)) {
    let nv = n[key];
    if (key === 'def') nv = nv.split('\n').filter(line => !NEW_DEF_LIS.some(p => line.trim().startsWith(p))).join('\n');
    compared++;
    if (nv !== o[key]) diffs.push({ label, key, old: sha(o[key]), new: sha(nv) });
  }
}
for (const [k, [label, o]] of oldR.rp.entries()) {
  const n = newR.rp[k][1];
  for (const key of Object.keys(o)) { compared++; if (n[key] !== o[key]) diffs.push({ label: '重播 ' + label, key, old: sha(o[key]), new: sha(n[key]) }); }
}
const defAdded = newR.caps[0][1].def.split('\n').filter(line => NEW_DEF_LIS.some(p => line.trim().startsWith(p))).length;
const out = {
  existing: oldR.caps.map(([label, o], k) => ({ label, old: Object.fromEntries(Object.entries(o).map(([key, v]) => [key, sha(v)])), new: Object.fromEntries(Object.entries(newR.caps[k][1]).map(([key, v]) => [key, sha(v)])) })),
  replaySamples: oldR.rp.length, compared, diffs, defAddedLines: defAdded, oldErrors: oldR.errors, newErrors: newR.errors,
};
writeFileSync(OUT, JSON.stringify(out, null, 1));
console.log(JSON.stringify({ compared, diffs: diffs.length, firstDiffs: diffs.slice(0, 8), replaySamples: oldR.rp.length, defAddedLines: defAdded, oldErrors: oldR.errors, newErrors: newR.errors }, null, 1));
