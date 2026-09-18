// #272 回歸:改前(viewer-cdp.pre272.html)/ 改後(viewer-cdp.html)兩頁,既有分頁的 DOM 要逐字相同。
// 改後多了 payload 的 mo(我的委託)與重播分頁的標記 —— 逐筆 / 當日事件 / 回測 / 活潑日索引 / 頁頭一格都不該動。
import { writeFileSync } from 'node:fs';
import { launch, openPage, selectDay, clickTab, REVIEW } from './pp_common.mjs';

const PAIRS = [
  ['3441', '2026-09-16'], ['2426', '2026-09-16'], ['2426', '2026-09-18'],
  ['6179', '2026-09-18'], ['3026', '2026-09-16'], ['2305', '2026-09-16'],
  ['3008', '2026-07-15'], ['2455', '2026-08-13'],   // 沒有簿的舊日子 + 有委託的舊日子
];
const TABS = ['ticks', 'events', 'bt', 'idx', 'def'];

async function snap(url) {
  const browser = await launch();
  try {
    const { page, errors } = await openPage(browser, url);
    const out = { errors, days: {} };
    for (const [code, date] of PAIRS) {
      await selectDay(page, code, date);
      const per = {};
      for (const tab of TABS) {
        await clickTab(page, tab);
        per[tab] = await page.evaluate(t => document.getElementById('tab-' + t).innerHTML, tab);
      }
      per.head = await page.evaluate(() => document.getElementById('dayInfo').innerHTML + '|' + document.getElementById('groupInfo').innerHTML);
      per.legend = await page.evaluate(() => [...document.querySelectorAll('#legend .chip')].map(b => b.textContent).join('|'));
      out.days[`${code}|${date}`] = per;
    }
    return out;
  } finally { await browser.close(); }
}

const before = await snap(REVIEW + 'viewer-cdp.pre272.html');
const after = await snap(REVIEW + 'viewer-cdp.html');
const diffs = [];
for (const key of Object.keys(before.days)) {
  for (const tab of [...TABS, 'head', 'legend']) {
    const a = before.days[key][tab], b = after.days[key][tab];
    if (a !== b) diffs.push({ key, tab, beforeLen: a.length, afterLen: b.length, sample: [a.slice(0, 200), b.slice(0, 200)] });
  }
}
// 定義與規則、圖例是刻意改的:單獨列出來看差在哪
const expected = diffs.filter(d => d.tab === 'def' || d.tab === 'legend');
const unexpected = diffs.filter(d => d.tab !== 'def' && d.tab !== 'legend');
const res = { pairs: PAIRS.length, tabs: TABS.length, unexpected, expectedTabs: [...new Set(expected.map(d => d.tab))], errorsBefore: before.errors, errorsAfter: after.errors };
writeFileSync(new URL('./result_dom_regression.json', import.meta.url), JSON.stringify(res, null, 1), 'utf8');
console.log(JSON.stringify({ unexpected: unexpected.length, expectedTabs: res.expectedTabs, errorsBefore: before.errors.length, errorsAfter: after.errors.length }));
for (const d of unexpected) console.log('DIFF', d.key, d.tab, d.beforeLen, d.afterLen);
